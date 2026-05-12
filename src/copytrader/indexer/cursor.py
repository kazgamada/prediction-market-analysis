"""Cursor management for backfill / stream progress.

Two invariants (T6, T9 prevention):
  * `advance(name, new)` only moves forward. Updates use GREATEST so a stale
    write never regresses progress.
  * `ensure_floor(name, floor)` snaps the cursor to `floor` if the existing
    cursor is older. Used at boot to skip pre-window history.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from copytrader.db.engine import get_session
from copytrader.db.models import Cursor


def get(name: str) -> int | None:
    with get_session() as s:
        row = s.get(Cursor, name)
        return row.last_block if row else None


def advance(name: str, new_block: int, block_ts: datetime | None = None) -> int:
    """Monotonic upsert. Returns the resulting last_block.

    Uses INSERT ... ON CONFLICT with GREATEST so two racing writers cannot
    regress the cursor (T6 prevention).
    """
    with get_session() as s:
        return _advance_in_session(s, name, new_block, block_ts)


def _advance_in_session(
    s: Session, name: str, new_block: int, block_ts: datetime | None
) -> int:
    stmt = pg_insert(Cursor).values(
        name=name, last_block=new_block, last_block_at=block_ts,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Cursor.name],
        set_={
            "last_block": text("GREATEST(cursors.last_block, EXCLUDED.last_block)"),
            "last_block_at": text(
                "CASE WHEN cursors.last_block >= EXCLUDED.last_block "
                "THEN cursors.last_block_at ELSE EXCLUDED.last_block_at END"
            ),
            "updated_at": text("now()"),
        },
    )
    s.execute(stmt)
    s.flush()
    return s.get(Cursor, name).last_block


def ensure_floor(name: str, floor_block: int) -> int:
    """If the cursor is below `floor_block`, snap it up to `floor_block`.

    Used at indexer boot: rather than scanning years of history, the cursor
    is fast-forwarded to `head - window_days` and stream/backfill take it
    from there (T9 prevention).
    """
    with get_session() as s:
        row = s.get(Cursor, name)
        if row is None:
            return _advance_in_session(s, name, floor_block, datetime.now(UTC))
        if row.last_block < floor_block:
            return _advance_in_session(s, name, floor_block, datetime.now(UTC))
        return row.last_block
