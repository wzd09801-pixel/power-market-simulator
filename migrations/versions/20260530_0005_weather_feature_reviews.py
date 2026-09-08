"""add weather feature review workflow

Revision ID: 20260530_0005
Revises: 20260530_0004
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_0005"
down_revision = "20260530_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "weather_feature_snapshots",
        sa.Column("forecast_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_weather_feature_snapshots_forecast_start",
        "weather_feature_snapshots",
        ["forecast_start"],
    )
    op.add_column(
        "weather_feature_snapshots",
        sa.Column(
            "human_review_status",
            sa.String(length=40),
            server_default="pending_review",
            nullable=False,
        ),
    )
    op.create_table(
        "weather_feature_reviews",
        sa.Column("review_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "feature_snapshot_id",
            sa.String(length=64),
            sa.ForeignKey("weather_feature_snapshots.feature_snapshot_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=120), server_default="local_operator", nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_weather_feature_reviews_feature_snapshot_id",
        "weather_feature_reviews",
        ["feature_snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weather_feature_reviews_feature_snapshot_id",
        table_name="weather_feature_reviews",
    )
    op.drop_table("weather_feature_reviews")
    op.drop_column("weather_feature_snapshots", "human_review_status")
    op.drop_index(
        "ix_weather_feature_snapshots_forecast_start",
        table_name="weather_feature_snapshots",
    )
    op.drop_column("weather_feature_snapshots", "forecast_start")
