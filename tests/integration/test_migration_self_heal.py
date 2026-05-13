"""Self-healing migration: detect & recover from stale alembic_version
left over from a prior incarnation of this repo (T12 prevention reinforced).
"""
from __future__ import annotations

from sqlalchemy import text


def test_reset_when_alembic_present_but_jobs_missing(fresh_db) -> None:
    """Simulate a stale `alembic_version` from a prior repo: jobs table got
    dropped manually but alembic_version row still claims revision '0001'.
    run_migrations() must wipe that row and recreate jobs.
    """
    from copytrader.db.engine import get_engine, run_migrations
    eng = get_engine()

    # Drop jobs (and related new-schema artifacts) but leave alembic_version.
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS job_logs CASCADE"))
        c.execute(text("DROP TABLE IF EXISTS jobs CASCADE"))
        # alembic_version still says we're at '0001' — sanity check
        ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver == "0001"
        # Confirm jobs really is gone
        present = c.execute(text("SELECT to_regclass('public.jobs')")).scalar()
        assert present is None

    # Self-heal kicks in:
    run_migrations()

    with eng.begin() as c:
        present = c.execute(text("SELECT to_regclass('public.jobs')")).scalar()
        assert present is not None, "self-heal should have recreated jobs table"
        ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver == "0001"


def test_no_reset_on_healthy_db(fresh_db) -> None:
    """On a healthy DB, run_migrations() must be a no-op (no DROP)."""
    from copytrader.db.engine import get_engine, run_migrations
    from copytrader.db.models import Trade
    eng = get_engine()

    # Seed a trade row to prove it survives the migration call.
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO trades (tx_hash, log_index, block_number, ts, exchange, "
            "order_hash, maker, taker, side, maker_asset_id, taker_asset_id, "
            "maker_amount_filled, taker_amount_filled, token_id, price, "
            "size_shares, size_usdc) VALUES "
            "(:tx, 0, 1, now(), 'ctf', :oh, :m, :tk, 0, 0, 1, 1, 1, 1, 0.5, 1, 1)"
        ), {"tx": b"\x01" * 32, "oh": b"\x02" * 32,
            "m": b"\x03" * 20, "tk": b"\x04" * 20})

    run_migrations()

    with eng.begin() as c:
        count = c.execute(text("SELECT count(*) FROM trades")).scalar()
        assert count == 1, "healthy DB should not have its data wiped"
        _ = Trade  # ensure import is exercised
