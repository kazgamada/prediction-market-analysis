"""Indexer supervisor.

Runs three async tasks concurrently:
  * catchup loop: every N seconds, walk forward from cursor to head
  * stream consumer: WS subscription for live events
  * dead-letter retry loop

Each task is wrapped in a restart-on-exception harness (T10).
"""
from __future__ import annotations

import asyncio
import logging
import time

from copytrader.chain.client import JsonRpcClient
from copytrader.config import settings
from copytrader.indexer import cursor as cursor_mod
from copytrader.indexer.backfill import CURSOR_NAME, backfill_range
from copytrader.indexer.retry_dead_letters import run_retry_loop
from copytrader.indexer.stream_consumer import run_stream

log = logging.getLogger(__name__)

# Approx blocks per day on Polygon (~2s blocks => 43200/day).
BLOCKS_PER_DAY = 43200
CATCHUP_INTERVAL_S = 30


async def _supervised(name: str, coro_factory) -> None:
    """Run a task forever, restarting after exceptions (T10)."""
    backoff = 1
    while True:
        try:
            log.info("supervisor: starting task=%s", name)
            await coro_factory()
            log.warning("supervisor: task=%s exited cleanly; restarting", name)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("supervisor: task=%s crashed (%s); restarting in %ds", name, e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


async def _catchup_loop(client: JsonRpcClient) -> None:
    """Forever: from cursor to current head, fill any gap."""
    while True:
        head = await client.get_block_number()
        floor = head - settings.indexer_window_days * BLOCKS_PER_DAY
        # Seed cursor at floor on the very first run (T9).
        seed_block = cursor_mod.ensure_floor(CURSOR_NAME, floor)
        if seed_block >= head:
            await asyncio.sleep(CATCHUP_INTERVAL_S)
            continue
        from_block = seed_block + 1
        to_block = head
        log.info(
            "catchup: window=%dd, head=%d, from=%d, to=%d (gap=%d blocks)",
            settings.indexer_window_days, head, from_block, to_block, to_block - from_block,
        )
        started = time.time()
        summary = await backfill_range(
            client,
            from_block=from_block,
            to_block=to_block,
            chunk_size=settings.indexer_chunk_size,
        )
        log.info(
            "catchup done: logs=%d ok=%d empty=%d failed=%d in %.1fs",
            summary["logs"], summary["chunks_ok"], summary["chunks_empty"],
            summary["chunks_failed"], time.time() - started,
        )
        await asyncio.sleep(CATCHUP_INTERVAL_S)


async def run() -> None:
    if not settings.polygon_rpc_http:
        log.error("POLYGON_RPC_HTTP unset; indexer cannot run")
        # Park but stay alive so the process doesn't crashloop.
        await asyncio.Event().wait()
        return

    client = JsonRpcClient(
        settings.polygon_rpc_http,
        max_parallel=settings.indexer_max_parallel,
        max_retries=settings.indexer_max_retries,
    )

    try:
        await asyncio.gather(
            _supervised("catchup", lambda: _catchup_loop(client)),
            _supervised("stream", lambda: run_stream(client, settings.polygon_rpc_ws)),
            _supervised("dead-letter-retry", lambda: run_retry_loop(client)),
        )
    finally:
        await client.aclose()
