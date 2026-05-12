"""WebSocket subscription for new OrderFilled logs.

Reconnects with exponential backoff. Emits parsed log dicts. The consumer
is responsible for decoding and persisting.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import websockets

from copytrader.chain.errors import redact_url

log = logging.getLogger(__name__)


async def subscribe_logs(
    ws_url: str,
    *,
    addresses: list[str],
    topics: list[str | None],
) -> AsyncIterator[dict]:
    """Yield log dicts from `eth_subscribe` indefinitely.

    Handles reconnection with backoff. Caller iterates with `async for`.
    """
    backoff = 1
    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20) as ws:
                sub_req = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["logs", {"address": addresses, "topics": topics}],
                }
                await ws.send(json.dumps(sub_req))
                ack = json.loads(await ws.recv())
                if "error" in ack:
                    raise RuntimeError(f"subscribe error: {ack['error']}")
                log.info("WS subscribed: %s", redact_url(ws_url))
                backoff = 1
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("method") == "eth_subscription":
                        params = msg.get("params", {})
                        log_dict = params.get("result")
                        if log_dict:
                            yield log_dict
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("WS error (%s); reconnecting in %ds", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
