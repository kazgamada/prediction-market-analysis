"""signal de-duplication: originating trade identity on signals

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-18

Adds `tx_hash` / `log_index` (the originating OrderFilled log identity) to
`signals`, plus a partial unique index. The indexer's catchup loop and the
live WS stream can both observe the same OrderFilled log; without this, a
single source trade produced two signals -> two copy orders (double spend).
The unique index makes signal emission idempotent at the DB level, which is
race-safe across the two concurrent ingest paths.

Columns are nullable and the unique index is partial (WHERE tx_hash IS NOT
NULL) so existing rows and manually-injected signals (no source trade) are
unaffected.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("tx_hash", sa.LargeBinary(), nullable=True))
    op.add_column("signals", sa.Column("log_index", sa.Integer(), nullable=True))
    op.create_index(
        "signals_src_trade_uq",
        "signals",
        ["tx_hash", "log_index"],
        unique=True,
        postgresql_where=sa.text("tx_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("signals_src_trade_uq", table_name="signals")
    op.drop_column("signals", "log_index")
    op.drop_column("signals", "tx_hash")
