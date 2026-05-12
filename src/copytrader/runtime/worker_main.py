"""`worker` process entrypoint.

In S3 this becomes the job-queue dequeue loop. For S1, health-only.
"""
from __future__ import annotations

import asyncio
import logging

from copytrader.config import settings
from copytrader.db.engine import run_migrations
from copytrader.health.server import HealthServer
from copytrader.logging_setup import setup_logging

log = logging.getLogger("runtime.worker")


async def _rpc_check() -> tuple[bool, str]:
    # Worker doesn't strictly need RPC, but report something.
    return True, "worker"


async def amain() -> None:
    health = HealthServer(settings.health_port + 2, _rpc_check)
    try:
        from copytrader.jobs.runner import run as run_worker
    except ImportError as e:
        log.warning("worker modules not yet implemented (%s); running health-only", e)
        await health.run_forever()
        return

    await asyncio.gather(health.run_forever(), run_worker())


def main() -> None:
    setup_logging()
    run_migrations()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
