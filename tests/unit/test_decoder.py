"""T2: V2 OrderFilled decoding."""
from __future__ import annotations

from decimal import Decimal

from copytrader.chain.contracts import (
    CTF_EXCHANGE_V2,
    NEG_RISK_CTF_EXCHANGE_V2,
    ORDER_FILLED_SIG,
    ORDER_FILLED_TOPIC0,
    exchange_name,
)
from copytrader.chain.decoder import decode_order_filled


def test_topic0_matches_canonical_signature() -> None:
    assert ORDER_FILLED_SIG.startswith("OrderFilled(")
    # topic0 is 32 bytes -> 0x + 64 hex chars
    assert ORDER_FILLED_TOPIC0.startswith("0x")
    assert len(ORDER_FILLED_TOPIC0) == 66


def test_exchange_name_lookup() -> None:
    assert exchange_name(CTF_EXCHANGE_V2) == "ctf"
    assert exchange_name(NEG_RISK_CTF_EXCHANGE_V2) == "neg_risk"
    assert exchange_name("0x" + "00" * 20) == "unknown"


def _u256(v: int) -> str:
    return f"{v:064x}"


def _addr_padded(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:].lower()


def _bytes32(val: int) -> str:
    return "0x" + f"{val:064x}"


def _build_log(*, side: int, maker_asset_id: int, taker_asset_id: int,
               maker_amount: int, taker_amount: int,
               maker_addr: str = "0x" + "11" * 20,
               taker_addr: str = "0x" + "22" * 20) -> dict:
    data = "0x" + "".join([
        _u256(side),
        _u256(maker_asset_id),
        _u256(taker_asset_id),
        _u256(maker_amount),
        _u256(taker_amount),
        _u256(0),  # builder
        _u256(0),  # metadata
    ])
    return {
        "address": CTF_EXCHANGE_V2,
        "blockNumber": "0x10",
        "transactionHash": "0x" + "ab" * 32,
        "logIndex": "0x2",
        "topics": [
            ORDER_FILLED_TOPIC0,
            _bytes32(0xdeadbeef),
            _addr_padded(maker_addr),
            _addr_padded(taker_addr),
        ],
        "data": data,
    }


def test_decode_buy_side() -> None:
    """BUY: maker pays USDC, receives shares of token_id."""
    log = _build_log(
        side=0,
        maker_asset_id=0,
        taker_asset_id=12345,
        maker_amount=10_000_000,  # 10 USDC
        taker_amount=20_000_000,  # 20 shares
    )
    d = decode_order_filled(log, block_timestamp=1_700_000_000)
    assert d.exchange == "ctf"
    assert d.side == 0
    assert d.token_id == 12345
    assert d.size_usdc == Decimal("10")
    assert d.size_shares == Decimal("20")
    assert d.price == Decimal("0.5")
    assert d.block_number == 16
    assert d.log_index == 2


def test_decode_sell_side() -> None:
    """SELL: maker pays shares of token_id, receives USDC."""
    log = _build_log(
        side=1,
        maker_asset_id=98765,
        taker_asset_id=0,
        maker_amount=50_000_000,  # 50 shares
        taker_amount=15_000_000,  # 15 USDC
    )
    d = decode_order_filled(log, block_timestamp=1_700_000_000)
    assert d.side == 1
    assert d.token_id == 98765
    assert d.size_shares == Decimal("50")
    assert d.size_usdc == Decimal("15")
    assert d.price == Decimal("0.3")


def test_decode_maker_taker_addresses() -> None:
    maker = "0x" + "aa" * 20
    taker = "0x" + "bb" * 20
    log = _build_log(
        side=0, maker_asset_id=0, taker_asset_id=1,
        maker_amount=1_000_000, taker_amount=1_000_000,
        maker_addr=maker, taker_addr=taker,
    )
    d = decode_order_filled(log, block_timestamp=0)
    assert d.maker.hex() == "aa" * 20
    assert d.taker.hex() == "bb" * 20


def test_decode_zero_shares_yields_zero_price() -> None:
    log = _build_log(
        side=0, maker_asset_id=0, taker_asset_id=1,
        maker_amount=1, taker_amount=0,
    )
    d = decode_order_filled(log, block_timestamp=0)
    assert d.price == Decimal(0)
