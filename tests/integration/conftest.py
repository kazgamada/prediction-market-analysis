"""Integration tests run against a real Postgres.

`copytrader_test` must exist and be reachable via env DATABASE_URL or the
default localhost:55432 used by the dev container.

Each test starts with a clean DB (TRUNCATE).
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

DEFAULT_TEST_URL = "postgresql+psycopg://copytrader:copytrader@localhost:55432/copytrader_test"


@pytest.fixture(autouse=True, scope="session")
def _set_db_url() -> None:
    if "TEST_DATABASE_URL" in os.environ:
        os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    else:
        os.environ.setdefault("DATABASE_URL", DEFAULT_TEST_URL)


@pytest.fixture
def fresh_db():  # noqa: ANN201
    # Lazy import so `_set_db_url` runs first.
    from copytrader.config import settings as cfg
    cfg.database_url = os.environ["DATABASE_URL"]

    # Reset engine singleton since DATABASE_URL changed at runtime.
    from copytrader.db import engine as engine_mod
    engine_mod.get_engine.cache_clear()
    engine_mod._session_factory.cache_clear()

    from copytrader.db.engine import get_engine, run_migrations
    from copytrader.db.models import Base

    eng = get_engine()
    # Verify reachable, else skip the whole integration suite.
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no test postgres available: {e}")

    # Drop any legacy-schema artifacts from prior tests *before* migrating
    # so the self-heal carry-over doesn't pull stale rows. (Tests that need
    # a fresh legacy schema recreate it explicitly.)
    with eng.begin() as c:
        for tbl in ("trade", "wallet", "market", "token_index",
                    "ingest_cursor", "signal", '"order"', "position",
                    "risk_event"):
            c.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))

    # Guarantee a full head schema for every test. The migration self-heal
    # tests deliberately mutate the schema (drop tables, clear
    # alembic_version), so a TRUNCATE-only fixture would cascade ERRORs into
    # later tests. run_migrations() restores head from any partial state.
    run_migrations()

    # Empty every ORM-managed table. Derived from metadata so new tables are
    # covered automatically.
    table_list = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with eng.begin() as c:
        c.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
    yield
