"""add recommendation decision feedback loop

Revision ID: 20260609_0015
Revises: 20260603_0014
Create Date: 2026-06-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260609_0015"
down_revision = "20260603_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_decisions",
        sa.Column("decision_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.String(length=64),
            sa.ForeignKey("recommendation_runs.rec_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="local_operator"),
        sa.Column("decision_status", sa.String(length=40), nullable=False),
        sa.Column("selected_windows_json", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("safety_boundary_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("no_auto_trading", sa.Boolean(), nullable=False),
        sa.Column("audit_snapshot_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_recommendation_decisions_recommendation_id",
        "recommendation_decisions",
        ["recommendation_id"],
    )

    op.create_table(
        "recommendation_decision_feedback",
        sa.Column("feedback_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "decision_id",
            sa.String(length=64),
            sa.ForeignKey("recommendation_decisions.decision_id"),
            nullable=False,
        ),
        sa.Column(
            "recommendation_id",
            sa.String(length=64),
            sa.ForeignKey("recommendation_runs.rec_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="local_operator"),
        sa.Column("outcome_status", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "data_mode",
            sa.String(length=40),
            nullable=False,
            server_default="user_uploaded",
        ),
    )
    op.create_index(
        "ix_recommendation_decision_feedback_decision_id",
        "recommendation_decision_feedback",
        ["decision_id"],
    )
    op.create_index(
        "ix_recommendation_decision_feedback_recommendation_id",
        "recommendation_decision_feedback",
        ["recommendation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_decision_feedback_recommendation_id",
        table_name="recommendation_decision_feedback",
    )
    op.drop_index(
        "ix_recommendation_decision_feedback_decision_id",
        table_name="recommendation_decision_feedback",
    )
    op.drop_table("recommendation_decision_feedback")
    op.drop_index(
        "ix_recommendation_decisions_recommendation_id",
        table_name="recommendation_decisions",
    )
    op.drop_table("recommendation_decisions")
