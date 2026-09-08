"""add intelligent brief api

Revision ID: 20260602_0012
Revises: 20260602_0011
Create Date: 2026-06-02 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260602_0012"
down_revision = "20260602_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_briefs",
        sa.Column("brief_id", sa.String(length=64), primary_key=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("human_review_status", sa.String(length=40), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("deterministic_facts_json", sa.JSON(), nullable=False),
        sa.Column("narrative_json", sa.JSON(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=False),
        sa.Column("missing_information_json", sa.JSON(), nullable=False),
        sa.Column("llm_used", sa.Boolean(), nullable=False),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("no_auto_trading", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_intelligence_briefs_target_date", "intelligence_briefs", ["target_date"])
    op.create_index("ix_intelligence_briefs_generated_at", "intelligence_briefs", ["generated_at"])
    op.create_table(
        "intelligence_brief_reviews",
        sa.Column("review_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "brief_id",
            sa.String(length=64),
            sa.ForeignKey("intelligence_briefs.brief_id"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_intelligence_brief_reviews_brief_id", "intelligence_brief_reviews", ["brief_id"]
    )
    op.create_table(
        "intelligence_question_runs",
        sa.Column("question_run_id", sa.String(length=64), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("analysis_mode", sa.String(length=40), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=False),
        sa.Column("missing_information_json", sa.JSON(), nullable=False),
        sa.Column("retrieved_chunk_ids_json", sa.JSON(), nullable=False),
        sa.Column("excluded_restricted_chunks", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.Column("llm_used", sa.Boolean(), nullable=False),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("intelligence_question_runs")
    op.drop_index("ix_intelligence_brief_reviews_brief_id", table_name="intelligence_brief_reviews")
    op.drop_table("intelligence_brief_reviews")
    op.drop_index("ix_intelligence_briefs_generated_at", table_name="intelligence_briefs")
    op.drop_index("ix_intelligence_briefs_target_date", table_name="intelligence_briefs")
    op.drop_table("intelligence_briefs")
