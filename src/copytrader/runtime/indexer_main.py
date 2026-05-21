"""`indexer` process entrypoint.

Boot order (mirrors web_main.py):
  1. Health server in a background thread (FIRST — so /readyz responds even if migrate crashes)
  2. alembic migration (best-effort; failure is logged and parks the indexer)
  3. Indexer supervisor
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading

from copytrader.chain.errors import redact_url
from copytrader.config import settings
from copytrader.health.server import HealthServer
from copytrader.logging_setup import setup_logging

log = logging.getLogger("runtime.indexer")

_MIGRATION_STATE: dict[str, str | None] = {"status": "pending", "error": None}


def _dump_boot_env() -> None:
    def present(name: str) -> str:
        v = os.environ.get(name) or ""
        return f"set (len={len(v)})" if v else "UNSET"
    log.info("boot env:")
    log.info("  DATABASE_URL: %s", present("DATABASE_URL"))
    log.info("  POLYGON_RPC_HTTP: %s (%s)",
             present("POLYGON_RPC_HTTP"), redact_url(settings.polygon_rpc_http))
    log.info("  POLYGON_RPC_WS: %s (%s)",
             present("POLYGON_RPC_WS"), redact_url(settings.polygon_rpc_ws))


def _run_migrations_safely() -> None:
    global _MIGRATION_STATE
    try:
        from copytrader.db.engine import run_migrations
        run_migrations()
        _MIGRATION_STATE = {"status": "ok", "error": None}
    except Exception as e:  # noqa: BLE001
        log.exception("migration failed; indexer will park")
        _MIGRATION_STATE = {
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
        }


async def _rpc_check() -> tuple[bool, str]:
    if not settings.polygon_rpc_http:
        return False, "polygon_rpc_http unset"
    from copytrader.chain.client import JsonRpcClient
    client = JsonRpcClient(settings.polygon_rpc_http)
    try:
        block = await client.get_block_number()
        return True, f"head={block}"
    finally:
        await client.aclose()


async def amain() -> None:
    # ヘルスサーバーはスレッドで先行起動済み (main() -> _start_health_in_thread)。
    # amain では indexer 本体の起動だけ担う。

    if _MIGRATION_STATE["status"] != "ok":
        log.error("indexer parked: migration not ok; health server still running on port %d",
                  settings.health_port + 1)
        await asyncio.Event().wait()
        return

    try:
        from copytrader.indexer.supervisor import run as run_indexer
    except ImportError as e:
        log.warning("indexer modules not yet implemented (%s); health-only mode", e)
        await asyncio.Event().wait()
        return

    await run_indexer()


def _start_health_in_thread() -> None:
    """Health server in background thread — starts BEFORE migrations (T21)."""
    rpc_check = _rpc_check

    async def readyz_with_state(request):  # type: ignore[no-untyped-def]
        from aiohttp import web as _w

        from copytrader.db.engine import ping as db_ping
        db_ok = db_ping()
        body = {
            "status": "ok" if db_ok else "degraded",
            "db": "ok" if db_ok else "down",
            "migration": _MIGRATION_STATE,
            "role": "indexer",
        }
        return _w.json_response(body, status=200 if db_ok else 503)

    health = HealthServer(settings.health_port + 1, rpc_check)
    health.readyz = readyz_with_state  # type: ignore[assignment]

    def runner() -> None:
        asyncio.run(health.run_forever())

    t = threading.Thread(target=runner, name="health-indexer", daemon=True)
    t.start()
    log.info("health server started on port %d", settings.health_port + 1)


def main() -> None:
    setup_logging()
    log.info("indexer_main: boot start (git_sha=%s build_time=%s)",
             settings.git_sha, settings.build_time)
    _dump_boot_env()
    _start_health_in_thread()  # step 1: health server first
    _run_migrations_safely()   # step 2: migrate
    asyncio.run(amain())       # step 3: indexer supervisor


if __name__ == "__main__":
    main()
