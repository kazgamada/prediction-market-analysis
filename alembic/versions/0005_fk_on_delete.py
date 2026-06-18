"""ON DELETE CASCADE on execution lineage FKs

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-18

executions.signal_id -> signals.id and trade_pnl.execution_id -> executions.id
were created without an ON DELETE rule, so deleting a signal/execution would
fail or orphan children. The lineage is signal -> execution -> trade_pnl, so
CASCADE cleans the whole chain (matches job_logs.job_id which already cascades).
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("executions_signal_id_fkey", "executions", type_="foreignkey")
    op.create_foreign_key(
        "executions_signal_id_fkey", "executions", "signals",
        ["signal_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("trade_pnl_execution_id_fkey", "trade_pnl", type_="foreignkey")
    op.create_foreign_key(
        "trade_pnl_execution_id_fkey", "trade_pnl", "executions",
        ["execution_id"], ["id"], ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("trade_pnl_execution_id_fkey", "trade_pnl", type_="foreignkey")
    op.create_foreign_key(
        "trade_pnl_execution_id_fkey", "trade_pnl", "executions",
        ["execution_id"], ["id"],
    )
    op.drop_constraint("executions_signal_id_fkey", "executions", type_="foreignkey")
    op.create_foreign_key(
        "executions_signal_id_fkey", "executions", "signals",
        ["signal_id"], ["id"],
    )
