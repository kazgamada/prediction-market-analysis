"""Range backfill of OrderFilled logs.

Public entrypoint: `backfill_range(client, from_block, to_block, *, progress_cb)`.

  * Splits the range into chunks via JsonRpcClient.iter_logs.
  * Decodes successful chunks and persists trades.
  * Pushes failed chunks to the dead-letter table (T1).
  * Updates the cursor monotonically (T6) after each batch.
  * Caches block timestamps to avoid N RPC calls per chunk.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from copytrader.chain.client import JsonRpcClient
from copytrader.chain.contracts import exchange_addresses, order_filled_topic0
from copytrader.chain.decoder import decode_order_filled
from copytrader.indexer import cursor as cursor_mod
from copytrader.indexer import dead_letters
from copytrader.indexer.persist import mark_blocks_seen, persist_trades

log = logging.getLogger(__name__)

CURSOR_NAME = "orderfilled_backfill"

ProgressCb = Callable[[dict[str, Any]], None] | None


async def backfill_range(
    client: JsonRpcClient,
    *,
    from_block: int,
    to_block: int,
    chunk_size: int = 1000,
    progress_cb: ProgressCb = None,
) -> dict[str, Any]:
    """Backfill OrderFilled events in [from_block, to_block]. Returns summary."""
    addrs = exchange_addresses()
    topic0 = order_filled_topic0()

    total_logs = 0
    chunks_ok = 0
    chunks_empty = 0
    chunks_failed = 0
    ts_cache: dict[int, int] = {}
    # Completed (OK/EMPTY) chunks keyed by from_block. The cursor is only
    # advanced along the *contiguous* frontier starting at `from_block`, so a
    # FAILED chunk — or a chunk that simply hasn't arrived yet (iter_logs
    # yields in completion order, not block order) — leaves a gap that holds
    # the cursor back. This makes the cursor a true low-water mark ("every
    # block <= cursor has been fully scanned"), so a crash mid-range or a
    # dead-lettered chunk is re-scanned by the next catchup instead of being
    # silently skipped (idempotent: trade upsert + signal de-dup).
    completed_chunks: dict[int, int] = {}

    def frontier_block() -> int:
        cur = from_block
        while cur in completed_chunks:
            cur = completed_chunks[cur] + 1
        return cur - 1

    async def block_ts(block: int) -> int:
        if block in ts_cache:
            return ts_cache[block]
        ts = await client.get_block_timestamp(block)
        ts_cache[block] = ts
        return ts

    async for chunk in client.iter_logs(
        from_block=from_block,
        to_block=to_block,
        topics=[topic0, None, None, None],
        addresses=addrs,
        chunk_size=chunk_size,
    ):
        if chunk.status == "FAILED":
            chunks_failed += 1
            dead_letters.push(
                kind="logs_range",
                request={
                    "from_block": chunk.from_block,
                    "to_block": chunk.to_block,
                    "topics": [topic0],
                    "addresses": addrs,
                },
                error_text=chunk.error or "unknown",
            )
            log.warning(
                "chunk FAILED [%d, %d] -> dead-letter (holds cursor frontier): %s",
                chunk.from_block, chunk.to_block, chunk.error,
            )
            continue

        if chunk.status == "EMPTY":
            chunks_empty += 1
        else:
            chunks_ok += 1
            decoded = []
            blocks_in_chunk: dict[int, int] = {}
            for raw in chunk.logs:
                bn = (
                    int(raw["blockNumber"], 16)
                    if isinstance(raw["blockNumber"], str)
                    else raw["blockNumber"]
                )
                try:
                    ts = await block_ts(bn)
                    trade = decode_order_filled(raw, ts)
                    decoded.append(trade)
                    blocks_in_chunk[bn] = blocks_in_chunk.get(bn, 0) + 1
                except Exception as e:  # noqa: BLE001
                    log.exception("decode failed for log at block %d: %s", bn, e)

            if decoded:
                persist_trades(decoded)
                mark_blocks_seen(blocks_in_chunk)
                total_logs += len(decoded)

        # Mark this chunk complete and advance the cursor only as far as the
        # contiguous confirmed frontier (never past a FAILED/missing gap).
        completed_chunks[chunk.from_block] = chunk.to_block
        frontier = frontier_block()

        if frontier >= from_block:
            try:
                cursor_mod.advance(
                    CURSOR_NAME, frontier,
                    block_ts=datetime.now(UTC),
                )
            except Exception:
                log.exception("cursor.advance failed; will retry next chunk")

        if progress_cb:
            progress_cb({
                "from_block": from_block,
                "to_block": to_block,
                "cursor": frontier,
                "logs": total_logs,
                "chunks_ok": chunks_ok,
                "chunks_empty": chunks_empty,
                "chunks_failed": chunks_failed,
            })

    return {
        "from_block": from_block,
        "to_block": to_block,
        "cursor": frontier_block(),
        "logs": total_logs,
        "chunks_ok": chunks_ok,
        "chunks_empty": chunks_empty,
        "chunks_failed": chunks_failed,
    }
