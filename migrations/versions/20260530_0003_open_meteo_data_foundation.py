"""add Open-Meteo weather data foundation

Revision ID: 20260530_0003
Revises: 20260530_0002
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_0003"
down_revision = "20260530_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weather_locations",
        sa.Column("location_id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "weather_raw_payloads",
        sa.Column("raw_payload_id", sa.String(length=64), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "location_id",
            sa.String(length=80),
            sa.ForeignKey("weather_locations.location_id"),
            nullable=False,
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_url", sa.Text(), nullable=False),
        sa.Column("request_params_json", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("quality_flag", sa.String(length=40), nullable=False),
    )
    op.create_index("ix_weather_raw_payloads_provider", "weather_raw_payloads", ["provider"])
    op.create_index("ix_weather_raw_payloads_location_id", "weather_raw_payloads", ["location_id"])

    op.create_table(
        "weather_ingestion_runs",
        sa.Column("ingestion_run_id", sa.String(length=64), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "location_id",
            sa.String(length=80),
            sa.ForeignKey("weather_locations.location_id"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("request_url", sa.Text(), nullable=False),
        sa.Column(
            "raw_payload_id",
            sa.String(length=64),
            sa.ForeignKey("weather_raw_payloads.raw_payload_id"),
            nullable=True,
        ),
        sa.Column("records_received", sa.Integer(), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("duplicate_records", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_weather_ingestion_runs_provider", "weather_ingestion_runs", ["provider"])
    op.create_index(
        "ix_weather_ingestion_runs_location_id", "weather_ingestion_runs", ["location_id"]
    )
    op.create_index("ix_weather_ingestion_runs_status", "weather_ingestion_runs", ["status"])

    op.create_table(
        "weather_records",
        sa.Column("weather_record_id", sa.String(length=64), primary_key=True),
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
        sa.Column("issue_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("variable", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("quality_flag", sa.String(length=40), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_weather_records_raw_payload_id", "weather_records", ["raw_payload_id"])
    op.create_index("ix_weather_records_provider", "weather_records", ["provider"])
    op.create_index("ix_weather_records_location_id", "weather_records", ["location_id"])
    op.create_index("ix_weather_records_issue_time", "weather_records", ["issue_time"])
    op.create_index("ix_weather_records_forecast_time", "weather_records", ["forecast_time"])
    op.create_index("ix_weather_records_variable", "weather_records", ["variable"])


def downgrade() -> None:
    op.drop_index("ix_weather_records_variable", table_name="weather_records")
    op.drop_index("ix_weather_records_forecast_time", table_name="weather_records")
    op.drop_index("ix_weather_records_issue_time", table_name="weather_records")
    op.drop_index("ix_weather_records_location_id", table_name="weather_records")
    op.drop_index("ix_weather_records_provider", table_name="weather_records")
    op.drop_index("ix_weather_records_raw_payload_id", table_name="weather_records")
    op.drop_table("weather_records")
    op.drop_index("ix_weather_ingestion_runs_status", table_name="weather_ingestion_runs")
    op.drop_index("ix_weather_ingestion_runs_location_id", table_name="weather_ingestion_runs")
    op.drop_index("ix_weather_ingestion_runs_provider", table_name="weather_ingestion_runs")
    op.drop_table("weather_ingestion_runs")
    op.drop_index("ix_weather_raw_payloads_location_id", table_name="weather_raw_payloads")
    op.drop_index("ix_weather_raw_payloads_provider", table_name="weather_raw_payloads")
    op.drop_table("weather_raw_payloads")
    op.drop_table("weather_locations")
