"""WebSocket stream of OrderFilled events into the trade table."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

import websockets

from copytrader.chain.contracts import (
    CTF_EXCHANGE,
    NEGRISK_CTF_EXCHANGE,
    ORDER_FILLED_TOPIC,
)
from copytrader.config import get_settings
from copytrader.db import session_scope
from copytrader.indexer.decoder import DecodedTrade, decode
from copytrader.models import Trade
from sqlalchemy.dialects.postgresql import insert
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

log = logging.getLogger(__name__)


def _exchange_for(addr: str) -> str:
    a = addr.lower()
    if a == CTF_EXCHANGE.lower():
        return "ctf"
    if a == NEGRISK_CTF_EXCHANGE.lower():
        return "negrisk"
    return "unknown"


async def subscribe_logs(
    on_trade: Callable[[DecodedTrade], Awaitable[None]],
    ws_url: str | None = None,
) -> None:
    """Connect to a Polygon WS endpoint and yield decoded trades to on_trade.

    Reconnects with exponential backoff on disconnect.
    """
    settings = get_settings()
    url = ws_url or settings.polygon_rpc_ws
    if not url:
        raise RuntimeError("POLYGON_RPC_WS is required for streaming")

    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_http, request_kwargs={"timeout": 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    from copytrader.chain.contracts import ORDER_FILLED_ABI

    contracts = {
        "ctf": w3.eth.contract(
            address=Web3.to_checksum_address(CTF_EXCHANGE), abi=[ORDER_FILLED_ABI]
        ),
        "negrisk": w3.eth.contract(
            address=Web3.to_checksum_address(NEGRISK_CTF_EXCHANGE), abi=[ORDER_FILLED_ABI]
        ),
    }

    sub_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_subscribe",
        "params": [
            "logs",
            {
                "address": [CTF_EXCHANGE, NEGRISK_CTF_EXCHANGE],
                "topics": [ORDER_FILLED_TOPIC],
            },
        ],
    }

    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(sub_payload))
                ack = json.loads(await ws.recv())
                log.info("subscribed: %s", ack.get("result"))
                backoff = 1.0
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        if msg.get("method") != "eth_subscription":
                            continue
                        log_ev = msg["params"]["result"]
                        exchange = _exchange_for(log_ev["address"])
                        if exchange == "unknown":
                            continue
                        log_ev_normalized = {
                            "address": log_ev["address"],
                            "topics": [bytes.fromhex(t[2:]) for t in log_ev["topics"]],
                            "data": log_ev["data"],
                            "blockNumber": int(log_ev["blockNumber"], 16),
                            "transactionHash": bytes.fromhex(log_ev["transactionHash"][2:]),
                            "logIndex": int(log_ev["logIndex"], 16),
                            "blockHash": bytes.fromhex(log_ev["blockHash"][2:]),
                            "transactionIndex": int(log_ev["transactionIndex"], 16),
                            "removed": log_ev.get("removed", False),
                        }
                        if log_ev_normalized["removed"]:
                            continue
                        decoded_args = (
                            contracts[exchange]
                            .events.OrderFilled()
                            .process_log(log_ev_normalized)
                        )
                        trade = decode(log_ev_normalized, dict(decoded_args["args"]), exchange)
                        if trade:
                            trade.block_timestamp = datetime.now(timezone.utc)
                            await on_trade(trade)
                    except Exception as e:
                        # 単一メッセージの失敗で WS ループを止めない
                        log.warning("decode/handle failed in stream: %s", e)
        except (websockets.WebSocketException, OSError) as e:
            log.warning("WS disconnected: %s; reconnecting in %.1fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        except Exception as e:
            # 想定外の例外でも reconnect する。死なせない。
            log.exception("WS loop unexpected error: %s; reconnecting in %.1fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


async def persist_trade(t: DecodedTrade) -> None:
    row = dict(
        tx_hash=t.tx_hash,
        log_index=t.log_index,
        block_number=t.block_number,
        block_timestamp=t.block_timestamp,
        exchange=t.exchange,
        order_hash=t.order_hash,
        maker=t.maker,
        taker=t.taker,
        maker_asset_id=t.maker_asset_id,
        taker_asset_id=t.taker_asset_id,
        maker_amount=t.maker_amount,
        taker_amount=t.taker_amount,
        fee=t.fee,
        token_id=t.token_id,
        side=t.side,
        price=t.price,
        size=t.size,
        notional_usd=t.notional_usd,
    )
    with session_scope() as session:
        stmt = insert(Trade).values([row]).on_conflict_do_nothing(
            index_elements=["tx_hash", "log_index"]
        )
        session.execute(stmt)
