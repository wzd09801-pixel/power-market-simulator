"""add policy knowledge foundation

Revision ID: 20260602_0011
Revises: 20260602_0010
Create Date: 2026-06-02 11:00:00.000000
"""

# ruff: noqa: E501
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260602_0011"
down_revision = "20260602_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_data_sources",
        sa.Column("trust_tier", sa.String(length=40), server_default="candidate", nullable=False),
    )
    op.add_column(
        "market_data_sources",
        sa.Column("attribution_text", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "market_data_sources",
        sa.Column("collection_permission_note", sa.Text(), server_default="", nullable=False),
    )
    _add_sources()
    op.create_table(
        "knowledge_documents",
        sa.Column("document_id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("document_layer", sa.String(length=40), nullable=False),
        sa.Column("trust_tier", sa.String(length=40), nullable=False),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=160), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "external_processing_allowed", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "human_review_status",
            sa.String(length=40),
            server_default="pending_review",
            nullable=False,
        ),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
    )
    op.create_index(
        "ix_knowledge_documents_document_layer", "knowledge_documents", ["document_layer"]
    )
    op.create_index("ix_knowledge_documents_captured_at", "knowledge_documents", ["captured_at"])
    op.create_table(
        "knowledge_document_versions",
        sa.Column("version_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=64),
            sa.ForeignKey("knowledge_documents.document_id"),
            nullable=False,
        ),
        sa.Column(
            "raw_object_id",
            sa.String(length=64),
            sa.ForeignKey("raw_objects.raw_object_id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_key", sa.String(length=80), nullable=False),
        sa.Column("parsed_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "version_number", name="uq_knowledge_version_number"),
        sa.UniqueConstraint("document_id", "content_sha256", name="uq_knowledge_document_hash"),
    )
    op.create_index(
        "ix_knowledge_document_versions_document_id", "knowledge_document_versions", ["document_id"]
    )
    op.create_index(
        "ix_knowledge_document_versions_raw_object_id",
        "knowledge_document_versions",
        ["raw_object_id"],
    )
    op.create_index(
        "ix_knowledge_document_versions_content_sha256",
        "knowledge_document_versions",
        ["content_sha256"],
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("chunk_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(length=64),
            sa.ForeignKey("knowledge_document_versions.version_id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("section_heading", sa.String(length=300), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.UniqueConstraint("version_id", "ordinal", name="uq_knowledge_chunk_ordinal"),
    )
    op.execute(
        "ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector"
    )
    op.create_index("ix_knowledge_chunks_version_id", "knowledge_chunks", ["version_id"])
    op.create_index("ix_knowledge_chunks_content_sha256", "knowledge_chunks", ["content_sha256"])
    op.create_table(
        "knowledge_authorization_audits",
        sa.Column("authorization_audit_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=64),
            sa.ForeignKey("knowledge_documents.document_id"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("external_processing_allowed", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_knowledge_authorization_audits_document_id",
        "knowledge_authorization_audits",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_authorization_audits_document_id", table_name="knowledge_authorization_audits"
    )
    op.drop_table("knowledge_authorization_audits")
    op.drop_index("ix_knowledge_chunks_content_sha256", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_version_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(
        "ix_knowledge_document_versions_content_sha256", table_name="knowledge_document_versions"
    )
    op.drop_index(
        "ix_knowledge_document_versions_raw_object_id", table_name="knowledge_document_versions"
    )
    op.drop_index(
        "ix_knowledge_document_versions_document_id", table_name="knowledge_document_versions"
    )
    op.drop_table("knowledge_document_versions")
    op.drop_index("ix_knowledge_documents_captured_at", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_document_layer", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_column("market_data_sources", "collection_permission_note")
    op.drop_column("market_data_sources", "attribution_text")
    op.drop_column("market_data_sources", "trust_tier")


def _add_sources() -> None:
    op.execute(
        """
        INSERT INTO market_data_sources (
            source_id, name, operator_name, official_url, market_scope, notes, data_mode,
            trust_tier, attribution_text, collection_permission_note
        ) VALUES
        ('southern_energy_regulator', 'Example Energy Regulator', 'Example Energy Regulator', 'https://policy.example.invalid/', 'southern_regional_policy', 'Official policy candidate. Automated collection remains disabled pending trusted TLS validation.', 'public_derived', 'official', 'Example Energy Regulator', 'Public official material; preserve attribution and source URL.'),
        ('example_electricity_council', 'Example Electricity Council', 'Example Electricity Council', 'https://council.example.invalid/', 'national_industry_research', 'Industry research candidate. Enable collection only after adapter review.', 'public_derived', 'industry_association', 'Example Electricity Council', 'Public research candidate; preserve attribution and source URL.'),
        ('example_province_electricity_association', 'Example Electricity Association', 'Example Electricity Association', 'https://association.example.invalid/', 'example_province_industry_research', 'Local industry research candidate. Enable collection only after adapter review.', 'public_derived', 'industry_association', 'Example Electricity Association', 'Public research candidate; preserve attribution and source URL.'),
        ('institute', 'Example Research Institute', 'Example Research Institute', 'https://institute.example.invalid/', 'national_power_research', 'Manual import only: automated request currently returns HTTP 418. Do not bypass anti-automation controls.', 'public_derived', 'research_institute', 'Example Research Institute', 'Manual import only unless an allowed automated contract is verified.')
        ON CONFLICT (source_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO market_source_endpoints (
            endpoint_id, source_id, name, canonical_url, endpoint_kind,
            allowed_domains_json, visibility_scope, access_mode, lifecycle_status,
            content_formats_json, data_granularity, adapter_key, parser_key,
            parser_version, health_check_enabled, manual_submission_enabled,
            collection_enabled, health_probe_not_before, cadence, notes
        ) VALUES
        ('southern_regulator_downloads', 'southern_energy_regulator', 'Southern regulator public downloads', 'https://policy.example.invalid/hdhy/zlxz/', 'html_listing', '["policy.example.invalid"]'::json, 'internet_public', 'anonymous_https', 'blocked_tls', '["text/html","application/pdf"]'::json, 'policy_documents', NULL, NULL, NULL, true, true, false, NULL, 'every_6_hours', 'Official candidate. Keep automated collection disabled until trusted TLS access is validated.'),
        ('council_home', 'example_electricity_council', 'COUNCIL public website', 'https://council.example.invalid/', 'public_frontend', '["council.example.invalid"]'::json, 'internet_public', 'anonymous_https', 'candidate_unverified', '["text/html","application/pdf"]'::json, 'industry_research', NULL, NULL, NULL, true, true, false, NULL, 'every_6_hours', 'Public industry research candidate. Adapter contract remains unverified.'),
        ('association_home', 'example_province_electricity_association', 'ASSOCIATION public website', 'https://association.example.invalid/', 'public_frontend', '["association.example.invalid"]'::json, 'internet_public', 'anonymous_https', 'candidate_unverified', '["text/html","application/pdf"]'::json, 'example_province_industry_research', NULL, NULL, NULL, true, true, false, NULL, 'every_6_hours', 'Public local industry research candidate. Adapter contract remains unverified.'),
        ('institute_home', 'institute', 'INSTITUTE public website', 'https://institute.example.invalid/', 'manual_submission_only', '["institute.example.invalid"]'::json, 'internet_public', 'manual_submission_only', 'blocked_anti_automation', '["text/html","application/pdf"]'::json, 'power_research', NULL, NULL, NULL, false, true, false, NULL, NULL, 'Manual import only. Do not bypass HTTP 418 anti-automation controls.')
        ON CONFLICT (endpoint_id) DO NOTHING
        """
    )
