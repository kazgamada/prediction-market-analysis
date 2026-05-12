"""PnL computation: weighted-avg cost / win/loss bookkeeping."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from copytrader.analysis.pnl import TradeRow, compute_wallet_pnl


def _t(secs: int, addr: bytes, token: int, side: int, price: str, shares: str) -> TradeRow:
    px = Decimal(price)
    sh = Decimal(shares)
    return TradeRow(
        ts=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=secs),
        address=addr,
        token_id=token,
        side=side,
        price=px,
        size_shares=sh,
        size_usdc=px * sh,
    )


def test_buy_then_sell_profit() -> None:
    a = b"\x01" * 20
    trades = [
        _t(0, a, 1, 0, "0.40", "100"),  # buy 100 @ 0.40 -> $40 cost
        _t(1, a, 1, 1, "0.60", "100"),  # sell 100 @ 0.60 -> $60 proceeds
    ]
    wp = compute_wallet_pnl(trades)[a]
    assert wp.realized_pnl_usdc == Decimal("20")
    assert wp.wins == 1
    assert wp.losses == 0
    assert wp.trades == 2


def test_buy_then_sell_loss() -> None:
    a = b"\x02" * 20
    trades = [
        _t(0, a, 1, 0, "0.60", "100"),
        _t(1, a, 1, 1, "0.40", "100"),
    ]
    wp = compute_wallet_pnl(trades)[a]
    assert wp.realized_pnl_usdc == Decimal("-20")
    assert wp.losses == 1


def test_partial_close() -> None:
    a = b"\x03" * 20
    trades = [
        _t(0, a, 1, 0, "0.50", "200"),  # cost = $100
        _t(1, a, 1, 1, "0.60", "100"),  # sell 100 @ 0.60: avg cost = 0.50 -> pnl = $10
    ]
    wp = compute_wallet_pnl(trades)[a]
    assert wp.realized_pnl_usdc == Decimal("10")
    # 100 shares left @ avg cost 0.50
    pos = wp.open_positions[1]
    assert pos["shares"] == Decimal("100")
    assert pos["cost_usdc"] == Decimal("50")


def test_average_cost_across_two_buys() -> None:
    a = b"\x04" * 20
    trades = [
        _t(0, a, 1, 0, "0.40", "100"),  # cost $40
        _t(1, a, 1, 0, "0.60", "100"),  # cost $60, total $100, avg $0.50
        _t(2, a, 1, 1, "0.55", "200"),  # sell all @ 0.55 -> proceeds $110 -> pnl +$10
    ]
    wp = compute_wallet_pnl(trades)[a]
    assert wp.realized_pnl_usdc == Decimal("10")


def test_volume_accumulates() -> None:
    a = b"\x05" * 20
    trades = [
        _t(0, a, 1, 0, "0.5", "100"),
        _t(1, a, 2, 0, "0.5", "100"),
    ]
    wp = compute_wallet_pnl(trades)[a]
    assert wp.volume_usdc == Decimal("100")


def test_win_rate() -> None:
    a = b"\x06" * 20
    trades = [
        _t(0, a, 1, 0, "0.4", "100"), _t(1, a, 1, 1, "0.6", "100"),  # win
        _t(2, a, 2, 0, "0.4", "100"), _t(3, a, 2, 1, "0.3", "100"),  # loss
        _t(4, a, 3, 0, "0.4", "100"), _t(5, a, 3, 1, "0.5", "100"),  # win
    ]
    wp = compute_wallet_pnl(trades)[a]
    assert wp.wins == 2
    assert wp.losses == 1
    assert wp.win_rate == Decimal(2) / Decimal(3)


def test_multiple_wallets_isolated() -> None:
    a, b = b"\xaa" * 20, b"\xbb" * 20
    trades = [
        _t(0, a, 1, 0, "0.4", "100"), _t(1, a, 1, 1, "0.6", "100"),  # a: +20
        _t(2, b, 1, 0, "0.6", "100"), _t(3, b, 1, 1, "0.4", "100"),  # b: -20
    ]
    wps = compute_wallet_pnl(trades)
    assert wps[a].realized_pnl_usdc == Decimal("20")
    assert wps[b].realized_pnl_usdc == Decimal("-20")
