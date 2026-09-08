"""add hydro optimization runs

Revision ID: 20260615_0017
Revises: 20260610_0016
Create Date: 2026-06-15 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260615_0017"
down_revision = "20260610_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hydro_optimization_runs",
        sa.Column("optimization_run_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("asset_id", sa.String(length=80), nullable=False),
        sa.Column("scenario_id", sa.String(length=120), nullable=False),
        sa.Column("algorithm_key", sa.String(length=80), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column("energy_budget_mwh", sa.Float(), nullable=False),
        sa.Column("min_output_mw", sa.Float(), nullable=False),
        sa.Column("max_output_mw", sa.Float(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("constraints_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("missing_data_warnings_json", sa.JSON(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.Column("no_auto_trading", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_hydro_optimization_runs_created_at",
        "hydro_optimization_runs",
        ["created_at"],
    )
    op.create_index(
        "ix_hydro_optimization_runs_trade_date",
        "hydro_optimization_runs",
        ["trade_date"],
    )
    op.create_index(
        "ix_hydro_optimization_runs_asset_id",
        "hydro_optimization_runs",
        ["asset_id"],
    )
    op.create_index(
        "ix_hydro_optimization_runs_scenario_id",
        "hydro_optimization_runs",
        ["scenario_id"],
    )
    op.create_index(
        "ix_hydro_optimization_runs_data_mode",
        "hydro_optimization_runs",
        ["data_mode"],
    )


def downgrade() -> None:
    op.drop_index("ix_hydro_optimization_runs_data_mode", table_name="hydro_optimization_runs")
    op.drop_index("ix_hydro_optimization_runs_scenario_id", table_name="hydro_optimization_runs")
    op.drop_index("ix_hydro_optimization_runs_asset_id", table_name="hydro_optimization_runs")
    op.drop_index("ix_hydro_optimization_runs_trade_date", table_name="hydro_optimization_runs")
    op.drop_index("ix_hydro_optimization_runs_created_at", table_name="hydro_optimization_runs")
    op.drop_table("hydro_optimization_runs")
