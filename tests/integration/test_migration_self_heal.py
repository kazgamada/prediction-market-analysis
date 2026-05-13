"""Self-healing migration + legacy-data carry-over.

Two scenarios are pinned:

  1. alembic_version exists (carrying a stamp from a prior repo) but the
     new `jobs` table is missing → run_migrations() clears alembic_version
     rows so alembic re-runs 0001_initial.py.
  2. Legacy `trade` table is present with rows → after the new schema is
     created, those rows are copied into the new `trades` table with the
     appropriate type conversions (hex string → bytea, side text → int,
     token_id text → numeric).
"""
from __future__ import annotations

from sqlalchemy import text

# DDL for the legacy 0001_init.py schema, just enough to seed for testing.
_LEGACY_TRADE_DDL = """
CREATE TABLE IF NOT EXISTS trade (
    id              BIGSERIAL PRIMARY KEY,
    tx_hash         VARCHAR(66) NOT NULL,
    log_index       INTEGER NOT NULL,
    block_number    BIGINT NOT NULL,
    block_timestamp TIMESTAMPTZ,
    exchange        VARCHAR(16) NOT NULL,
    order_hash      VARCHAR(66) NOT NULL,
    maker           VARCHAR(42) NOT NULL,
    taker           VARCHAR(42) NOT NULL,
    maker_asset_id  VARCHAR(80) NOT NULL,
    taker_asset_id  VARCHAR(80) NOT NULL,
    maker_amount    NUMERIC(40, 0) NOT NULL,
    taker_amount    NUMERIC(40, 0) NOT NULL,
    fee             NUMERIC(40, 0) DEFAULT 0,
    token_id        VARCHAR(80) NOT NULL,
    side            VARCHAR(4) NOT NULL,
    price           NUMERIC(20, 8) NOT NULL,
    size            NUMERIC(20, 6) NOT NULL,
    notional_usd    NUMERIC(20, 6) NOT NULL,
    UNIQUE (tx_hash, log_index)
);
"""


def test_clear_stale_alembic_when_jobs_missing(fresh_db) -> None:
    """alembic_version present + jobs missing -> alembic_version is cleared
    so the next run actually creates the new tables."""
    from copytrader.db.engine import get_engine, run_migrations
    eng = get_engine()

    # Setup: simulate stale state from prior repo
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS job_logs CASCADE"))
        c.execute(text("DROP TABLE IF EXISTS jobs CASCADE"))
        # alembic_version still says '0001'
        ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver == "0001"
        assert c.execute(text("SELECT to_regclass('public.jobs')")).scalar() is None

    # Run self-heal
    run_migrations()

    # Verify: jobs exists, alembic_version is back at '0001'
    with eng.begin() as c:
        assert c.execute(text("SELECT to_regclass('public.jobs')")).scalar() is not None
        ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver == "0001"


def test_legacy_trade_data_is_carried_over(fresh_db) -> None:
    """When legacy `trade` rows exist and `trades` is empty, carry-over
    copies the rows with proper type conversions."""
    from copytrader.db.engine import get_engine, run_migrations
    eng = get_engine()

    # Drop new schema, recreate legacy table, seed 2 rows
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS job_logs CASCADE"))
        c.execute(text("DROP TABLE IF EXISTS jobs CASCADE"))
        c.execute(text("DROP TABLE IF EXISTS trades CASCADE"))
        c.execute(text(_LEGACY_TRADE_DDL))
        c.execute(text("""
            INSERT INTO trade (tx_hash, log_index, block_number, block_timestamp,
                exchange, order_hash, maker, taker,
                maker_asset_id, taker_asset_id, maker_amount, taker_amount,
                token_id, side, price, size, notional_usd)
            VALUES
              ('0x' || repeat('aa', 32), 0, 1000, now(), 'ctf',
               '0x' || repeat('bb', 32), '0x' || repeat('11', 20),
               '0x' || repeat('22', 20),
               '0', '12345', 5000000, 10000000,
               '12345', 'BUY', 0.50, 10, 5),
              ('0x' || repeat('cc', 32), 1, 1001, now(), 'neg_risk',
               '0x' || repeat('dd', 32), '0x' || repeat('33', 20),
               '0x' || repeat('44', 20),
               '98765', '0', 20000000, 12000000,
               '98765', 'SELL', 0.60, 20, 12)
        """))

    # Self-heal: clear alembic, re-run, then carry data
    run_migrations()

    with eng.begin() as c:
        # New table exists and has the legacy rows
        count = c.execute(text("SELECT count(*) FROM trades")).scalar()
        assert count == 2, f"expected 2 carried rows, got {count}"

        # Verify type conversions
        rows = list(c.execute(text("""
            SELECT encode(tx_hash, 'hex'), side, token_id,
                   encode(maker, 'hex'), encode(taker, 'hex'),
                   price, size_shares, size_usdc
            FROM trades ORDER BY log_index
        """)))
        # Row 1: BUY -> side=0
        assert rows[0][0] == "aa" * 32
        assert rows[0][1] == 0  # BUY
        assert int(rows[0][2]) == 12345
        assert rows[0][3] == "11" * 20
        assert rows[0][5] == 0.50
        # Row 2: SELL -> side=1
        assert rows[1][1] == 1  # SELL
        assert int(rows[1][2]) == 98765

        # Legacy table is preserved
        legacy_count = c.execute(text("SELECT count(*) FROM trade")).scalar()
        assert legacy_count == 2, "legacy table should not be dropped"


def test_carry_over_skipped_when_trades_already_populated(fresh_db) -> None:
    """If trades already has data, carry-over must NOT overwrite it."""
    from copytrader.db.engine import get_engine, run_migrations
    eng = get_engine()

    # Healthy DB; insert one real trade row first
    with eng.begin() as c:
        c.execute(text("""
            INSERT INTO trades (tx_hash, log_index, block_number, ts, exchange,
                order_hash, maker, taker, side, maker_asset_id, taker_asset_id,
                maker_amount_filled, taker_amount_filled,
                token_id, price, size_shares, size_usdc)
            VALUES (:tx, 0, 1, now(), 'ctf', :oh, :m, :tk, 0,
                    0, 1, 1, 1, 1, 0.99, 1, 0.99)
        """), {"tx": b"\xfe" * 32, "oh": b"\xff" * 32,
               "m": b"\xee" * 20, "tk": b"\xdd" * 20})
        # Create legacy with a different row
        c.execute(text(_LEGACY_TRADE_DDL))
        c.execute(text("""
            INSERT INTO trade (tx_hash, log_index, block_number, block_timestamp,
                exchange, order_hash, maker, taker,
                maker_asset_id, taker_asset_id, maker_amount, taker_amount,
                token_id, side, price, size, notional_usd)
            VALUES ('0x' || repeat('aa', 32), 0, 1000, now(), 'ctf',
                    '0x' || repeat('bb', 32), '0x' || repeat('11', 20),
                    '0x' || repeat('22', 20),
                    '0', '12345', 5000000, 10000000,
                    '12345', 'BUY', 0.50, 10, 5)
        """))

    run_migrations()

    with eng.begin() as c:
        # The 0.99 row survives; legacy row is NOT inserted.
        rows = list(c.execute(text("SELECT price FROM trades ORDER BY price")))
        assert len(rows) == 1, "should still have 1 row, legacy carry-over skipped"
        assert float(rows[0][0]) == 0.99


def test_no_reset_on_healthy_db_preserves_data(fresh_db) -> None:
    """A healthy DB with rows in trades must not have its data touched."""
    from copytrader.db.engine import get_engine, run_migrations
    eng = get_engine()
    with eng.begin() as c:
        c.execute(text("""
            INSERT INTO trades (tx_hash, log_index, block_number, ts, exchange,
                order_hash, maker, taker, side, maker_asset_id, taker_asset_id,
                maker_amount_filled, taker_amount_filled,
                token_id, price, size_shares, size_usdc)
            VALUES (:tx, 0, 1, now(), 'ctf', :oh, :m, :tk, 0,
                    0, 1, 1, 1, 1, 0.5, 1, 0.5)
        """), {"tx": b"\x01" * 32, "oh": b"\x02" * 32,
               "m": b"\x03" * 20, "tk": b"\x04" * 20})

    run_migrations()

    with eng.begin() as c:
        n = c.execute(text("SELECT count(*) FROM trades")).scalar()
        assert n == 1, "healthy DB row must survive a no-op migrate"
