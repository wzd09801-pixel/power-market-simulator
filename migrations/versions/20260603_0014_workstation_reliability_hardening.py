"""harden workstation workflow reliability

Revision ID: 20260603_0014
Revises: 20260602_0013
Create Date: 2026-06-03 02:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603_0014"
down_revision = "20260602_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("schedule_identity", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("lease_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_workflow_runs_schedule_identity",
        "workflow_runs",
        ["schedule_identity"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_runs_schedule_identity", table_name="workflow_runs")
    op.drop_column("workflow_runs", "lease_token")
    op.drop_column("workflow_runs", "schedule_identity")
    op.drop_column("workflow_runs", "scheduled_for")
