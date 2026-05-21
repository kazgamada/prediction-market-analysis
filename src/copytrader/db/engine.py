"""DB engine + URL normalization (T17 prevention)."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

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

    Self-healing for revision-id collisions: when the production Postgres
    carries `alembic_version` from a previous incarnation of this repo (old
    `0001_init.py`), the new `0001_initial.py` collides on revision id so
    alembic treats the DB as already-at-head and skips DDL. We handle that
    by clearing `alembic_version` rows (not dropping the table) so alembic
    re-runs migrations. The old tables (`trade`, `wallet`, `market`, etc.)
    are NOT dropped — table names don't collide with the new schema
    (`trades`, `wallet_stats_daily`, ...), so they coexist as legacy.

    Data carry-over: after the new tables are created, `_copy_legacy_data`
    moves rows from legacy `trade` → new `trades` with type conversion
    (hex strings → bytea, etc). User's past indexed data is preserved.
    """
    from alembic.config import Config
    from sqlalchemy.pool import NullPool

    from alembic import command

    url = normalize_db_url(settings.database_url)
    _repo_root = Path(__file__).parents[3]
    cfg = Config(str(_repo_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    lock_engine = create_engine(url, poolclass=NullPool)
    with lock_engine.connect() as lock_conn:
        lock_conn = lock_conn.execution_options(isolation_level="AUTOCOMMIT")
        log.info("alembic upgrade head: acquiring advisory lock")
        lock_conn.execute(text("SELECT pg_advisory_lock(8675309)"))
        try:
            _clear_stale_alembic_state(lock_conn)
            log.info("alembic upgrade head: starting")
            command.upgrade(cfg, "head")
            log.info("alembic upgrade head: ok")
            _copy_legacy_data(lock_conn, lock_engine)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(8675309)"))
    lock_engine.dispose()


def _clear_stale_alembic_state(conn) -> None:
    """If alembic_version exists but the new `jobs` table doesn't, the prod
    DB is carrying a stamp from a prior repo incarnation that collides on
    revision id. Clear the alembic_version rows (keep the table) so the
    next alembic.upgrade re-runs migrations. Old (non-colliding) tables
    are left in place — data carry-over happens after migrations.
    """
    alembic_present = conn.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar()
    jobs_present = conn.execute(
        text("SELECT to_regclass('public.jobs')")
    ).scalar()

    if alembic_present is None or jobs_present is not None:
        return

    versions = list(conn.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalars())
    log.warning(
        "schema state: alembic_version=%s but 'jobs' missing; "
        "clearing alembic_version so the new 0001_initial.py runs. "
        "Old tables (trade, wallet, etc.) are kept and will be copied later.",
        versions,
    )
    conn.execute(text("DELETE FROM alembic_version"))
    # Drop new-schema tables that may have been left behind by a partial
    # earlier run, plus the enum (so the IF-NOT-EXISTS guard in 0001 has
    # a clean slate). Anything not in this list (= old-schema tables) is
    # preserved for carry-over.
    for tbl in ("jobs", "job_logs", "rpc_dead_letters", "settings",
                "signals", "risk_events", "watchlist",
                "wallet_stats_daily", "trades", "blocks_seen", "cursors"):
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS job_status"))


def _copy_legacy_data(conn, engine: Engine) -> None:
    """Carry rows from legacy `trade` → new `trades` with type conversion.

    Old columns were strings (`tx_hash VARCHAR(66)`, `side VARCHAR(4)`,
    `token_id VARCHAR(80)`) and a synthetic `id BIGSERIAL` PK. The new
    table uses bytea for hashes, SMALLINT for side, NUMERIC(78,0) for
    token_id, and a composite (tx_hash, log_index) PK.

    Only runs when the legacy table exists and the new table is empty.
    Idempotent: ON CONFLICT DO NOTHING.
    """
    legacy = conn.execute(text("SELECT to_regclass('public.trade')")).scalar()
    target = conn.execute(text("SELECT to_regclass('public.trades')")).scalar()
    if legacy is None or target is None:
        return

    legacy_n = conn.execute(text("SELECT count(*) FROM trade")).scalar() or 0
    if legacy_n == 0:
        return

    new_n = conn.execute(text("SELECT count(*) FROM trades")).scalar() or 0
    if new_n > 0:
        log.info("carry-over: trades already has %d rows; skipping", new_n)
        return

    log.info("carry-over: copying %d rows from legacy 'trade' -> 'trades'", legacy_n)
    # Run the INSERT in its own transactional connection so a failure is fully
    # rolled back (the autocommit conn used for the advisory lock cannot roll back).
    with engine.begin() as txn:
        txn.execute(text("""
            INSERT INTO trades (
                tx_hash, log_index, block_number, ts, exchange, order_hash,
                maker, taker, side,
                maker_asset_id, taker_asset_id,
                maker_amount_filled, taker_amount_filled,
                token_id, price, size_shares, size_usdc
            )
            SELECT
                decode(REPLACE(tx_hash, '0x', ''), 'hex'),
                log_index,
                block_number,
                COALESCE(block_timestamp, NOW()),
                COALESCE(exchange, 'ctf'),
                decode(REPLACE(order_hash, '0x', ''), 'hex'),
                decode(REPLACE(maker, '0x', ''), 'hex'),
                decode(REPLACE(taker, '0x', ''), 'hex'),
                CASE WHEN LOWER(side) = 'buy' THEN 0 ELSE 1 END,
                COALESCE(maker_asset_id::numeric, 0),
                COALESCE(taker_asset_id::numeric, 0),
                maker_amount,
                taker_amount,
                COALESCE(token_id::numeric, 0),
                price,
                size,
                notional_usd
            FROM trade
            ON CONFLICT (tx_hash, log_index) DO NOTHING
        """))
        final_n = txn.execute(text("SELECT count(*) FROM trades")).scalar() or 0
    log.info("carry-over complete: %d rows now in 'trades'", final_n)
