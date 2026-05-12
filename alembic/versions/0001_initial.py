"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-12

Single migration that creates the full schema documented in
docs/plans/IMPLEMENTATION_PLAN.md §3.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cursors",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("last_block", sa.BigInteger(), nullable=False),
        sa.Column("last_block_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "blocks_seen",
        sa.Column("block_number", sa.BigInteger(), primary_key=True),
        sa.Column("log_count", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "trades",
        sa.Column("tx_hash", sa.LargeBinary(), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),  # 'ctf' or 'neg_risk'
        sa.Column("order_hash", sa.LargeBinary(), nullable=False),
        sa.Column("maker", sa.LargeBinary(), nullable=False),
        sa.Column("taker", sa.LargeBinary(), nullable=False),
        sa.Column("side", sa.SmallInteger(), nullable=False),
        sa.Column("maker_asset_id", sa.Numeric(78, 0), nullable=False),
        sa.Column("taker_asset_id", sa.Numeric(78, 0), nullable=False),
        sa.Column("maker_amount_filled", sa.Numeric(38, 0), nullable=False),
        sa.Column("taker_amount_filled", sa.Numeric(38, 0), nullable=False),
        sa.Column("token_id", sa.Numeric(78, 0), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("size_shares", sa.Numeric(38, 18), nullable=False),
        sa.Column("size_usdc", sa.Numeric(28, 6), nullable=False),
        sa.PrimaryKeyConstraint("tx_hash", "log_index"),
    )
    op.create_index("trades_ts_idx", "trades", ["ts"])
    op.create_index("trades_block_idx", "trades", ["block_number"])
    op.create_index("trades_taker_ts_idx", "trades", ["taker", sa.text("ts DESC")])
    op.create_index("trades_token_ts_idx", "trades", ["token_id", sa.text("ts DESC")])

    op.create_table(
        "wallet_stats_daily",
        sa.Column("address", sa.LargeBinary(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("volume_usdc", sa.Numeric(28, 6), nullable=False),
        sa.Column("realized_pnl_usdc", sa.Numeric(28, 6)),
        sa.Column("win_rate", sa.Numeric(6, 4)),
        sa.PrimaryKeyConstraint("address", "date"),
    )

    op.create_table(
        "watchlist",
        sa.Column("address", sa.LargeBinary(), primary_key=True),
        sa.Column("note", sa.Text()),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("address", sa.LargeBinary(), nullable=False),
        sa.Column("token_id", sa.Numeric(78, 0), nullable=False),
        sa.Column("side", sa.SmallInteger(), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("size_usdc", sa.Numeric(28, 6), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
    )
    op.create_index("signals_ts_idx", "signals", [sa.text("ts DESC")])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("risk_events_ts_idx", "risk_events", [sa.text("ts DESC")])

    # job_status enum
    op.execute(
        "CREATE TYPE job_status AS ENUM ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')"
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED",
                name="job_status", create_type=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("error_text", sa.Text()),
        sa.Column("idempotency_key", sa.Text(), unique=True),
        sa.Column("parent_job_id", sa.BigInteger(), sa.ForeignKey("jobs.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("worker_id", sa.Text()),
    )
    op.create_index("jobs_status_idx", "jobs", ["status", "created_at"])

    op.create_table(
        "job_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.BigInteger(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("job_logs_job_ts_idx", "job_logs", ["job_id", "ts"])

    op.create_table(
        "rpc_dead_letters",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=False),
        sa.Column("retries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_retry", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "CREATE INDEX rpc_dl_pending_idx ON rpc_dead_letters (next_retry) "
        "WHERE resolved_at IS NULL"
    )

    op.create_table(
        "settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index("rpc_dl_pending_idx", table_name="rpc_dead_letters")
    op.drop_table("rpc_dead_letters")
    op.drop_index("job_logs_job_ts_idx", table_name="job_logs")
    op.drop_table("job_logs")
    op.drop_index("jobs_status_idx", table_name="jobs")
    op.drop_table("jobs")
    op.execute("DROP TYPE job_status")
    op.drop_index("risk_events_ts_idx", table_name="risk_events")
    op.drop_table("risk_events")
    op.drop_index("signals_ts_idx", table_name="signals")
    op.drop_table("signals")
    op.drop_table("watchlist")
    op.drop_table("wallet_stats_daily")
    op.drop_index("trades_token_ts_idx", table_name="trades")
    op.drop_index("trades_taker_ts_idx", table_name="trades")
    op.drop_index("trades_block_idx", table_name="trades")
    op.drop_index("trades_ts_idx", table_name="trades")
    op.drop_table("trades")
    op.drop_table("blocks_seen")
    op.drop_table("cursors")
