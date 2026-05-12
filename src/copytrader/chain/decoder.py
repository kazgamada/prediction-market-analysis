"""Decode OrderFilled events into trade rows.

V2 OrderFilled signature:
  OrderFilled(
    bytes32 orderHash,         // indexed (topic1)
    address maker,             // indexed (topic2)
    address taker,             // indexed (topic3)
    uint8   side,              // data field 0
    uint256 makerAssetId,      // data field 1
    uint256 takerAssetId,      // data field 2
    uint256 makerAmountFilled, // data field 3
    uint256 takerAmountFilled, // data field 4
    bytes32 _builder,          // data field 5
    bytes32 _metadata          // data field 6
  )

Polymarket binary outcome tokens are ERC1155 token ids; collateral USDC
uses asset id 0. So:
  side=BUY  (0): maker pays USDC, gets outcome tokens
                 makerAssetId=0,  takerAssetId=token_id
                 maker_amount=usdc, taker_amount=shares
  side=SELL (1): maker pays outcome tokens, gets USDC
                 makerAssetId=token_id, takerAssetId=0
                 maker_amount=shares, taker_amount=usdc

Decoder normalizes to taker-side semantics:
  token_id = nonzero asset id
  side     = 0 if BUY (token taker pays USDC), 1 if SELL
  size_shares = shares amount (6 decimals on Polymarket CTF tokens? actually 1e18-scale)
  size_usdc   = USDC amount (1e6)
  price       = size_usdc / size_shares
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from copytrader.chain.contracts import exchange_name

# Polymarket CTF outcome tokens are 1e6 scaled like USDC (shares = USDC unit).
# OrderFilled uses raw uint256 amounts; both USDC and shares are 1e6.
DECIMALS_USDC = Decimal(10) ** 6
DECIMALS_SHARES = Decimal(10) ** 6


@dataclass
class DecodedTrade:
    tx_hash: bytes
    log_index: int
    block_number: int
    ts: datetime
    exchange: str
    order_hash: bytes
    maker: bytes
    taker: bytes
    side: int  # 0=BUY, 1=SELL
    maker_asset_id: int
    taker_asset_id: int
    maker_amount_filled: int
    taker_amount_filled: int
    token_id: int
    price: Decimal
    size_shares: Decimal
    size_usdc: Decimal


def _hex_to_int(h: str) -> int:
    return int(h, 16)


def _addr_from_topic(topic_hex: str) -> bytes:
    """Last 20 bytes of a 32-byte topic."""
    raw = bytes.fromhex(topic_hex[2:] if topic_hex.startswith("0x") else topic_hex)
    return raw[-20:]


def _bytes32_from_topic(topic_hex: str) -> bytes:
    raw = bytes.fromhex(topic_hex[2:] if topic_hex.startswith("0x") else topic_hex)
    return raw


def _slice_data(data_hex: str, n_words: int) -> list[str]:
    """Slice ABI-encoded data into 32-byte hex chunks."""
    h = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(h) < 64 * n_words:
        raise ValueError(f"data too short: have {len(h)} hex chars, need {64 * n_words}")
    return ["0x" + h[i * 64 : (i + 1) * 64] for i in range(n_words)]


def decode_order_filled(log: dict, block_timestamp: int) -> DecodedTrade:
    """Decode a single OrderFilled log dict (as returned by eth_getLogs)."""
    topics: list[str] = log["topics"]
    if len(topics) < 4:
        raise ValueError(f"OrderFilled expects 4 topics, got {len(topics)}")

    order_hash = _bytes32_from_topic(topics[1])
    maker = _addr_from_topic(topics[2])
    taker = _addr_from_topic(topics[3])

    fields = _slice_data(log["data"], 7)
    side = _hex_to_int(fields[0]) & 0xFF
    maker_asset_id = _hex_to_int(fields[1])
    taker_asset_id = _hex_to_int(fields[2])
    maker_amount_filled = _hex_to_int(fields[3])
    taker_amount_filled = _hex_to_int(fields[4])

    if side == 0:  # BUY (maker pays USDC -> shares)
        token_id = taker_asset_id
        size_usdc = Decimal(maker_amount_filled) / DECIMALS_USDC
        size_shares = Decimal(taker_amount_filled) / DECIMALS_SHARES
    elif side == 1:  # SELL (maker pays shares -> USDC)
        token_id = maker_asset_id
        size_shares = Decimal(maker_amount_filled) / DECIMALS_SHARES
        size_usdc = Decimal(taker_amount_filled) / DECIMALS_USDC
    else:
        raise ValueError(f"unexpected side byte: {side}")

    price = (size_usdc / size_shares) if size_shares > 0 else Decimal(0)

    tx_hash = bytes.fromhex(log["transactionHash"][2:])
    log_index = int(log["logIndex"], 16) if isinstance(log["logIndex"], str) else log["logIndex"]
    block_number = (
        int(log["blockNumber"], 16) if isinstance(log["blockNumber"], str) else log["blockNumber"]
    )

    return DecodedTrade(
        tx_hash=tx_hash,
        log_index=log_index,
        block_number=block_number,
        ts=datetime.fromtimestamp(block_timestamp, tz=UTC),
        exchange=exchange_name(log["address"]),
        order_hash=order_hash,
        maker=maker,
        taker=taker,
        side=side,
        maker_asset_id=maker_asset_id,
        taker_asset_id=taker_asset_id,
        maker_amount_filled=maker_amount_filled,
        taker_amount_filled=taker_amount_filled,
        token_id=token_id,
        price=price,
        size_shares=size_shares,
        size_usdc=size_usdc,
    )


def decoded_to_row(d: DecodedTrade) -> dict:
    """Convert to a dict suitable for `bulk_upsert(table=Trade.__table__, ...)`."""
    return {
        "tx_hash": d.tx_hash,
        "log_index": d.log_index,
        "block_number": d.block_number,
        "ts": d.ts,
        "exchange": d.exchange,
        "order_hash": d.order_hash,
        "maker": d.maker,
        "taker": d.taker,
        "side": d.side,
        "maker_asset_id": d.maker_asset_id,
        "taker_asset_id": d.taker_asset_id,
        "maker_amount_filled": d.maker_amount_filled,
        "taker_amount_filled": d.taker_amount_filled,
        "token_id": d.token_id,
        "price": d.price,
        "size_shares": d.size_shares,
        "size_usdc": d.size_usdc,
    }
