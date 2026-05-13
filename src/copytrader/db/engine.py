"""DB engine + URL normalization (T17 prevention)."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from copytrader.config import settings

log = logging.getLogger(__name__)


def normalize_db_url(url: str) -> str:
    """Coerce a raw URL into one SQLAlchemy + psycopg3 will accept.

    Fly.io's `DATABASE_URL` comes back as `postgres://...`. SQLAlchemy 2 / psycopg3
    requires `postgresql+psycopg://...`. Idempotent.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = normalize_db_url(settings.database_url)
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        future=True,
    )
    return engine


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session that commits on success and rolls back on error."""
    session: Session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping() -> bool:
    """Return True if the DB is reachable."""
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("db.ping failed: %s", e)
        return False


def run_migrations() -> None:
    """Run alembic upgrade head with a postgres advisory lock.

    Called from each runtime process at boot. The lock prevents races when
    multiple processes boot simultaneously (T12 prevention). Held on a
    separate connection so it doesn't interfere with alembic's own
    transaction lifetime.

    Self-healing for revision-id collisions: when the prediction-market-
    analysis app's Postgres was carrying alembic_version from a previous
    incarnation of this repo (old `0001_init.py`), the new `0001_initial.py`
    in this rebuild collides on revision id, so alembic treats the DB as
    already-at-head and skips DDL. We detect that by checking whether a
    required table from the new schema (`jobs`) is missing despite
    alembic_version being present. If so, we drop alembic_version (and any
    old-schema tables) and let the fresh migration recreate everything.

    This wipes prediction-market-analysis trade data, which is acceptable
    pre-Phase-0 (no real data of value yet).
    """
    from alembic.config import Config
    from sqlalchemy.pool import NullPool

    from alembic import command

    url = normalize_db_url(settings.database_url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    lock_engine = create_engine(url, poolclass=NullPool)
    with lock_engine.connect() as lock_conn:
        lock_conn = lock_conn.execution_options(isolation_level="AUTOCOMMIT")
        log.info("alembic upgrade head: acquiring advisory lock")
        lock_conn.execute(text("SELECT pg_advisory_lock(8675309)"))
        try:
            _reset_stale_alembic_state(lock_conn)
            log.info("alembic upgrade head: starting")
            command.upgrade(cfg, "head")
            log.info("alembic upgrade head: ok")
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(8675309)"))
    lock_engine.dispose()


# Tables created by the new 0001_initial.py. If `jobs` is missing but
# alembic_version is present, we know prior migration history collided.
_NEW_REQUIRED_TABLE = "jobs"
_OLD_TABLES_TO_DROP = [
    "jobs", "job_logs", "rpc_dead_letters", "settings",
    "signals", "risk_events", "watchlist", "wallet_stats_daily",
    "trades", "blocks_seen", "cursors",
    # Old schema (pre-rebuild) tables — drop if present
    "positions", "orders", "wallets", "ui_state", "ranks", "replays",
]


def _reset_stale_alembic_state(conn) -> None:
    """If alembic_version exists but the new schema doesn't, wipe and retry."""
    alembic_present = conn.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar()
    jobs_present = conn.execute(
        text(f"SELECT to_regclass('public.{_NEW_REQUIRED_TABLE}')")
    ).scalar()

    if alembic_present is None:
        log.info("schema state: fresh DB (no alembic_version) — normal migrate")
        return
    if jobs_present is not None:
        log.info("schema state: already on new schema — normal migrate")
        return

    # alembic_version exists but jobs doesn't → revision-id collision.
    versions = conn.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalars().all()
    log.warning(
        "schema state: alembic_version=%s but '%s' missing; wiping public schema",
        versions, _NEW_REQUIRED_TABLE,
    )
    conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    for tbl in _OLD_TABLES_TO_DROP:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS job_status"))
    log.info("schema state: old artifacts dropped; alembic will recreate from scratch")
