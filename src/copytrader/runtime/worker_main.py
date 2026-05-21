"""`worker` process entrypoint.

Mirrors web_main.py / indexer_main.py boot order: health server first,
migrate best-effort, then the job runner.
"""
from __future__ import annotations

import asyncio
import logging
import os

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
    health = HealthServer(settings.health_port + 2, _rpc_check)

    original_readyz = health.readyz

    async def readyz(request):  # type: ignore[no-untyped-def]
        resp = await original_readyz(request)
        try:
            import json
            body = json.loads(resp.body.decode())
        except Exception:  # noqa: BLE001
            body = {}
        body["migration"] = _MIGRATION_STATE
        body["role"] = "worker"
        from aiohttp import web as _w
        return _w.json_response(body, status=resp.status)

    health.readyz = readyz  # type: ignore[assignment]

    if _MIGRATION_STATE["status"] != "ok":
        log.error("worker parked: migration not ok")
        await health.run_forever()
        return

    try:
        from copytrader.jobs.runner import run as run_worker
    except ImportError as e:
        log.warning("worker modules not yet implemented (%s); running health-only", e)
        await health.run_forever()
        return

    # Seed and start the cron scheduler alongside the job runner.
    try:
        from copytrader.jobs.scheduler import run_scheduler, seed_default_schedule
        seed_default_schedule()
        scheduler_coro = run_scheduler(interval_seconds=60)
    except Exception as e:  # noqa: BLE001
        log.warning("scheduler init failed (%s); running without cron", e)

        async def scheduler_coro() -> None:  # type: ignore[no-redef]
            await asyncio.Event().wait()

    await asyncio.gather(
        health.run_forever(),
        run_worker(),
        scheduler_coro,
    )


def main() -> None:
    setup_logging()
    log.info("worker_main: boot start (git_sha=%s build_time=%s)",
             settings.git_sha, settings.build_time)
    _dump_boot_env()
    _run_migrations_safely()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
