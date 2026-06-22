"""app_settings / openrouter_config / ai_usage_log tables

AUDIT.md 共通機能要件（AIモデル選択・OpenRouter）に対応する3テーブルを追加する。
本スタックは Postgres RLS を使わずアプリ層 `require_admin()` でアクセス制御するため、
RLS ポリシーは作成しない（要件の意図はアプリ層で担保）。

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "openrouter_config",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=True),
        sa.Column("prompt_price_per_token", sa.Numeric(20, 10), nullable=True),
        sa.Column("completion_price_per_token", sa.Numeric(20, 10), nullable=True),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )
    # is_selected=true の行は常に高々1件（トリガーの代替）
    op.create_index(
        "openrouter_config_selected_uq",
        "openrouter_config",
        ["is_selected"],
        unique=True,
        postgresql_where=sa.text("is_selected"),
    )

    op.create_table(
        "ai_usage_log",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(20, 10), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ai_usage_log_created_idx", "ai_usage_log",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ai_usage_log_created_idx", table_name="ai_usage_log")
    op.drop_table("ai_usage_log")
    op.drop_index("openrouter_config_selected_uq", table_name="openrouter_config")
    op.drop_table("openrouter_config")
    op.drop_table("app_settings")
