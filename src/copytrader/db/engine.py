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
    """
    from alembic.config import Config

    from alembic import command

    url = normalize_db_url(settings.database_url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    # Use a dedicated short-lived engine so we don't hold a pool slot.
    lock_engine = create_engine(url, poolclass=__import__("sqlalchemy.pool", fromlist=["NullPool"]).NullPool)
    with lock_engine.connect() as lock_conn:
        lock_conn = lock_conn.execution_options(isolation_level="AUTOCOMMIT")
        log.info("alembic upgrade head: acquiring advisory lock")
        lock_conn.execute(text("SELECT pg_advisory_lock(8675309)"))
        try:
            log.info("alembic upgrade head: starting")
            command.upgrade(cfg, "head")
            log.info("alembic upgrade head: ok")
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(8675309)"))
    lock_engine.dispose()
