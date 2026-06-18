"""jobs.heartbeat_at for lease liveness

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-18

Adds `heartbeat_at` to `jobs`. The lease-expiry sweep measures staleness from
this beat (bumped on every log/progress write), falling back to started_at,
so a long-but-alive job is no longer falsely marked FAILED by a fixed
started_at threshold.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("jobs", "heartbeat_at")
