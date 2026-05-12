"""`indexer` process entrypoint.

In S2 this becomes: backfill + WS stream + dead-letter retry, all
supervised. For S1, it boots health + heartbeats.
"""
from __future__ import annotations

import asyncio
import logging

from copytrader.config import settings
from copytrader.db.engine import run_migrations
from copytrader.health.server import HealthServer
from copytrader.logging_setup import setup_logging

log = logging.getLogger("runtime.indexer")


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

    # Lazy import so S1 can boot even if S2 modules are missing.
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
    run_migrations()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
