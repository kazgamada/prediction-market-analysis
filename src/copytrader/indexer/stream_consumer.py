"""Consume the WS subscription, decode + persist, advance cursor."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from datetime import UTC, datetime

from copytrader.chain.client import JsonRpcClient
from copytrader.chain.contracts import exchange_addresses, order_filled_topic0
from copytrader.chain.decoder import decode_order_filled
from copytrader.chain.stream import subscribe_logs
from copytrader.config import settings
from copytrader.db.engine import get_session
from copytrader.db.models import RiskEvent
from copytrader.indexer import cursor as cursor_mod
from copytrader.indexer.backfill import CURSOR_NAME
from copytrader.indexer.persist import mark_blocks_seen, persist_trades

log = logging.getLogger(__name__)


async def run_stream(http_client: JsonRpcClient, ws_url: str) -> None:
    """Subscribe to OrderFilled logs and persist them as they arrive.

    If we go >10 minutes without a single log, file a `risk_event` (F14).
    The aliveness check runs in a separate watchdog task so it fires even
    when the WebSocket is disconnected and reconnecting (not yielding logs).
    """
    if not ws_url:
        log.warning("no WS url configured; skipping stream")
        return

    last_received = time.time()
    addrs = exchange_addresses()
    topic0 = order_filled_topic0()

    async def _watchdog() -> None:
        nonlocal last_received
        while True:
            await asyncio.sleep(60)
            if time.time() - last_received > 600:
                _emit_risk(
                    "ws_idle",
                    severity=2,
                    message=f"no logs received in >10min via {settings.polygon_rpc_ws[:40]}...",
                )
                last_received = time.time()

    watchdog_task = asyncio.create_task(_watchdog())
    try:
        async for raw in subscribe_logs(
            ws_url, addresses=addrs, topics=[topic0, None, None, None],
        ):
            try:
                bn = (
                    int(raw["blockNumber"], 16)
                    if isinstance(raw["blockNumber"], str)
                    else raw["blockNumber"]
                )
                ts = await http_client.get_block_timestamp(bn)
                trade = decode_order_filled(raw, ts)
                persist_trades([trade])
                mark_blocks_seen({bn: 1})
                cursor_mod.advance(CURSOR_NAME, bn, datetime.now(UTC))
                last_received = time.time()
            except Exception as e:  # noqa: BLE001
                log.exception("stream decode/persist failed: %s", e)
    finally:
        watchdog_task.cancel()
        with suppress(asyncio.CancelledError):
            await watchdog_task


def _emit_risk(kind: str, *, severity: int, message: str, context: dict | None = None) -> None:
    with get_session() as s:
        s.add(RiskEvent(kind=kind, severity=severity, message=message, context=context))
