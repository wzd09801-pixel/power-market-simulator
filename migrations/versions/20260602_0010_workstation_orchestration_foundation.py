"""add workstation orchestration foundation

Revision ID: 20260602_0010
Revises: 20260602_0009
Create Date: 2026-06-02 10:00:00.000000
"""

from __future__ import annotations

from datetime import date, timedelta

import sqlalchemy as sa
from alembic import op

revision = "20260602_0010"
down_revision = "20260602_0009"
branch_labels = None
depends_on = None

OFFICIAL_URL = "https://calendar.example.invalid/zhengce/content/202511/content_7047098.htm"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "raw_objects",
        sa.Column("raw_object_id", sa.String(length=64), primary_key=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False, unique=True),
        sa.Column("storage_backend", sa.String(length=40), nullable=False),
        sa.Column("bucket_name", sa.String(length=120), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False, unique=True),
        sa.Column("media_type", sa.String(length=160), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
    )
    op.create_index("ix_raw_objects_content_sha256", "raw_objects", ["content_sha256"])
    op.create_index("ix_raw_objects_captured_at", "raw_objects", ["captured_at"])
    op.create_table(
        "workflow_runs",
        sa.Column("workflow_run_id", sa.String(length=64), primary_key=True),
        sa.Column("workflow_key", sa.String(length=80), nullable=False),
        sa.Column("trigger_mode", sa.String(length=40), nullable=False),
        sa.Column("prefect_flow_run_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_workflow_runs_workflow_key", "workflow_runs", ["workflow_key"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_started_at", "workflow_runs", ["started_at"])
    calendar = op.create_table(
        "workday_calendar_overrides",
        sa.Column("calendar_date", sa.Date(), primary_key=True),
        sa.Column("is_workday", sa.Boolean(), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.bulk_insert(calendar, _official_2026_overrides())


def downgrade() -> None:
    op.drop_table("workday_calendar_overrides")
    op.drop_index("ix_workflow_runs_started_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_key", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_raw_objects_captured_at", table_name="raw_objects")
    op.drop_index("ix_raw_objects_content_sha256", table_name="raw_objects")
    op.drop_table("raw_objects")


def _official_2026_overrides() -> list[dict[str, object]]:
    holidays = (
        _dates("2026-01-01", "2026-01-03")
        | _dates("2026-02-15", "2026-02-23")
        | _dates("2026-04-04", "2026-04-06")
        | _dates("2026-05-01", "2026-05-05")
        | _dates("2026-06-19", "2026-06-21")
        | _dates("2026-09-25", "2026-09-27")
        | _dates("2026-10-01", "2026-10-07")
    )
    adjusted_workdays = {
        date.fromisoformat(value)
        for value in (
            "2026-01-04",
            "2026-02-14",
            "2026-02-28",
            "2026-05-09",
            "2026-09-20",
            "2026-10-10",
        )
    }
    rows = [
        {
            "calendar_date": item,
            "is_workday": False,
            "source_kind": "official_2026_holiday",
            "source_url": OFFICIAL_URL,
            "note": "Official mainland holiday override.",
        }
        for item in sorted(holidays)
    ]
    rows.extend(
        {
            "calendar_date": item,
            "is_workday": True,
            "source_kind": "official_2026_adjusted_workday",
            "source_url": OFFICIAL_URL,
            "note": "Official mainland adjusted workday.",
        }
        for item in sorted(adjusted_workdays)
    )
    return rows


def _dates(start: str, end: str) -> set[date]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    return {first + timedelta(days=offset) for offset in range((last - first).days + 1)}
