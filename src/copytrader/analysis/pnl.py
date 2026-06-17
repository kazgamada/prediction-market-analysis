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


def apply_resolutions(wallets: dict[bytes, WalletPnl]) -> int:
    """Close out open positions using market_resolutions.

    Iterates each wallet's open_positions dict, and for any token_id whose
    market has resolved, computes the realized PnL as if the position were
    settled at payout_per_share. Mutates `wallets` in place. Returns the
    number of positions closed.

    This is the "Phase 0 → resolve-aware" upgrade: instead of only counting
    realized PnL from explicit sells (which under-counts since smart-money
    often holds to resolution), we add the implicit realization at resolve
    time so `realized_pnl_usdc` reflects the *true* edge.

    Resolutions are keyed by `condition_id` but our trades carry `token_id`.
    Polymarket's CTF: condition_id == hash(token_id back to the market). For
    Phase 0 we treat token_id as a unique key tied to a single market — i.e.
    we look up `market_resolutions WHERE condition_id = sha256(token_id)`
    via a `resolutions` mapping the caller provides.
    """
    from copytrader.db.models import MarketResolution

    # Build token_id -> (outcome, payout) mapping.
    # Phase 0 simplification: we don't yet have the token_id ↔ condition_id
    # mapping from on-chain data. Until that's wired (PR #2.5), we look up
    # by token_id stored as the condition_id integer. This works for outcome
    # tokens that share the condition_id (CTF index 1 = Yes).
    resolutions: dict[int, tuple[int, Decimal]] = {}
    with get_session() as s:
        for row in s.execute(select(MarketResolution)).scalars():
            # Treat condition_id bytes as a big-endian integer matching
            # token_id. This is a placeholder — proper mapping requires
            # gamma `clobTokenIds` (added in a follow-up).
            try:
                key = int.from_bytes(row.condition_id, "big")
            except Exception:  # noqa: BLE001
                continue
            resolutions[key] = (int(row.outcome), row.payout_per_share)

    closed = 0
    for wp in wallets.values():
        for token_id, pos in list(wp.open_positions.items()):
            if pos["shares"] <= 0:
                continue
            res = resolutions.get(int(token_id))
            if res is None:
                continue
            _outcome, payout = res
            # Long position settled at payout; cost basis comes from pos
            proceeds = payout * pos["shares"]
            cost = pos["cost_usdc"]
            pnl = proceeds - cost
            wp.realized_pnl_usdc += pnl
            if pnl > 0:
                wp.wins += 1
            elif pnl < 0:
                wp.losses += 1
            # Zero out the open position
            wp.open_positions[token_id] = {
                "shares": Decimal(0), "cost_usdc": Decimal(0),
            }
            closed += 1
    log.info("apply_resolutions: closed %d open positions via resolve PnL", closed)
    return closed


def compute_wallet_pnl_with_resolutions(window_days: int) -> dict[bytes, WalletPnl]:
    """Convenience: stream trades + apply resolutions in one call."""
    wallets = stream_wallet_pnl(window_days)
    apply_resolutions(wallets)
    return wallets


def compute_wallet_equity_curves(
    addresses: list[bytes],
    window_days: int = 30,
    points: int = 30,
) -> dict[bytes, list[float]]:
    """For each wallet address, return a daily cumulative realized-PnL series.

    Used to plot per-wallet equity curves. Memory-bounded by chunked stream.
    """
    from datetime import UTC, timedelta

    if not addresses:
        return {}
    since = datetime.now(UTC) - timedelta(days=window_days)
    addr_set = set(addresses)
    # day index -> { address -> running pnl }
    # We compute realized PnL day-by-day per wallet using the same
    # weighted-avg accounting as compute_wallet_pnl.
    per_wallet: dict[bytes, WalletPnl] = {
        a: WalletPnl(address=a) for a in addr_set
    }
    daily_pnl: dict[bytes, dict] = {a: {} for a in addr_set}

    with get_session() as s:
        stmt = (
            select(
                Trade.ts, Trade.taker, Trade.token_id, Trade.side,
                Trade.price, Trade.size_shares, Trade.size_usdc,
            )
            .where(Trade.ts >= since)
            .where(Trade.taker.in_(addr_set))
            .order_by(Trade.ts)
            .execution_options(yield_per=5000)
        )
        for ts, taker, token_id, side, price, size_shares, size_usdc in s.execute(stmt):
            if taker not in addr_set:
                continue
            tr = TradeRow(ts, taker, int(token_id), side, price,
                          size_shares, size_usdc)
            wp = per_wallet[taker]
            prev = wp.realized_pnl_usdc
            _apply_trade(wp, tr)
            delta = wp.realized_pnl_usdc - prev
            day = ts.date()
            daily_pnl[taker].setdefault(day, Decimal(0))
            daily_pnl[taker][day] += delta

    # Build dense daily series ordered by date
    from datetime import timedelta as _td
    end_day = datetime.now(UTC).date()
    days = [end_day - _td(days=i) for i in range(points - 1, -1, -1)]

    out: dict[bytes, list[float]] = {}
    for a in addresses:
        deltas = daily_pnl.get(a, {})
        cum = Decimal(0)
        series: list[float] = []
        for d in days:
            cum += deltas.get(d, Decimal(0))
            series.append(float(cum))
        out[a] = series
    return out


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
