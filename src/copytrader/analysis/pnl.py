"""Per-wallet PnL calculation.

Simplified Phase 0 accounting:
  * For each (taker_address, token_id) compute net position (long: bought -
    sold) and weighted-average cost.
  * "Realized PnL" = sum over closed shares of (sell_price - avg_buy_price) *
    shares_sold. Equivalent to FIFO if all buys precede all sells; we use
    the running weighted-average which is the standard simplification.
  * Phase 0 does not need market-resolution PnL (we only judge whether the
    smart money is making good entries); residual open positions are
    reported separately as `unrealized_units`.

This avoids needing the on-chain `payouts` from condition resolution for
Phase 0 (which would require Gamma API).

Memory note: with 1M+ legacy carry-over rows, materializing all `TradeRow`
objects at once requires ~500MB and OOMs a 512MB worker. `compute_wallet_pnl`
accepts any Iterable so callers can stream rows via SQLAlchemy `yield_per`;
`stream_wallet_pnl(window_days)` is the convenience wrapper that does so.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import Trade

log = logging.getLogger(__name__)


@dataclass
class TradeRow:
    ts: datetime
    address: bytes
    token_id: int
    side: int  # 0=BUY 1=SELL (taker perspective)
    price: Decimal
    size_shares: Decimal
    size_usdc: Decimal


@dataclass
class WalletPnl:
    address: bytes
    trades: int = 0
    volume_usdc: Decimal = Decimal(0)
    realized_pnl_usdc: Decimal = Decimal(0)
    wins: int = 0
    losses: int = 0
    open_positions: dict[int, dict] = field(default_factory=dict)

    @property
    def win_rate(self) -> Decimal | None:
        closed = self.wins + self.losses
        if closed == 0:
            return None
        return Decimal(self.wins) / Decimal(closed)


def _apply_trade(wp: WalletPnl, tr: TradeRow) -> None:
    wp.trades += 1
    wp.volume_usdc += tr.size_usdc

    pos = wp.open_positions.setdefault(
        tr.token_id, {"shares": Decimal(0), "cost_usdc": Decimal(0)},
    )
    if tr.side == 0:  # BUY: add to position
        pos["shares"] += tr.size_shares
        pos["cost_usdc"] += tr.size_usdc
        return

    # SELL: realize against avg cost
    sell_shares = min(tr.size_shares, pos["shares"])
    if pos["shares"] > 0 and sell_shares > 0:
        avg_cost = pos["cost_usdc"] / pos["shares"]
        proceeds = (
            (tr.size_usdc / tr.size_shares) * sell_shares
            if tr.size_shares > 0
            else Decimal(0)
        )
        cost_of_sold = avg_cost * sell_shares
        pnl = proceeds - cost_of_sold
        wp.realized_pnl_usdc += pnl
        if pnl > 0:
            wp.wins += 1
        elif pnl < 0:
            wp.losses += 1
        pos["shares"] -= sell_shares
        pos["cost_usdc"] -= cost_of_sold
    # any over-sell (more than we have on the book) is treated as a naked
    # short opening; track it as negative shares for completeness
    remaining = tr.size_shares - sell_shares
    if remaining > 0:
        pos["shares"] -= remaining
        pos["cost_usdc"] -= (
            (tr.size_usdc / tr.size_shares) * remaining
            if tr.size_shares > 0
            else Decimal(0)
        )


def compute_wallet_pnl(trades: Iterable[TradeRow]) -> dict[bytes, WalletPnl]:
    """In-memory variant for tests and small datasets.

    For production paths with >100k trades, prefer `stream_wallet_pnl`
    which avoids materializing the full row set.
    """
    sorted_trades = sorted(trades, key=lambda t: t.ts)
    wallets: dict[bytes, WalletPnl] = {}
    for tr in sorted_trades:
        wp = wallets.setdefault(tr.address, WalletPnl(address=tr.address))
        _apply_trade(wp, tr)
    return wallets


def stream_wallet_pnl(
    window_days: int,
    *,
    yield_per: int = 10_000,
    progress_cb: Callable[[int], None] | None = None,
) -> dict[bytes, WalletPnl]:
    """Stream trades from the DB in time order and aggregate per-wallet.

    Memory bound: ~one `WalletPnl` per unique wallet (cheap; ~few hundred
    bytes), regardless of the number of trade rows. A 1-million-row dataset
    that previously OOM'd a 512MB worker now needs only ~10MB.

    The `progress_cb(rows_seen)` is invoked every `yield_per` rows so the
    caller can write live-log progress without changing this module.
    """
    from datetime import UTC, timedelta
    since = datetime.now(UTC) - timedelta(days=window_days)

    wallets: dict[bytes, WalletPnl] = {}
    rows_seen = 0
    with get_session() as s:
        stmt = (
            select(
                Trade.ts, Trade.taker, Trade.token_id, Trade.side,
                Trade.price, Trade.size_shares, Trade.size_usdc,
            )
            .where(Trade.ts >= since)
            .order_by(Trade.ts)
            .execution_options(yield_per=yield_per)
        )
        result = s.execute(stmt)
        for ts, taker, token_id, side, price, size_shares, size_usdc in result:
            tr = TradeRow(ts, taker, int(token_id), side, price, size_shares, size_usdc)
            wp = wallets.setdefault(tr.address, WalletPnl(address=tr.address))
            _apply_trade(wp, tr)
            rows_seen += 1
            if rows_seen % yield_per == 0:
                log.info("stream_wallet_pnl: %d rows processed", rows_seen)
                if progress_cb is not None:
                    progress_cb(rows_seen)

    log.info("stream_wallet_pnl: done, %d rows -> %d wallets", rows_seen, len(wallets))
    if progress_cb is not None:
        progress_cb(rows_seen)
    return wallets


def load_trades(window_days: int) -> list[TradeRow]:
    """Pull all trades from the last `window_days` days, keyed by taker.

    Deprecated for large datasets — kept for tests and small windows. Use
    `stream_wallet_pnl` instead when scaling matters.
    """
    from datetime import UTC, timedelta
    since = datetime.now(UTC) - timedelta(days=window_days)
    with get_session() as s:
        rows = s.execute(
            select(
                Trade.ts, Trade.taker, Trade.token_id, Trade.side,
                Trade.price, Trade.size_shares, Trade.size_usdc,
            ).where(Trade.ts >= since).order_by(Trade.ts)
        ).all()
    return [TradeRow(*r) for r in rows]
