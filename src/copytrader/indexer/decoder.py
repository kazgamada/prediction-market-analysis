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
    """Decode an OrderFilled event log + decoded args into a normalized trade.

    Returns None for trades that aren't USDC <-> outcome-token (e.g. fpmm splits).
    The Polymarket CTF Exchange always has one side as USDC (asset_id == 0); skip
    anything else defensively.
    """
    maker_asset = int(args["makerAssetId"])
    taker_asset = int(args["takerAssetId"])
    if maker_asset != 0 and taker_asset != 0:
        return None
    if maker_asset == 0 and taker_asset == 0:
        return None

    maker_amount = int(args["makerAmountFilled"])
    taker_amount = int(args["takerAmountFilled"])
    fee = int(args.get("fee", 0))

    if maker_asset == 0:
        # maker provides USDC -> taker receives USDC's counter-asset (sells)
        # Wait: maker gives USDC, taker gives outcome tokens.
        # From the taker's perspective: taker is providing tokens for USDC = SELL.
        token_id = str(taker_asset)
        usdc_amount = Decimal(maker_amount)
        token_amount = Decimal(taker_amount)
        side = "SELL"  # taker pov
    else:
        token_id = str(maker_asset)
        usdc_amount = Decimal(taker_amount)
        token_amount = Decimal(maker_amount)
        side = "BUY"  # taker pov: gets tokens for USDC

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
        maker_asset_id=str(maker_asset),
        taker_asset_id=str(taker_asset),
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
