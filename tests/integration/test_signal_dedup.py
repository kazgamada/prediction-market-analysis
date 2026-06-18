"""Signal emission is idempotent on the source trade identity.

The indexer's catchup loop and the live WS stream can both observe the same
OrderFilled log. Before the (tx_hash, log_index) unique index, that produced
two signals -> two copy orders (double spend). These tests pin that the same
source trade now yields exactly one signal, while genuinely distinct trades
still each produce one.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from copytrader.db.engine import get_session
from copytrader.db.models import Signal, Watchlist


def _add_watchlist(addr: bytes) -> None:
    with get_session() as s:
        s.add(Watchlist(address=addr, active=True, added_at=datetime.now(UTC)))


def _record(addr: bytes, *, tx: bytes, log_index: int):
    from copytrader.execution.signal_consumer import maybe_record_signal
    return maybe_record_signal(
        address=addr,
        token_id=12345,
        side=0,
        price=Decimal("0.40"),
        size_usdc=Decimal("100"),
        trade_ts=datetime.now(UTC),
        tx_hash=tx,
        log_index=log_index,
    )


def test_same_source_trade_yields_one_signal(fresh_db) -> None:
    addr = b"\x42" * 20
    _add_watchlist(addr)
    tx = b"\xab" * 32

    first = _record(addr, tx=tx, log_index=7)
    second = _record(addr, tx=tx, log_index=7)  # duplicate observation

    assert first is not None
    assert second is None, "duplicate source trade must not create a 2nd signal"
    with get_session() as s:
        n = s.execute(select(func.count()).select_from(Signal)).scalar_one()
    assert n == 1


def test_distinct_trades_each_produce_a_signal(fresh_db) -> None:
    addr = b"\x42" * 20
    _add_watchlist(addr)

    a = _record(addr, tx=b"\xaa" * 32, log_index=0)
    b = _record(addr, tx=b"\xbb" * 32, log_index=0)
    c = _record(addr, tx=b"\xaa" * 32, log_index=1)  # same tx, different log

    assert a is not None and b is not None and c is not None
    with get_session() as s:
        n = s.execute(select(func.count()).select_from(Signal)).scalar_one()
    assert n == 3


def test_dedup_survives_concurrent_emit_path(fresh_db) -> None:
    """Simulate catchup + stream both calling the emit path for the same
    batch of trades: the second pass is fully absorbed by ON CONFLICT."""
    from copytrader.chain.decoder import DecodedTrade
    from copytrader.indexer.persist import _emit_signals_for_watchlist

    addr = b"\x42" * 20
    _add_watchlist(addr)

    trade = DecodedTrade(
        tx_hash=b"\xcd" * 32,
        log_index=3,
        block_number=1000,
        ts=datetime.now(UTC),
        exchange="ctf",
        order_hash=b"\xbb" * 32,
        maker=b"\x11" * 20,
        taker=addr,
        side=0,
        maker_asset_id=0,
        taker_asset_id=12345,
        maker_amount_filled=40_000_000,
        taker_amount_filled=100_000_000,
        token_id=12345,
        price=Decimal("0.40"),
        size_shares=Decimal("100"),
        size_usdc=Decimal("40"),
    )

    _emit_signals_for_watchlist([trade])  # catchup
    _emit_signals_for_watchlist([trade])  # stream re-observes

    with get_session() as s:
        n = s.execute(select(func.count()).select_from(Signal)).scalar_one()
    assert n == 1
