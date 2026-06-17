"""phase1: market_resolutions + execution layer + risk + scheduling + audit

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-21

Adds all tables required for Phase 1+ live execution per
docs/requirements/PHASE1_LIVE_EXECUTION.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Layer 1: Gamma resolutions ---
    op.create_table(
        "market_resolutions",
        sa.Column("condition_id", sa.LargeBinary(), primary_key=True),
        sa.Column("outcome", sa.SmallInteger(), nullable=False),
        sa.Column("payout_per_share", sa.Numeric(18, 6), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("market_resolutions_resolved_idx",
                    "market_resolutions", [sa.text("resolved_at DESC")])

    # --- Layer 2: Execution ---
    # Extend existing signals table with execution lifecycle columns.
    op.add_column("signals",
                  sa.Column("detected_at", sa.DateTime(timezone=True)))
    op.add_column("signals",
                  sa.Column("execute_after", sa.DateTime(timezone=True)))
    op.add_column("signals",
                  sa.Column("status", sa.Text(), server_default="PENDING",
                            nullable=False))
    op.add_column("signals",
                  sa.Column("skip_reason", sa.Text()))
    op.add_column("signals",
                  sa.Column("execution_id", sa.BigInteger()))
    # Existing rows (legacy unused) get status='LEGACY' so they don't get
    # picked up by the executor.
    op.execute(
        "UPDATE signals SET status='LEGACY', "
        "detected_at=COALESCE(ts, now()), "
        "execute_after=COALESCE(ts, now()) "
        "WHERE status IS NULL OR status='PENDING'"
    )
    op.create_index(
        "signals_status_exec_idx", "signals", ["status", "execute_after"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.BigInteger(),
                  sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("clob_order_id", sa.Text()),
        sa.Column("token_id", sa.Numeric(78, 0), nullable=False),
        sa.Column("side", sa.SmallInteger(), nullable=False),
        sa.Column("size_usdc", sa.Numeric(18, 6), nullable=False),
        sa.Column("limit_price", sa.Numeric(8, 6), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("filled_size", sa.Numeric(18, 6), server_default="0"),
        sa.Column("filled_price", sa.Numeric(8, 6)),
        sa.Column("fill_time", sa.DateTime(timezone=True)),
        sa.Column("signal_to_place_ms", sa.Integer()),
        sa.Column("place_to_fill_ms", sa.Integer()),
        sa.Column("error_text", sa.Text()),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
    )
    op.create_index("executions_status_idx", "executions",
                    ["status", sa.text("placed_at DESC")])
    op.create_index("executions_signal_idx", "executions", ["signal_id"])

    op.create_table(
        "positions",
        sa.Column("token_id", sa.Numeric(78, 0), primary_key=True),
        sa.Column("market_label", sa.Text()),
        sa.Column("side", sa.SmallInteger(), nullable=False),
        sa.Column("open_size_shares", sa.Numeric(18, 6), nullable=False),
        sa.Column("open_size_usdc", sa.Numeric(18, 6), nullable=False),
        sa.Column("avg_price", sa.Numeric(8, 6), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "trade_pnl",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("execution_id", sa.BigInteger(),
                  sa.ForeignKey("executions.id"), nullable=False),
        sa.Column("token_id", sa.Numeric(78, 0), nullable=False),
        sa.Column("realized_usdc", sa.Numeric(18, 6), nullable=False),
        sa.Column("fees_usdc", sa.Numeric(18, 6), server_default="0",
                  nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("trade_pnl_ts_idx", "trade_pnl",
                    [sa.text("ts DESC")])
    op.create_index("trade_pnl_token_ts_idx", "trade_pnl",
                    ["token_id", sa.text("ts DESC")])

    # --- Layer 3: Risk ---
    op.create_table(
        "risk_evaluations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("allow_new", sa.Boolean(), nullable=False),
        sa.Column("halted_reasons", postgresql.JSONB()),
        sa.Column("warnings", postgresql.JSONB()),
        sa.Column("metrics_snapshot", postgresql.JSONB()),
    )
    op.create_index("risk_eval_ts_idx", "risk_evaluations",
                    [sa.text("ts DESC")])

    # --- Layer 4: Meta-autonomy ---
    op.create_table(
        "scheduled_jobs",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("cron_expr", sa.Text(), nullable=False),
        sa.Column("job_kind", sa.Text(), nullable=False),
        sa.Column("job_params", postgresql.JSONB(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(),
                  server_default="true", nullable=False),
    )
    op.create_index("scheduled_jobs_next_idx", "scheduled_jobs",
                    ["next_run_at", "enabled"])

    op.create_table(
        "strategy_variants",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("weight", sa.Numeric(3, 2), nullable=False),
        sa.Column("enabled", sa.Boolean(),
                  server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # --- Layer 5: Audit ---
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
    )
    op.create_index("audit_ts_idx", "audit_log", [sa.text("ts DESC")])


def downgrade() -> None:
    op.drop_index("audit_ts_idx", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("strategy_variants")
    op.drop_index("scheduled_jobs_next_idx", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
    op.drop_index("risk_eval_ts_idx", table_name="risk_evaluations")
    op.drop_table("risk_evaluations")
    op.drop_index("trade_pnl_token_ts_idx", table_name="trade_pnl")
    op.drop_index("trade_pnl_ts_idx", table_name="trade_pnl")
    op.drop_table("trade_pnl")
    op.drop_table("positions")
    op.drop_index("executions_signal_idx", table_name="executions")
    op.drop_index("executions_status_idx", table_name="executions")
    op.drop_table("executions")
    op.drop_index("signals_status_exec_idx", table_name="signals")
    op.drop_column("signals", "execution_id")
    op.drop_column("signals", "skip_reason")
    op.drop_column("signals", "status")
    op.drop_column("signals", "execute_after")
    op.drop_column("signals", "detected_at")
    op.drop_index("market_resolutions_resolved_idx",
                  table_name="market_resolutions")
    op.drop_table("market_resolutions")
