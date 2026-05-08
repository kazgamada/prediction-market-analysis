"""Helpers to read/write Position rows for the bot's own positions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from copytrader.db import session_scope
from copytrader.models import Position


def get_position(token_id: str, mode: str) -> Position | None:
    with session_scope() as session:
        pos = session.execute(
            select(Position).where(
                Position.token_id == token_id,
                Position.mode == mode,
                Position.closed_at.is_(None),
            )
        ).scalar_one_or_none()
        if pos is not None:
            session.expunge(pos)
        return pos


def total_exposure_usd(mode: str) -> float:
    with session_scope() as session:
        rows = session.execute(
            select(Position.size, Position.avg_entry_price).where(
                Position.mode == mode, Position.closed_at.is_(None)
            )
        ).all()
    total = Decimal(0)
    for size, avg in rows:
        if size and avg:
            total += abs(size * avg)
    return float(total)


def upsert_position(
    token_id: str,
    mode: str,
    side: str,
    size_tokens: Decimal,
    fill_price: Decimal,
) -> tuple[Position, Decimal]:
    """Apply a fill to the open position; returns (position, realized_delta)."""
    realized_delta = Decimal(0)
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        pos = session.execute(
            select(Position).where(
                Position.token_id == token_id,
                Position.mode == mode,
                Position.closed_at.is_(None),
            )
        ).scalar_one_or_none()
        if pos is None:
            pos = Position(
                mode=mode,
                token_id=token_id,
                size=Decimal(0),
                avg_entry_price=Decimal(0),
                realized_pnl=Decimal(0),
                opened_at=now,
            )
            session.add(pos)

        if side == "BUY":
            new_size = pos.size + size_tokens
            if new_size > 0:
                pos.avg_entry_price = (
                    (pos.avg_entry_price or Decimal(0)) * pos.size + fill_price * size_tokens
                ) / new_size
            pos.size = new_size
        else:  # SELL
            sell_size = min(size_tokens, pos.size)
            if sell_size > 0:
                realized_delta = (fill_price - (pos.avg_entry_price or Decimal(0))) * sell_size
                pos.realized_pnl += realized_delta
                pos.size -= sell_size
        if pos.size <= 0:
            pos.closed_at = now
        session.flush()
        session.expunge(pos)
    return pos, realized_delta
