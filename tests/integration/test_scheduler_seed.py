"""seed_default_schedule wires the built-in cron jobs (incl. balance_refresh)."""
from __future__ import annotations

from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import ScheduledJob
from copytrader.jobs.handlers import HANDLERS
from copytrader.jobs.scheduler import seed_default_schedule


def _names() -> set[str]:
    with get_session() as s:
        return set(s.execute(select(ScheduledJob.name)).scalars().all())


def test_seed_registers_balance_refresh(fresh_db) -> None:
    seed_default_schedule()
    names = _names()
    assert "balance_refresh" in names


def test_seed_is_idempotent(fresh_db) -> None:
    seed_default_schedule()
    first = _names()
    seed_default_schedule()
    assert _names() == first  # no duplicates / no growth


def test_every_seeded_job_has_a_handler(fresh_db) -> None:
    seed_default_schedule()
    with get_session() as s:
        kinds = set(s.execute(select(ScheduledJob.job_kind)).scalars().all())
    missing = kinds - set(HANDLERS)
    assert not missing, f"scheduled kinds without a handler: {missing}"
