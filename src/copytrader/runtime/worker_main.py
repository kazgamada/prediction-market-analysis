"""`worker` process entrypoint.

Boot order (mirrors web_main.py):
  1. Health server in a background thread (FIRST)
  2. alembic migration (best-effort)
  3. Job runner
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading

from copytrader.config import settings
from copytrader.health.server import HealthServer
from copytrader.logging_setup import setup_logging

log = logging.getLogger("runtime.worker")

_MIGRATION_STATE: dict[str, str | None] = {"status": "pending", "error": None}


def _dump_boot_env() -> None:
    def present(name: str) -> str:
        v = os.environ.get(name) or ""
        return f"set (len={len(v)})" if v else "UNSET"
    log.info("boot env:")
    log.info("  DATABASE_URL: %s", present("DATABASE_URL"))


def _run_migrations_safely() -> None:
    global _MIGRATION_STATE
    try:
        from copytrader.db.engine import run_migrations
        run_migrations()
        _MIGRATION_STATE = {"status": "ok", "error": None}
    except Exception as e:  # noqa: BLE001
        log.exception("migration failed; worker will park")
        _MIGRATION_STATE = {
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
        }


async def _rpc_check() -> tuple[bool, str]:
    return True, "worker"


async def amain() -> None:
    # ヘルスサーバーはスレッドで先行起動済み (main() -> _start_health_in_thread)。
    # amain では worker 本体の起動だけ担う。

    if _MIGRATION_STATE["status"] != "ok":
        log.error("worker parked: migration not ok; health server still running on port %d",
                  settings.health_port + 2)
        await asyncio.Event().wait()
        return

    try:
        from copytrader.jobs.runner import run as run_worker
    except ImportError as e:
        log.warning("worker modules not yet implemented (%s); health-only mode", e)
        await asyncio.Event().wait()
        return

    await run_worker()


def _start_health_in_thread() -> None:
    """Health server in background thread — starts BEFORE migrations (T21)."""

    async def readyz_with_state(request):  # type: ignore[no-untyped-def]
        from aiohttp import web as _w

        from copytrader.db.engine import ping as db_ping
        db_ok = db_ping()
        body = {
            "status": "ok" if db_ok else "degraded",
            "db": "ok" if db_ok else "down",
            "migration": _MIGRATION_STATE,
            "role": "worker",
        }
        return _w.json_response(body, status=200 if db_ok else 503)

    health = HealthServer(settings.health_port + 2, None)
    health.readyz = readyz_with_state  # type: ignore[assignment]

    def runner() -> None:
        asyncio.run(health.run_forever())

    t = threading.Thread(target=runner, name="health-worker", daemon=True)
    t.start()
    log.info("health server started on port %d", settings.health_port + 2)


def main() -> None:
    setup_logging()
    log.info("worker_main: boot start (git_sha=%s build_time=%s)",
             settings.git_sha, settings.build_time)
    _dump_boot_env()
    _start_health_in_thread()  # step 1: health server first
    _run_migrations_safely()   # step 2: migrate
    asyncio.run(amain())       # step 3: job runner


if __name__ == "__main__":
    main()
