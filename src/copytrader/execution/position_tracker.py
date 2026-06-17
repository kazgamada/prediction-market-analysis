"""Reconcile executions FILLED → positions + trade_pnl.

For each newly-FILLED execution, update the matching position row using
weighted-average cost basis. If a SELL closes part of the position, compute
realized PnL = (fill_price - avg_cost) * shares_sold and INSERT a trade_pnl
row.

Called periodically by worker_main, or right after CLOB callback if we ever
get push notifications.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db.engine import get_session
from copytrader.db.models import Execution, Position, TradePnl
from copytrader.execution.clob_client import get_clob
from copytrader.execution.order_state import EXEC_FILLED, EXEC_PLACED

log = logging.getLogger("execution.position_tracker")


def _poll_fills_from_clob() -> int:
    """For each PLACED execution older than 5s, ask CLOB for status.

    Updates filled_size / filled_price / fill_time / status accordingly.
    Returns number of executions updated.
    """
    updated = 0
    clob = get_clob()
    with get_session() as s:
        placed = s.execute(
            select(Execution).where(Execution.status == EXEC_PLACED).limit(50)
        ).scalars().all()
        for ex in placed:
            if not ex.clob_order_id:
                # dry-run had no order_id; auto-mark as filled at limit for
                # paper accounting if execution_enabled=false.
                # (executor.py would already have skipped these but defensive)
                continue
            info = clob.get_order(ex.clob_order_id)
            if not info:
                continue
            status = str(info.get("status", "")).upper()
            filled_size = Decimal(str(info.get("filled_size") or 0))
            avg_price = Decimal(str(info.get("avg_price") or ex.limit_price))
            if status in ("FILLED", "MATCHED"):
                _apply_fill(ex, filled_size, avg_price)
                updated += 1
            elif status in ("CANCELLED", "EXPIRED"):
                s.execute(
                    update(Execution)
                    .where(Execution.id == ex.id)
                    .values(status="CANCELLED")
                )
                updated += 1
    return updated


def _apply_fill(ex: Execution, filled_size: Decimal, fill_price: Decimal) -> None:
    """Mark execution FILLED + update positions + compute realized PnL."""
    now = datetime.now(UTC)
    place_to_fill_ms = int((now - ex.placed_at).total_seconds() * 1000)

    with get_session() as s:
        s.execute(
            update(Execution)
            .where(Execution.id == ex.id)
            .values(
                status=EXEC_FILLED,
                filled_size=filled_size,
                filled_price=fill_price,
                fill_time=now,
                place_to_fill_ms=place_to_fill_ms,
            )
        )

        pos = s.get(Position, ex.token_id)
        size_usdc = filled_size * fill_price

        if pos is None:
            # New position
            stmt = pg_insert(Position).values(
                token_id=ex.token_id,
                market_label=None,
                side=ex.side,
                open_size_shares=filled_size,
                open_size_usdc=size_usdc,
                avg_price=fill_price,
                opened_at=now,
                updated_at=now,
            ).on_conflict_do_nothing(index_elements=[Position.token_id])
            s.execute(stmt)
        else:
            if int(ex.side) == int(pos.side):
                # Same direction: average up
                new_shares = pos.open_size_shares + filled_size
                new_usdc = pos.open_size_usdc + size_usdc
                new_avg = new_usdc / new_shares if new_shares > 0 else fill_price
                s.execute(
                    update(Position).where(Position.token_id == ex.token_id)
                    .values(
                        open_size_shares=new_shares,
                        open_size_usdc=new_usdc,
                        avg_price=new_avg,
                        updated_at=now,
                    )
                )
            else:
                # Opposite direction: realize PnL on the closed portion
                close_shares = min(filled_size, pos.open_size_shares)
                realized = (fill_price - pos.avg_price) * close_shares
                # For sells closing longs, PnL = sell - avg_cost.
                # For buys closing shorts (rare in Polymarket), flip sign.
                if int(pos.side) == 1:
                    realized = -realized
                s.add(TradePnl(
                    execution_id=ex.id,
                    token_id=ex.token_id,
                    realized_usdc=realized,
                ))
                remaining_shares = pos.open_size_shares - close_shares
                remaining_usdc = pos.open_size_usdc - (pos.avg_price * close_shares)
                if remaining_shares <= 0:
                    s.execute(
                        update(Position).where(Position.token_id == ex.token_id)
                        .values(
                            open_size_shares=Decimal(0),
                            open_size_usdc=Decimal(0),
                            updated_at=now,
                        )
                    )
                else:
                    s.execute(
                        update(Position).where(Position.token_id == ex.token_id)
                        .values(
                            open_size_shares=remaining_shares,
                            open_size_usdc=remaining_usdc,
                            updated_at=now,
                        )
                    )
    log.info(
        "fill applied: exec=%s token=%s size=%s price=%s",
        ex.id, ex.token_id, filled_size, fill_price,
    )


async def run_position_tracker(*, tick_seconds: int = 5) -> None:
    """Long-running coroutine: poll CLOB for fills every tick_seconds."""
    log.info("position_tracker: starting, tick=%ds", tick_seconds)
    while True:
        try:
            n = _poll_fills_from_clob()
            if n:
                log.info("position_tracker: %d executions updated", n)
        except Exception as e:  # noqa: BLE001
            log.exception("position_tracker tick failed: %s", e)
        await asyncio.sleep(tick_seconds)
