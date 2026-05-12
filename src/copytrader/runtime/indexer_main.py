"""`indexer` process entrypoint.

Mirrors web_main.py boot order: health server FIRST, then migrate (best-
effort), then the actual indexer supervisor. This way crash-on-boot is
observable via /readyz rather than just a generic Fly "appears to be
crashing" message.
"""
from __future__ import annotations

import asyncio
import logging
import os

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
    health = HealthServer(settings.health_port + 1, _rpc_check)

    # Augment readyz with migration + role info.
    original_readyz = health.readyz

    async def readyz(request):  # type: ignore[no-untyped-def]
        resp = await original_readyz(request)
        try:
            import json
            body = json.loads(resp.body.decode())
        except Exception:  # noqa: BLE001
            body = {}
        body["migration"] = _MIGRATION_STATE
        body["role"] = "indexer"
        from aiohttp import web as _w
        return _w.json_response(body, status=resp.status)

    health.readyz = readyz  # type: ignore[assignment]

    if _MIGRATION_STATE["status"] != "ok":
        log.error("indexer parked: migration not ok")
        await health.run_forever()
        return

    try:
        from copytrader.indexer.supervisor import run as run_indexer
    except ImportError as e:
        log.warning("indexer modules not yet implemented (%s); running health-only", e)
        await health.run_forever()
        return

    await asyncio.gather(
        health.run_forever(),
        run_indexer(),
    )


def main() -> None:
    setup_logging()
    log.info("indexer_main: boot start (git_sha=%s build_time=%s)",
             settings.git_sha, settings.build_time)
    _dump_boot_env()
    _run_migrations_safely()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
