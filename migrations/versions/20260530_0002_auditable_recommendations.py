"""add auditable recommendation snapshots and reviews

Revision ID: 20260530_0002
Revises: 20260529_0001
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_0002"
down_revision = "20260529_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("asset_id", sa.String(length=80), nullable=False),
        sa.Column("scenario_id", sa.String(length=120), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("inputs_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_feature_snapshots_trade_date", "feature_snapshots", ["trade_date"])
    op.create_index("ix_feature_snapshots_scenario_id", "feature_snapshots", ["scenario_id"])

    op.add_column(
        "recommendation_runs",
        sa.Column("input_snapshot_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        INSERT INTO feature_snapshots (
            snapshot_id,
            created_at,
            trade_date,
            asset_id,
            scenario_id,
            data_mode,
            inputs_json,
            evidence_json
        )
        SELECT
            'legacy_' || md5(rec_id),
            created_at,
            trade_date,
            asset_id,
            scenario_id,
            data_mode,
            json_build_object('legacy_recommendation_id', rec_id),
            '[]'::json
        FROM recommendation_runs
        """
    )
    op.execute(
        """
        UPDATE recommendation_runs
        SET input_snapshot_id = 'legacy_' || md5(rec_id)
        WHERE input_snapshot_id IS NULL
        """
    )
    op.alter_column("recommendation_runs", "input_snapshot_id", nullable=False)
    op.create_foreign_key(
        "fk_recommendation_runs_input_snapshot_id",
        "recommendation_runs",
        "feature_snapshots",
        ["input_snapshot_id"],
        ["snapshot_id"],
    )
    op.create_index(
        "ix_recommendation_runs_input_snapshot_id",
        "recommendation_runs",
        ["input_snapshot_id"],
    )
    op.execute(
        """
        UPDATE recommendation_runs
        SET review_status = 'pending_review'
        WHERE review_status = 'pending'
        """
    )
    op.alter_column(
        "recommendation_runs",
        "review_status",
        server_default="pending_review",
    )

    op.create_table(
        "recommendation_reviews",
        sa.Column("review_id", sa.String(length=64), primary_key=True),
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
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_recommendation_reviews_recommendation_id",
        "recommendation_reviews",
        ["recommendation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_reviews_recommendation_id",
        table_name="recommendation_reviews",
    )
    op.drop_table("recommendation_reviews")
    op.drop_index("ix_recommendation_runs_input_snapshot_id", table_name="recommendation_runs")
    op.drop_constraint(
        "fk_recommendation_runs_input_snapshot_id",
        "recommendation_runs",
        type_="foreignkey",
    )
    op.drop_column("recommendation_runs", "input_snapshot_id")
    op.drop_index("ix_feature_snapshots_scenario_id", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_trade_date", table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
