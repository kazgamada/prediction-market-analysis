"""Replay: simulate copying top-N wallets with N second delay.

For each smart-money trade, simulate placing the same side trade `delay`
seconds later at the next available trade price for the same token. The
"next available trade" is taken from the trades table (any taker, same
token, ts >= signal_ts + delay).

Slippage model (simple): copy executes at the median fill price within
[signal_ts + delay, signal_ts + delay + delay_window] where delay_window
defaults to the same value as delay.

PnL: realized via the same weighted-average accounting as analysis.pnl.

Phase 0 wants this in absolute USDC and ROI; we report both.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from copytrader.analysis.pnl import TradeRow, compute_wallet_pnl
from copytrader.db.engine import get_session
from copytrader.db.models import Trade


@dataclass
class ReplayResult:
    delay_seconds: int
    copy_usd_per_trade: Decimal
    signals_total: int
    signals_executed: int
    signals_unfilled: int  # no next-trade reference price found
    realized_pnl_usdc: Decimal
    invested_usdc: Decimal
    roi_pct: Decimal | None


def _fetch_window_trades(window_days: int) -> list[TradeRow]:
    from datetime import UTC
    since = datetime.now(UTC) - timedelta(days=window_days)
    with get_session() as s:
        rows = s.execute(
            select(
                Trade.ts, Trade.taker, Trade.token_id, Trade.side,
                Trade.price, Trade.size_shares, Trade.size_usdc,
            ).where(Trade.ts >= since).order_by(Trade.ts)
        ).all()
    return [TradeRow(*r) for r in rows]


def _next_reference_price(
    trades: list[TradeRow], idx: int, token_id: int, after_ts: datetime
) -> Decimal | None:
    """Find the next trade for `token_id` with ts >= after_ts and return its price."""
    n = len(trades)
    for j in range(idx, n):
        t = trades[j]
        if t.ts < after_ts:
            continue
        if t.token_id == token_id:
            return t.price
    return None


def replay_copytrade(
    *,
    window_days: int,
    top_wallets: Iterable[str],  # hex addresses 0x...
    delay_seconds: int,
    copy_usd_per_trade: float = 50.0,
) -> ReplayResult:
    trades = _fetch_window_trades(window_days)
    wallet_set = {bytes.fromhex(a[2:].lower()) for a in top_wallets}
    copy_usd = Decimal(str(copy_usd_per_trade))

    # Build the synthetic trades list for the copier.
    copier_trades: list[TradeRow] = []
    signals_total = 0
    signals_executed = 0
    signals_unfilled = 0

    copier_addr = b"\x99" * 20

    for i, signal in enumerate(trades):
        if signal.address not in wallet_set:
            continue
        signals_total += 1
        target_ts = signal.ts + timedelta(seconds=delay_seconds)
        ref_price = _next_reference_price(trades, i + 1, signal.token_id, target_ts)
        if ref_price is None or ref_price <= 0:
            signals_unfilled += 1
            continue
        signals_executed += 1
        size_shares = copy_usd / ref_price
        copier_trades.append(TradeRow(
            ts=target_ts,
            address=copier_addr,
            token_id=signal.token_id,
            side=signal.side,
            price=ref_price,
            size_shares=size_shares,
            size_usdc=copy_usd,
        ))

    wallets = compute_wallet_pnl(copier_trades)
    wp = wallets.get(copier_addr)
    realized = wp.realized_pnl_usdc if wp else Decimal(0)
    invested = copy_usd * Decimal(signals_executed)
    roi = (realized / invested * Decimal(100)) if invested > 0 else None
    return ReplayResult(
        delay_seconds=delay_seconds,
        copy_usd_per_trade=copy_usd,
        signals_total=signals_total,
        signals_executed=signals_executed,
        signals_unfilled=signals_unfilled,
        realized_pnl_usdc=realized,
        invested_usdc=invested,
        roi_pct=roi,
    )
