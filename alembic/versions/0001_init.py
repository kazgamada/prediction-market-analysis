"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wallet",
        sa.Column("address", sa.String(42), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("n_trades", sa.Integer, server_default="0"),
        sa.Column("total_volume_usd", sa.Numeric(20, 6), server_default="0"),
        sa.Column("realized_pnl_usd", sa.Numeric(20, 6), server_default="0"),
        sa.Column("score", sa.Numeric(20, 6)),
        sa.Column("watchlisted", sa.Boolean, server_default=sa.false(), index=True),
        sa.Column("notes", sa.Text),
    )

    op.create_table(
        "trade",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("log_index", sa.Integer, nullable=False),
        sa.Column("block_number", sa.BigInteger, nullable=False),
        sa.Column("block_timestamp", sa.DateTime(timezone=True)),
        sa.Column("exchange", sa.String(16), nullable=False),
        sa.Column("order_hash", sa.String(66), nullable=False),
        sa.Column("maker", sa.String(42), nullable=False),
        sa.Column("taker", sa.String(42), nullable=False),
        sa.Column("maker_asset_id", sa.String(80), nullable=False),
        sa.Column("taker_asset_id", sa.String(80), nullable=False),
        sa.Column("maker_amount", sa.Numeric(40, 0), nullable=False),
        sa.Column("taker_amount", sa.Numeric(40, 0), nullable=False),
        sa.Column("fee", sa.Numeric(40, 0), server_default="0"),
        sa.Column("token_id", sa.String(80), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("size", sa.Numeric(20, 6), nullable=False),
        sa.Column("notional_usd", sa.Numeric(20, 6), nullable=False),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_trade_tx_log"),
    )
    op.create_index("ix_trade_maker_block", "trade", ["maker", "block_number"])
    op.create_index("ix_trade_taker_block", "trade", ["taker", "block_number"])
    op.create_index("ix_trade_token_block", "trade", ["token_id", "block_number"])
    op.create_index("ix_trade_block_ts", "trade", ["block_number"])

    op.create_table(
        "market",
        sa.Column("condition_id", sa.String(66), primary_key=True),
        sa.Column("question", sa.Text),
        sa.Column("slug", sa.String(255), index=True),
        sa.Column("outcomes_json", sa.Text),
        sa.Column("clob_token_ids_json", sa.Text),
        sa.Column("outcome_prices_json", sa.Text),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean, server_default=sa.false()),
        sa.Column("closed", sa.Boolean, server_default=sa.false()),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "token_index",
        sa.Column("token_id", sa.String(80), primary_key=True),
        sa.Column("condition_id", sa.String(66), nullable=False, index=True),
        sa.Column("outcome_index", sa.Integer, nullable=False),
    )

    op.create_table(
        "ingest_cursor",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("block_number", sa.BigInteger),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "signal",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_wallet", sa.String(42), nullable=False, index=True),
        sa.Column("source_trade_id", sa.BigInteger, sa.ForeignKey("trade.id")),
        sa.Column("token_id", sa.String(80), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("source_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("source_size", sa.Numeric(20, 6), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_signal_detected", "signal", ["detected_at"])

    op.create_table(
        "order",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.BigInteger, sa.ForeignKey("signal.id")),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("clob_order_id", sa.String(80)),
        sa.Column("token_id", sa.String(80), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("size", sa.Numeric(20, 6), nullable=False),
        sa.Column("limit_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("filled_size", sa.Numeric(20, 6), server_default="0"),
        sa.Column("avg_fill_price", sa.Numeric(20, 8)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text),
    )

    op.create_table(
        "position",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("token_id", sa.String(80), nullable=False, index=True),
        sa.Column("size", sa.Numeric(20, 6), server_default="0"),
        sa.Column("avg_entry_price", sa.Numeric(20, 8)),
        sa.Column("realized_pnl", sa.Numeric(20, 6), server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "risk_event",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("halted", sa.Boolean, server_default=sa.false()),
    )


def downgrade() -> None:
    for tbl in [
        "risk_event",
        "position",
        "order",
        "signal",
        "ingest_cursor",
        "token_index",
        "market",
        "trade",
        "wallet",
    ]:
        op.drop_table(tbl)
