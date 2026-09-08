"""add workstation job execution

Revision ID: 20260602_0013
Revises: 20260602_0012
Create Date: 2026-06-02 18:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260602_0013"
down_revision = "20260602_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("available_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE workflow_runs SET available_at = started_at WHERE available_at IS NULL")
    op.alter_column("workflow_runs", "available_at", nullable=False)
    op.add_column(
        "workflow_runs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("workflow_runs", sa.Column("worker_id", sa.String(length=120), nullable=True))
    op.add_column(
        "workflow_runs",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_workflow_runs_available_at", "workflow_runs", ["available_at"])
    op.create_index("ix_workflow_runs_lease_expires_at", "workflow_runs", ["lease_expires_at"])

    op.add_column(
        "weather_locations",
        sa.Column(
            "collection_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "weather_locations",
        sa.Column(
            "verification_status",
            sa.String(length=60),
            server_default="manual_input",
            nullable=False,
        ),
    )
    op.add_column("weather_locations", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "weather_locations",
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
    )
    op.execute(
        """
        INSERT INTO weather_locations (
            location_id, name, latitude, longitude, timezone, data_mode,
            collection_enabled, verification_status, source_url, notes
        ) VALUES (
            'demo_hydro_a_reference',
            'Demo Hydro A public reference point',
            30.0,
            110.0,
            'Asia/Shanghai',
            'public_derived',
            true,
            'unverified_analysis_input',
            'https://api.open-meteo.com/v1/forecast',
            'Public reference point for personal research. Coordinates are not verified '
            'station sensors or internal operational data.'
        )
        ON CONFLICT (location_id) DO UPDATE SET
            collection_enabled = EXCLUDED.collection_enabled,
            verification_status = EXCLUDED.verification_status,
            source_url = EXCLUDED.source_url,
            notes = EXCLUDED.notes
        """
    )


def downgrade() -> None:
    op.drop_column("weather_locations", "notes")
    op.drop_column("weather_locations", "source_url")
    op.drop_column("weather_locations", "verification_status")
    op.drop_column("weather_locations", "collection_enabled")
    op.drop_index("ix_workflow_runs_lease_expires_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_available_at", table_name="workflow_runs")
    op.drop_column("workflow_runs", "attempt_count")
    op.drop_column("workflow_runs", "worker_id")
    op.drop_column("workflow_runs", "lease_expires_at")
    op.drop_column("workflow_runs", "claimed_at")
    op.drop_column("workflow_runs", "available_at")
