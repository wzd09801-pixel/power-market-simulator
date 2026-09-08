"""add weather quality issues and derived feature snapshots

Revision ID: 20260530_0004
Revises: 20260530_0003
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_0004"
down_revision = "20260530_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "weather_ingestion_runs",
        sa.Column("quality_status", sa.String(length=40), server_default="valid", nullable=False),
    )
    op.add_column(
        "weather_ingestion_runs",
        sa.Column("quality_issue_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("weather_records", "value", existing_type=sa.Float(), nullable=True)

    op.create_table(
        "weather_quality_issues",
        sa.Column("quality_issue_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "ingestion_run_id",
            sa.String(length=64),
            sa.ForeignKey("weather_ingestion_runs.ingestion_run_id"),
            nullable=False,
        ),
        sa.Column(
            "raw_payload_id",
            sa.String(length=64),
            sa.ForeignKey("weather_raw_payloads.raw_payload_id"),
            nullable=False,
        ),
        sa.Column(
            "weather_record_id",
            sa.String(length=64),
            sa.ForeignKey("weather_records.weather_record_id"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "location_id",
            sa.String(length=80),
            sa.ForeignKey("weather_locations.location_id"),
            nullable=False,
        ),
        sa.Column("forecast_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("variable", sa.String(length=80), nullable=True),
        sa.Column("issue_code", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_weather_quality_issues_ingestion_run_id",
        "weather_quality_issues",
        ["ingestion_run_id"],
    )
    op.create_index(
        "ix_weather_quality_issues_raw_payload_id",
        "weather_quality_issues",
        ["raw_payload_id"],
    )
    op.create_index(
        "ix_weather_quality_issues_weather_record_id",
        "weather_quality_issues",
        ["weather_record_id"],
    )
    op.create_index("ix_weather_quality_issues_provider", "weather_quality_issues", ["provider"])
    op.create_index(
        "ix_weather_quality_issues_location_id", "weather_quality_issues", ["location_id"]
    )
    op.create_index(
        "ix_weather_quality_issues_issue_code", "weather_quality_issues", ["issue_code"]
    )

    op.create_table(
        "weather_feature_snapshots",
        sa.Column("feature_snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "ingestion_run_id",
            sa.String(length=64),
            sa.ForeignKey("weather_ingestion_runs.ingestion_run_id"),
            nullable=False,
        ),
        sa.Column(
            "raw_payload_id",
            sa.String(length=64),
            sa.ForeignKey("weather_raw_payloads.raw_payload_id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "location_id",
            sa.String(length=80),
            sa.ForeignKey("weather_locations.location_id"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(length=80), nullable=False),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("features_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("missing_data_warnings_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
    )
    op.create_index(
        "ix_weather_feature_snapshots_ingestion_run_id",
        "weather_feature_snapshots",
        ["ingestion_run_id"],
    )
    op.create_index(
        "ix_weather_feature_snapshots_raw_payload_id",
        "weather_feature_snapshots",
        ["raw_payload_id"],
    )
    op.create_index(
        "ix_weather_feature_snapshots_provider", "weather_feature_snapshots", ["provider"]
    )
    op.create_index(
        "ix_weather_feature_snapshots_location_id", "weather_feature_snapshots", ["location_id"]
    )
    op.create_index(
        "ix_weather_feature_snapshots_generated_at", "weather_feature_snapshots", ["generated_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weather_feature_snapshots_generated_at", table_name="weather_feature_snapshots"
    )
    op.drop_index(
        "ix_weather_feature_snapshots_location_id", table_name="weather_feature_snapshots"
    )
    op.drop_index("ix_weather_feature_snapshots_provider", table_name="weather_feature_snapshots")
    op.drop_index(
        "ix_weather_feature_snapshots_raw_payload_id", table_name="weather_feature_snapshots"
    )
    op.drop_index(
        "ix_weather_feature_snapshots_ingestion_run_id", table_name="weather_feature_snapshots"
    )
    op.drop_table("weather_feature_snapshots")
    op.drop_index("ix_weather_quality_issues_issue_code", table_name="weather_quality_issues")
    op.drop_index("ix_weather_quality_issues_location_id", table_name="weather_quality_issues")
    op.drop_index("ix_weather_quality_issues_provider", table_name="weather_quality_issues")
    op.drop_index(
        "ix_weather_quality_issues_weather_record_id", table_name="weather_quality_issues"
    )
    op.drop_index("ix_weather_quality_issues_raw_payload_id", table_name="weather_quality_issues")
    op.drop_index("ix_weather_quality_issues_ingestion_run_id", table_name="weather_quality_issues")
    op.drop_table("weather_quality_issues")
    op.execute("DELETE FROM weather_records WHERE value IS NULL")
    op.alter_column("weather_records", "value", existing_type=sa.Float(), nullable=False)
    op.drop_column("weather_ingestion_runs", "quality_issue_count")
    op.drop_column("weather_ingestion_runs", "quality_status")
