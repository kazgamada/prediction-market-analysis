"""Decode raw OrderFilled events into normalized trade rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from copytrader.chain.contracts import USDC_DECIMALS

USDC_UNIT = Decimal(10) ** USDC_DECIMALS


@dataclass
class DecodedTrade:
    tx_hash: str
    log_index: int
    block_number: int
    block_timestamp: datetime | None
    exchange: str
    order_hash: str
    maker: str
    taker: str
    maker_asset_id: str
    taker_asset_id: str
    maker_amount: int
    taker_amount: int
    fee: int
    token_id: str
    side: str  # 'BUY' or 'SELL' from taker pov
    price: Decimal
    size: Decimal
    notional_usd: Decimal


def _hexify(b: bytes | str) -> str:
    if isinstance(b, bytes):
        return "0x" + b.hex()
    if isinstance(b, str) and not b.startswith("0x"):
        return "0x" + b
    return b


def decode(log: dict, args: dict, exchange: str) -> DecodedTrade | None:
    """Decode a V2 OrderFilled event into a normalized trade row.

    V2 イベントは V1 と異なり、`side` (uint8: 0=BUY, 1=SELL maker のオーダー方向)
    と `tokenId` を直接持つ (V1 の makerAssetId/takerAssetId ペアではない)。

    保存する `side` は **taker pov** にして V1 と同じ意味にする:
    - maker side BUY (maker が tokens を買う) → taker は tokens を渡している = SELL
    - maker side SELL (maker が tokens を売る) → taker は tokens を受け取る = BUY

    `maker_asset_id` / `taker_asset_id` は後方互換のため、どちら側が USDC かを
    "0" と tokenId で再現する (`wallet_side()` 等の既存ロジックがそのまま動く)。
    """
    side_raw = int(args["side"])  # 0 = maker BUY, 1 = maker SELL
    token_id_int = int(args["tokenId"])
    if token_id_int == 0:
        return None
    token_id = str(token_id_int)

    maker_amount = int(args["makerAmountFilled"])
    taker_amount = int(args["takerAmountFilled"])
    fee = int(args.get("fee", 0))

    if side_raw == 0:
        # maker is buying tokens: maker provides USDC, taker provides tokens
        usdc_amount = Decimal(maker_amount)
        token_amount = Decimal(taker_amount)
        maker_asset_id = "0"
        taker_asset_id = token_id
        side = "SELL"  # taker pov
    else:
        # maker is selling tokens: maker provides tokens, taker provides USDC
        usdc_amount = Decimal(taker_amount)
        token_amount = Decimal(maker_amount)
        maker_asset_id = token_id
        taker_asset_id = "0"
        side = "BUY"  # taker pov

    if token_amount <= 0:
        return None

    # Both USDC and token use 6 decimals -> ratio is unitless price 0..1
    price = (usdc_amount / token_amount).quantize(Decimal("0.00000001"))
    size = (token_amount / USDC_UNIT).quantize(Decimal("0.000001"))
    notional = (usdc_amount / USDC_UNIT).quantize(Decimal("0.000001"))

    tx_hash = log["transactionHash"]
    if isinstance(tx_hash, bytes):
        tx_hash = "0x" + tx_hash.hex()
    elif isinstance(tx_hash, str) and not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash

    order_hash = args["orderHash"]
    if isinstance(order_hash, bytes):
        order_hash = "0x" + order_hash.hex()

    return DecodedTrade(
        tx_hash=tx_hash,
        log_index=int(log["logIndex"]),
        block_number=int(log["blockNumber"]),
        block_timestamp=None,
        exchange=exchange,
        order_hash=order_hash,
        maker=str(args["maker"]).lower(),
        taker=str(args["taker"]).lower(),
        maker_asset_id=maker_asset_id,
        taker_asset_id=taker_asset_id,
        maker_amount=maker_amount,
        taker_amount=taker_amount,
        fee=fee,
        token_id=token_id,
        side=side,
        price=price,
        size=size,
        notional_usd=notional,
    )


def attach_timestamp(trade: DecodedTrade, unix_ts: int) -> DecodedTrade:
    trade.block_timestamp = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return trade
