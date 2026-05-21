"""Periodically retry RPC chunks parked in `rpc_dead_letters` (T1)."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from copytrader.chain.client import JsonRpcClient
from copytrader.chain.decoder import decode_order_filled
from copytrader.indexer import dead_letters
from copytrader.indexer.persist import mark_blocks_seen, persist_trades

log = logging.getLogger(__name__)


async def _retry_one(client: JsonRpcClient, dl_id: int, request: dict) -> bool:
    """Return True on success."""
    addrs = request["addresses"]
    topics = request["topics"] + [None] * (4 - len(request["topics"]))
    from_block = request["from_block"]
    to_block = request["to_block"]

    ts_cache: dict[int, int] = {}
    async for chunk in client.iter_logs(
        from_block=from_block,
        to_block=to_block,
        topics=topics,
        addresses=addrs,
        chunk_size=max(1, to_block - from_block + 1),
    ):
        if chunk.status == "FAILED":
            dead_letters.mark_retry(dl_id, chunk.error or "unknown")
            return False
        if chunk.status == "EMPTY":
            dead_letters.mark_resolved(dl_id)
            return True
        decoded = []
        blocks: dict[int, int] = {}
        for raw in chunk.logs:
            bn = int(raw["blockNumber"], 16) if isinstance(raw["blockNumber"], str) else raw["blockNumber"]
            if bn not in ts_cache:
                ts_cache[bn] = await client.get_block_timestamp(bn)
            try:
                decoded.append(decode_order_filled(raw, ts_cache[bn]))
            except Exception as e:  # noqa: BLE001
                log.warning("dl id=%d decode failed for log %s: %s; skipping", dl_id, raw.get("transactionHash"), e)
                continue
            blocks[bn] = blocks.get(bn, 0) + 1
        if decoded:
            persist_trades(decoded)
            mark_blocks_seen(blocks)
        dead_letters.mark_resolved(dl_id)
        return True
    return False


async def run_retry_loop(client: JsonRpcClient, *, interval_s: int = 60) -> None:
    """Forever: pull pending dead-letters, retry one at a time, sleep."""
    while True:
        try:
            rows = dead_letters.pending(limit=20)
            if rows:
                log.info("retrying %d dead-letter chunk(s)", len(rows))
            for r in rows:
                ok = await _retry_one(client, r.id, r.request)
                log.info("dl id=%d retry result=%s (retries=%d)", r.id, ok, r.retries)
        except Exception as e:  # noqa: BLE001
            log.exception("retry loop error: %s", e)
        await asyncio.sleep(interval_s)


def _emit_risk(kind: str, message: str, severity: int = 2, ctx: dict[str, Any] | None = None) -> None:
    from copytrader.db.engine import get_session
    from copytrader.db.models import RiskEvent
    with get_session() as s:
        s.add(RiskEvent(kind=kind, severity=severity, message=message, context=ctx))
        s.flush()
    log.warning("risk_event ts=%s kind=%s msg=%s", datetime.now(UTC).isoformat(), kind, message)
