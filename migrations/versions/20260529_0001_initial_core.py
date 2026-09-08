"""initial core tables

Revision ID: 20260529_0001
Revises:
Create Date: 2026-05-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260529_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])

    op.create_table(
        "recommendation_runs",
        sa.Column("rec_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("asset_id", sa.String(length=80), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("scenario_id", sa.String(length=120), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("strategy_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="pending"),
    )
    op.create_index("ix_recommendation_runs_trade_date", "recommendation_runs", ["trade_date"])
    op.create_index("ix_recommendation_runs_scenario_id", "recommendation_runs", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_runs_scenario_id", table_name="recommendation_runs")
    op.drop_index("ix_recommendation_runs_trade_date", table_name="recommendation_runs")
    op.drop_table("recommendation_runs")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
