"""add knowledge document reviews

Revision ID: 20260610_0016
Revises: 20260609_0015
Create Date: 2026-06-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260610_0016"
down_revision = "20260609_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_document_reviews",
        sa.Column("review_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=64),
            sa.ForeignKey("knowledge_documents.document_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_knowledge_document_reviews_document_id",
        "knowledge_document_reviews",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_document_reviews_document_id",
        table_name="knowledge_document_reviews",
    )
    op.drop_table("knowledge_document_reviews")
