"""Replay backtest: simulate copying a target wallet with N-second delay.

Model
-----
For each trade that the target wallet executed (as maker or taker), assume our
bot detected it `delay_seconds` after `block_timestamp` and placed a market
order in the same direction. The fill price is the price of the next on-chain
trade in that token at or after the detection time, plus a configurable slippage.

PnL accounting per (wallet, token):
    cost basis (USDC out) updated on copy-BUYs
    realized PnL on copy-SELLs against running average entry
    open positions are marked to the last observed trade price for that token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import text

from copytrader.db import session_scope

log = logging.getLogger(__name__)


@dataclass
class ReplayParams:
    wallets: list[str]
    since: datetime
    until: datetime | None = None
    delay_seconds: int = 60
    copy_size_usd: float = 50.0  # USD per signal
    slippage_bps: int = 50  # 0.5%
    skip_short_lived_tokens: bool = True


@dataclass
class WalletReplayResult:
    address: str
    n_signals: int
    n_filled: int
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    total_pnl_usd: float
    gross_volume_usd: float
    win_rate: float
    n_winning_closes: int
    n_losing_closes: int


@dataclass
class _Position:
    size: Decimal = Decimal(0)  # tokens (positive long)
    avg_entry: Decimal = Decimal(0)
    realized: Decimal = Decimal(0)
    n_winning: int = 0
    n_losing: int = 0

    def buy(self, size: Decimal, price: Decimal) -> None:
        new_size = self.size + size
        if new_size > 0:
            self.avg_entry = ((self.avg_entry * self.size) + (price * size)) / new_size
        self.size = new_size

    def sell(self, size: Decimal, price: Decimal) -> None:
        sell_size = min(size, self.size)
        if sell_size > 0:
            pnl = (price - self.avg_entry) * sell_size
            self.realized += pnl
            self.size -= sell_size
            if pnl > 0:
                self.n_winning += 1
            elif pnl < 0:
                self.n_losing += 1


_REPLAY_SQL = text(
    """
    SELECT
        src.id            AS src_id,
        src.block_timestamp AS src_ts,
        src.token_id      AS token_id,
        src.maker         AS maker,
        src.taker         AS taker,
        src.maker_asset_id AS maker_asset,
        src.price         AS src_price,
        src.size          AS src_size,
        fill.price        AS fill_price,
        fill.block_timestamp AS fill_ts,
        last_mark.price   AS last_mark_price
    FROM trade src
    LEFT JOIN LATERAL (
        SELECT price, block_timestamp
        FROM trade f
        WHERE f.token_id = src.token_id
          AND f.block_timestamp >= src.block_timestamp + (:delay_seconds || ' seconds')::interval
        ORDER BY f.block_timestamp ASC
        LIMIT 1
    ) fill ON TRUE
    LEFT JOIN LATERAL (
        SELECT price
        FROM trade lm
        WHERE lm.token_id = src.token_id
        ORDER BY lm.block_number DESC, lm.log_index DESC
        LIMIT 1
    ) last_mark ON TRUE
    WHERE (lower(src.maker) = ANY(:wallets) OR lower(src.taker) = ANY(:wallets))
      AND src.block_timestamp >= :since
      AND (:until IS NULL OR src.block_timestamp < :until)
    ORDER BY src.block_timestamp ASC, src.id ASC
    """
)


def _wallet_side(row, wallet: str) -> str | None:
    """From `wallet`'s perspective, was this trade a BUY or SELL?"""
    is_maker = row.maker.lower() == wallet
    is_taker = row.taker.lower() == wallet
    if not (is_maker or is_taker):
        return None
    maker_provides_usdc = str(row.maker_asset) == "0"
    if maker_provides_usdc:
        # maker buys, taker sells
        return "BUY" if is_maker else "SELL"
    else:
        return "SELL" if is_maker else "BUY"


def replay(params: ReplayParams) -> list[WalletReplayResult]:
    wallets_lower = [w.lower() for w in params.wallets]
    if not wallets_lower:
        return []

    with session_scope() as session:
        rows = session.execute(
            _REPLAY_SQL,
            {
                "wallets": wallets_lower,
                "since": params.since,
                "until": params.until,
                "delay_seconds": params.delay_seconds,
            },
        ).all()

    # Aggregate per wallet
    state: dict[str, dict[str, _Position]] = {w: {} for w in wallets_lower}
    last_marks: dict[str, dict[str, Decimal]] = {w: {} for w in wallets_lower}
    counters: dict[str, dict[str, int]] = {
        w: {"signals": 0, "filled": 0, "gross": 0} for w in wallets_lower
    }
    gross_volume: dict[str, Decimal] = {w: Decimal(0) for w in wallets_lower}
    slip_factor = Decimal(params.slippage_bps) / Decimal(10000)
    copy_size_usd = Decimal(str(params.copy_size_usd))

    for row in rows:
        for w in wallets_lower:
            side = _wallet_side(row, w)
            if side is None:
                continue
            counters[w]["signals"] += 1
            if row.fill_price is None:
                continue
            fill_price = Decimal(str(row.fill_price))
            if side == "BUY":
                fill_price = fill_price * (Decimal(1) + slip_factor)
            else:
                fill_price = fill_price * (Decimal(1) - slip_factor)
            fill_price = max(min(fill_price, Decimal("0.999999")), Decimal("0.000001"))
            tokens = (copy_size_usd / fill_price).quantize(Decimal("0.000001"))

            pos = state[w].setdefault(row.token_id, _Position())
            if side == "BUY":
                pos.buy(tokens, fill_price)
            else:
                pos.sell(tokens, fill_price)

            counters[w]["filled"] += 1
            gross_volume[w] += copy_size_usd
            if row.last_mark_price is not None:
                last_marks[w][row.token_id] = Decimal(str(row.last_mark_price))

    # Build results
    results: list[WalletReplayResult] = []
    for w in wallets_lower:
        realized = Decimal(0)
        unrealized = Decimal(0)
        n_win = 0
        n_lose = 0
        for tid, pos in state[w].items():
            realized += pos.realized
            n_win += pos.n_winning
            n_lose += pos.n_losing
            if pos.size != 0:
                mark = last_marks[w].get(tid, pos.avg_entry)
                unrealized += (mark - pos.avg_entry) * pos.size
        n_closes = n_win + n_lose
        win_rate = (n_win / n_closes) if n_closes else 0.0
        results.append(
            WalletReplayResult(
                address=w,
                n_signals=counters[w]["signals"],
                n_filled=counters[w]["filled"],
                realized_pnl_usd=float(realized),
                unrealized_pnl_usd=float(unrealized),
                total_pnl_usd=float(realized + unrealized),
                gross_volume_usd=float(gross_volume[w]),
                win_rate=win_rate,
                n_winning_closes=n_win,
                n_losing_closes=n_lose,
            )
        )
    results.sort(key=lambda r: r.total_pnl_usd, reverse=True)
    return results


def replay_with_delays(
    wallets: Iterable[str],
    delays_seconds: list[int],
    window_days: int = 30,
    copy_size_usd: float = 50.0,
    slippage_bps: int = 50,
) -> dict[int, list[WalletReplayResult]]:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    out = {}
    wallets = list(wallets)
    for d in delays_seconds:
        log.info("replay delay=%ss", d)
        out[d] = replay(
            ReplayParams(
                wallets=wallets,
                since=since,
                delay_seconds=d,
                copy_size_usd=copy_size_usd,
                slippage_bps=slippage_bps,
            )
        )
    return out
