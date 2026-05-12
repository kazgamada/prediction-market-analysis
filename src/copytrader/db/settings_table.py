"""Runtime-overridable settings stored in the `settings` table.

Used for contract addresses, indexer thresholds, and anything else that
should be tweakable without redeploying (requirements D6).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db.engine import get_session
from copytrader.db.models import Setting


def get(key: str, default: Any = None) -> Any:
    with get_session() as s:
        row = s.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
        if row is None:
            return default
        return row.value


def set_(key: str, value: Any) -> None:
    with get_session() as s:
        stmt = pg_insert(Setting).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Setting.key],
            set_={"value": stmt.excluded.value, "updated_at": stmt.excluded.updated_at},
        )
        s.execute(stmt)


def all_() -> dict[str, Any]:
    with get_session() as s:
        rows = s.execute(select(Setting)).scalars().all()
        return {r.key: r.value for r in rows}
