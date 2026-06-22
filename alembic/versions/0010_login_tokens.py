"""login_tokens table (magic link / password reset)

統一ログインページのマジックリンク・パスワードリセットで使うワンタイムトークン。

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("login_tokens_token_hash_idx", "login_tokens", ["token_hash"])


def downgrade() -> None:
    op.drop_index("login_tokens_token_hash_idx", table_name="login_tokens")
    op.drop_table("login_tokens")
