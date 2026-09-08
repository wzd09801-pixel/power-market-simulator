"""add interval forecasting research foundation

Revision ID: 20260602_0009
Revises: 20260531_0008
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260602_0009"
down_revision = "20260531_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_research_datasets",
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("region_code", sa.String(length=40), nullable=False),
        sa.Column("region_name", sa.String(length=120), nullable=False),
        sa.Column("market_scope", sa.String(length=80), nullable=False),
        sa.Column("market_stage", sa.String(length=40), nullable=False),
        sa.Column("price_scope", sa.String(length=80), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("price_unit", sa.String(length=40), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("usage_scope", sa.String(length=40), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("quality_issue_count", sa.Integer(), nullable=False),
        sa.Column("normalized_point_count", sa.Integer(), nullable=False),
        sa.Column("trade_date_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
    )
    _create_indexes(
        "forecast_research_datasets",
        "region_code",
        "market_stage",
        "usage_scope",
        "imported_at",
        "quality_status",
    )
    op.create_index(
        "ix_forecast_research_datasets_content_sha256",
        "forecast_research_datasets",
        ["content_sha256"],
        unique=True,
    )

    op.create_table(
        "forecast_research_dataset_import_runs",
        sa.Column("import_run_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("submitted_point_count", sa.Integer(), nullable=False),
        sa.Column("normalized_point_count", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("quality_issue_count", sa.Integer(), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["forecast_research_datasets.dataset_id"]),
        sa.PrimaryKeyConstraint("import_run_id"),
    )
    _create_indexes(
        "forecast_research_dataset_import_runs",
        "dataset_id",
        "completed_at",
        "status",
    )

    op.create_table(
        "forecast_research_price_points",
        sa.Column("point_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("interval_index", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["forecast_research_datasets.dataset_id"]),
        sa.PrimaryKeyConstraint("point_id"),
        sa.UniqueConstraint(
            "dataset_id",
            "interval_start",
            name="uq_forecast_research_price_points_dataset_time",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "trade_date",
            "interval_index",
            name="uq_forecast_research_price_points_dataset_trade_interval",
        ),
    )
    _create_indexes("forecast_research_price_points", "dataset_id", "interval_start", "trade_date")

    op.create_table(
        "forecast_research_quality_issues",
        sa.Column("quality_issue_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("import_run_id", sa.String(length=64), nullable=True),
        sa.Column("issue_code", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["forecast_research_datasets.dataset_id"]),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["forecast_research_dataset_import_runs.import_run_id"],
        ),
        sa.PrimaryKeyConstraint("quality_issue_id"),
    )
    _create_indexes("forecast_research_quality_issues", "dataset_id", "import_run_id", "issue_code")

    op.create_table(
        "forecast_research_model_runs",
        sa.Column("model_run_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("model_key", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("feature_version", sa.String(length=80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("registry_status", sa.String(length=40), nullable=False),
        sa.Column("train_start", sa.Date(), nullable=False),
        sa.Column("train_end", sa.Date(), nullable=False),
        sa.Column("evaluation_start", sa.Date(), nullable=False),
        sa.Column("evaluation_end", sa.Date(), nullable=False),
        sa.Column("horizon_intervals", sa.Integer(), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("usage_scope", sa.String(length=40), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["forecast_research_datasets.dataset_id"]),
        sa.PrimaryKeyConstraint("model_run_id"),
    )
    _create_indexes(
        "forecast_research_model_runs",
        "dataset_id",
        "model_key",
        "completed_at",
        "status",
        "registry_status",
        "usage_scope",
    )

    op.create_table(
        "forecast_research_predictions",
        sa.Column("prediction_id", sa.String(length=64), nullable=False),
        sa.Column("model_run_id", sa.String(length=64), nullable=False),
        sa.Column("target_interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("interval_index", sa.Integer(), nullable=False),
        sa.Column("actual_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("predicted_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["model_run_id"], ["forecast_research_model_runs.model_run_id"]),
        sa.PrimaryKeyConstraint("prediction_id"),
        sa.UniqueConstraint(
            "model_run_id",
            "target_interval_start",
            name="uq_forecast_research_predictions_run_time",
        ),
    )
    _create_indexes(
        "forecast_research_predictions",
        "model_run_id",
        "target_interval_start",
        "trade_date",
    )


def downgrade() -> None:
    _drop_indexes(
        "forecast_research_predictions",
        "trade_date",
        "target_interval_start",
        "model_run_id",
    )
    op.drop_table("forecast_research_predictions")
    _drop_indexes(
        "forecast_research_model_runs",
        "usage_scope",
        "registry_status",
        "status",
        "completed_at",
        "model_key",
        "dataset_id",
    )
    op.drop_table("forecast_research_model_runs")
    _drop_indexes(
        "forecast_research_quality_issues",
        "issue_code",
        "import_run_id",
        "dataset_id",
    )
    op.drop_table("forecast_research_quality_issues")
    _drop_indexes("forecast_research_price_points", "trade_date", "interval_start", "dataset_id")
    op.drop_table("forecast_research_price_points")
    _drop_indexes(
        "forecast_research_dataset_import_runs",
        "status",
        "completed_at",
        "dataset_id",
    )
    op.drop_table("forecast_research_dataset_import_runs")
    _drop_indexes(
        "forecast_research_datasets",
        "quality_status",
        "imported_at",
        "content_sha256",
        "usage_scope",
        "market_stage",
        "region_code",
    )
    op.drop_table("forecast_research_datasets")


def _create_indexes(table_name: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])


def _drop_indexes(table_name: str, *columns: str) -> None:
    for column in columns:
        op.drop_index(f"ix_{table_name}_{column}", table_name=table_name)
