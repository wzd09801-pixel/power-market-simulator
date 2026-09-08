"""add reviewed REPORTS weekly market report parser storage

Revision ID: 20260531_0007
Revises: 20260530_0006
Create Date: 2026-05-31 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260531_0007"
down_revision = "20260530_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_raw_artifacts",
        sa.Column(
            "human_review_status",
            sa.String(length=40),
            server_default="pending_review",
            nullable=False,
        ),
    )
    op.create_table(
        "market_artifact_reviews",
        sa.Column("review_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.String(length=64),
            sa.ForeignKey("market_raw_artifacts.artifact_id"),
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
        "ix_market_artifact_reviews_artifact_id",
        "market_artifact_reviews",
        ["artifact_id"],
    )

    op.create_table(
        "market_parsing_runs",
        sa.Column("parsing_run_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.String(length=64),
            sa.ForeignKey("market_raw_artifacts.artifact_id"),
            nullable=False,
        ),
        sa.Column("parser_key", sa.String(length=120), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("observations_parsed", sa.Integer(), nullable=False),
        sa.Column("observations_inserted", sa.Integer(), nullable=False),
        sa.Column("duplicate_observations", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("quality_issue_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_market_parsing_runs_artifact_id",
        "market_parsing_runs",
        ["artifact_id"],
    )
    op.create_index(
        "ix_market_parsing_runs_parser_key",
        "market_parsing_runs",
        ["parser_key"],
    )
    op.create_index(
        "ix_market_parsing_runs_status",
        "market_parsing_runs",
        ["status"],
    )

    op.add_column(
        "market_quality_issues",
        sa.Column(
            "parsing_run_id",
            sa.String(length=64),
            sa.ForeignKey("market_parsing_runs.parsing_run_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_market_quality_issues_parsing_run_id",
        "market_quality_issues",
        ["parsing_run_id"],
    )

    op.create_table(
        "market_observations",
        sa.Column("observation_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.String(length=64),
            sa.ForeignKey("market_raw_artifacts.artifact_id"),
            nullable=False,
        ),
        sa.Column(
            "parsing_run_id",
            sa.String(length=64),
            sa.ForeignKey("market_parsing_runs.parsing_run_id"),
            nullable=False,
        ),
        sa.Column("parser_key", sa.String(length=120), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("area_scope", sa.String(length=40), nullable=False),
        sa.Column("area_code", sa.String(length=40), nullable=False),
        sa.Column("area_name", sa.String(length=80), nullable=False),
        sa.Column("market_stage", sa.String(length=40), nullable=False),
        sa.Column("participant_side", sa.String(length=40), nullable=False),
        sa.Column("metric", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("settlement_status", sa.String(length=40), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "artifact_id",
            "parser_key",
            "parser_version",
            "area_code",
            "market_stage",
            "metric",
            name="uq_market_observations_artifact_parser_dimension",
        ),
    )
    op.create_index(
        "ix_market_observations_artifact_id",
        "market_observations",
        ["artifact_id"],
    )
    op.create_index(
        "ix_market_observations_parsing_run_id",
        "market_observations",
        ["parsing_run_id"],
    )
    op.create_index(
        "ix_market_observations_area_code",
        "market_observations",
        ["area_code"],
    )
    op.create_index(
        "ix_market_observations_market_stage",
        "market_observations",
        ["market_stage"],
    )
    op.create_index(
        "ix_market_observations_metric",
        "market_observations",
        ["metric"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_observations_metric", table_name="market_observations")
    op.drop_index("ix_market_observations_market_stage", table_name="market_observations")
    op.drop_index("ix_market_observations_area_code", table_name="market_observations")
    op.drop_index("ix_market_observations_parsing_run_id", table_name="market_observations")
    op.drop_index("ix_market_observations_artifact_id", table_name="market_observations")
    op.drop_table("market_observations")
    op.drop_index(
        "ix_market_quality_issues_parsing_run_id",
        table_name="market_quality_issues",
    )
    op.drop_column("market_quality_issues", "parsing_run_id")
    op.drop_index("ix_market_parsing_runs_status", table_name="market_parsing_runs")
    op.drop_index("ix_market_parsing_runs_parser_key", table_name="market_parsing_runs")
    op.drop_index("ix_market_parsing_runs_artifact_id", table_name="market_parsing_runs")
    op.drop_table("market_parsing_runs")
    op.drop_index("ix_market_artifact_reviews_artifact_id", table_name="market_artifact_reviews")
    op.drop_table("market_artifact_reviews")
    op.drop_column("market_raw_artifacts", "human_review_status")
