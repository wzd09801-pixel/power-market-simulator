"""add extensible public market artifact foundation

Revision ID: 20260530_0006
Revises: 20260530_0005
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_0006"
down_revision = "20260530_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    market_data_sources = op.create_table(
        "market_data_sources",
        sa.Column("source_id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("operator_name", sa.String(length=160), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("market_scope", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.bulk_insert(
        market_data_sources,
        [
            {
                "source_id": "example_province_power_trading_portal",
                "name": "Example Province Power Trading Portal",
                "operator_name": "Example Market Exchange",
                "official_url": "https://portal.market.example.invalid/portal/",
                "market_scope": "example_province_power_market_disclosure_candidate",
                "notes": (
                    "Official Example Province portal candidate. Anonymous frontend access is "
                    "verified; API fields and historical coverage remain unverified."
                ),
                "data_mode": "public_derived",
            },
            {
                "source_id": "example_region_power_exchange_center",
                "name": "Example Regional Exchange",
                "operator_name": "Example Regional Exchange Co., Ltd.",
                "official_url": "https://reports.market.example.invalid/",
                "market_scope": "southern_regional_market_disclosure",
                "notes": (
                    "Official regional disclosure website. Do not relabel regional material "
                    "as a Example Province 96-point spot-price curve."
                ),
                "data_mode": "public_derived",
            },
            {
                "source_id": "southern_regional_spot_platform",
                "name": "Southern Regional Spot Market Platform",
                "operator_name": "Operator to be verified",
                "official_url": "https://spot.market.example.invalid/uptspot/sr/pt/",
                "market_scope": "southern_regional_spot_platform_candidate",
                "notes": (
                    "Candidate public frontend linked from the Example Regional Exchange "
                    "website. Operator, anonymous fields, and historical coverage remain "
                    "unverified."
                ),
                "data_mode": "public_derived",
            },
        ],
    )

    market_source_endpoints = op.create_table(
        "market_source_endpoints",
        sa.Column("endpoint_id", sa.String(length=80), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=80),
            sa.ForeignKey("market_data_sources.source_id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("endpoint_kind", sa.String(length=60), nullable=False),
        sa.Column("allowed_domains_json", sa.JSON(), nullable=False),
        sa.Column("visibility_scope", sa.String(length=60), nullable=False),
        sa.Column("access_mode", sa.String(length=60), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=60), nullable=False),
        sa.Column("content_formats_json", sa.JSON(), nullable=False),
        sa.Column("data_granularity", sa.String(length=120), nullable=False),
        sa.Column("adapter_key", sa.String(length=120), nullable=True),
        sa.Column("parser_key", sa.String(length=120), nullable=True),
        sa.Column("parser_version", sa.String(length=80), nullable=True),
        sa.Column(
            "collection_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("cadence", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_market_source_endpoints_source_id",
        "market_source_endpoints",
        ["source_id"],
    )
    op.create_index(
        "ix_market_source_endpoints_lifecycle_status",
        "market_source_endpoints",
        ["lifecycle_status"],
    )
    op.bulk_insert(
        market_source_endpoints,
        [
            {
                "endpoint_id": "example_province_portal_home",
                "source_id": "example_province_power_trading_portal",
                "name": "Example Province portal public frontend",
                "canonical_url": "https://portal.market.example.invalid/portal/",
                "endpoint_kind": "public_frontend",
                "allowed_domains_json": ["portal.market.example.invalid"],
                "visibility_scope": "internet_public",
                "access_mode": "anonymous_https",
                "lifecycle_status": "candidate_unverified",
                "content_formats_json": ["text/html"],
                "data_granularity": "frontend_shell_only",
                "adapter_key": None,
                "parser_key": None,
                "parser_version": None,
                "collection_enabled": False,
                "cadence": None,
                "notes": "Anonymous frontend shell verified. Structured API contract unverified.",
            },
            {
                "endpoint_id": "reports_market_research",
                "source_id": "example_region_power_exchange_center",
                "name": "REPORTS market research column",
                "canonical_url": "http://reports.market.example.invalid/news/scyj/",
                "endpoint_kind": "html_listing",
                "allowed_domains_json": ["reports.market.example.invalid"],
                "visibility_scope": "internet_public",
                "access_mode": "anonymous_http_only",
                "lifecycle_status": "blocked_tls",
                "content_formats_json": ["text/html"],
                "data_granularity": "weekly_and_monthly_regional_reports",
                "adapter_key": None,
                "parser_key": "reports_weekly_market_report",
                "parser_version": None,
                "collection_enabled": False,
                "cadence": "weekly",
                "notes": (
                    "Public HTML reports exist, but trusted HTTPS currently fails hostname "
                    "validation. Automated collection remains disabled."
                ),
            },
            {
                "endpoint_id": "southern_spot_public_frontend",
                "source_id": "southern_regional_spot_platform",
                "name": "Southern regional spot public frontend",
                "canonical_url": "https://spot.market.example.invalid/uptspot/sr/pt/",
                "endpoint_kind": "public_frontend",
                "allowed_domains_json": ["spot.market.example.invalid"],
                "visibility_scope": "unknown",
                "access_mode": "anonymous_https",
                "lifecycle_status": "candidate_unverified",
                "content_formats_json": ["text/html"],
                "data_granularity": "frontend_shell_only",
                "adapter_key": None,
                "parser_key": None,
                "parser_version": None,
                "collection_enabled": False,
                "cadence": None,
                "notes": (
                    "Anonymous frontend shell verified. Do not infer public API fields or "
                    "automate login."
                ),
            },
        ],
    )

    op.create_table(
        "market_raw_artifacts",
        sa.Column("artifact_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=80),
            sa.ForeignKey("market_data_sources.source_id"),
            nullable=False,
        ),
        sa.Column(
            "endpoint_id",
            sa.String(length=80),
            sa.ForeignKey("market_source_endpoints.endpoint_id"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("media_type", sa.String(length=80), nullable=False),
        sa.Column("storage_backend", sa.String(length=40), nullable=False),
        sa.Column("inline_text", sa.Text(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_method", sa.String(length=40), nullable=False),
        sa.Column("transport_security_status", sa.String(length=40), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.UniqueConstraint(
            "source_id",
            "content_sha256",
            name="uq_market_raw_artifacts_source_hash",
        ),
    )
    op.create_index("ix_market_raw_artifacts_source_id", "market_raw_artifacts", ["source_id"])
    op.create_index("ix_market_raw_artifacts_endpoint_id", "market_raw_artifacts", ["endpoint_id"])
    op.create_index(
        "ix_market_raw_artifacts_content_sha256",
        "market_raw_artifacts",
        ["content_sha256"],
    )
    op.create_index("ix_market_raw_artifacts_captured_at", "market_raw_artifacts", ["captured_at"])

    op.create_table(
        "market_ingestion_runs",
        sa.Column("ingestion_run_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=80),
            sa.ForeignKey("market_data_sources.source_id"),
            nullable=False,
        ),
        sa.Column(
            "endpoint_id",
            sa.String(length=80),
            sa.ForeignKey("market_source_endpoints.endpoint_id"),
            nullable=False,
        ),
        sa.Column("trigger_mode", sa.String(length=40), nullable=False),
        sa.Column("adapter_key", sa.String(length=120), nullable=True),
        sa.Column("adapter_version", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("items_received", sa.Integer(), nullable=False),
        sa.Column("items_inserted", sa.Integer(), nullable=False),
        sa.Column("duplicate_items", sa.Integer(), nullable=False),
        sa.Column("rejected_items", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("quality_issue_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_market_ingestion_runs_source_id", "market_ingestion_runs", ["source_id"])
    op.create_index(
        "ix_market_ingestion_runs_endpoint_id", "market_ingestion_runs", ["endpoint_id"]
    )
    op.create_index("ix_market_ingestion_runs_status", "market_ingestion_runs", ["status"])

    op.create_table(
        "market_ingestion_run_items",
        sa.Column("ingestion_run_item_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "ingestion_run_id",
            sa.String(length=64),
            sa.ForeignKey("market_ingestion_runs.ingestion_run_id"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.String(length=64),
            sa.ForeignKey("market_raw_artifacts.artifact_id"),
            nullable=True,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("item_status", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_market_ingestion_run_items_ingestion_run_id",
        "market_ingestion_run_items",
        ["ingestion_run_id"],
    )
    op.create_index(
        "ix_market_ingestion_run_items_artifact_id",
        "market_ingestion_run_items",
        ["artifact_id"],
    )
    op.create_index(
        "ix_market_ingestion_run_items_item_status",
        "market_ingestion_run_items",
        ["item_status"],
    )

    op.create_table(
        "market_quality_issues",
        sa.Column("quality_issue_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=80),
            sa.ForeignKey("market_data_sources.source_id"),
            nullable=False,
        ),
        sa.Column(
            "endpoint_id",
            sa.String(length=80),
            sa.ForeignKey("market_source_endpoints.endpoint_id"),
            nullable=True,
        ),
        sa.Column(
            "ingestion_run_id",
            sa.String(length=64),
            sa.ForeignKey("market_ingestion_runs.ingestion_run_id"),
            nullable=True,
        ),
        sa.Column(
            "ingestion_run_item_id",
            sa.String(length=64),
            sa.ForeignKey("market_ingestion_run_items.ingestion_run_item_id"),
            nullable=True,
        ),
        sa.Column(
            "artifact_id",
            sa.String(length=64),
            sa.ForeignKey("market_raw_artifacts.artifact_id"),
            nullable=True,
        ),
        sa.Column("issue_scope", sa.String(length=40), nullable=False),
        sa.Column("issue_code", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("data_mode", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    for column_name in [
        "source_id",
        "endpoint_id",
        "ingestion_run_id",
        "ingestion_run_item_id",
        "artifact_id",
        "issue_code",
    ]:
        op.create_index(
            f"ix_market_quality_issues_{column_name}",
            "market_quality_issues",
            [column_name],
        )

    op.create_table(
        "market_endpoint_health_checks",
        sa.Column("endpoint_health_check_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "endpoint_id",
            sa.String(length=80),
            sa.ForeignKey("market_source_endpoints.endpoint_id"),
            nullable=False,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dns_status", sa.String(length=40), nullable=False),
        sa.Column("tcp_status", sa.String(length=40), nullable=False),
        sa.Column("tls_status", sa.String(length=40), nullable=False),
        sa.Column("http_status", sa.String(length=40), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_market_endpoint_health_checks_endpoint_id",
        "market_endpoint_health_checks",
        ["endpoint_id"],
    )
    op.create_index(
        "ix_market_endpoint_health_checks_checked_at",
        "market_endpoint_health_checks",
        ["checked_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_endpoint_health_checks_checked_at",
        table_name="market_endpoint_health_checks",
    )
    op.drop_index(
        "ix_market_endpoint_health_checks_endpoint_id",
        table_name="market_endpoint_health_checks",
    )
    op.drop_table("market_endpoint_health_checks")
    for column_name in [
        "issue_code",
        "artifact_id",
        "ingestion_run_item_id",
        "ingestion_run_id",
        "endpoint_id",
        "source_id",
    ]:
        op.drop_index(
            f"ix_market_quality_issues_{column_name}",
            table_name="market_quality_issues",
        )
    op.drop_table("market_quality_issues")
    op.drop_index(
        "ix_market_ingestion_run_items_item_status",
        table_name="market_ingestion_run_items",
    )
    op.drop_index(
        "ix_market_ingestion_run_items_artifact_id",
        table_name="market_ingestion_run_items",
    )
    op.drop_index(
        "ix_market_ingestion_run_items_ingestion_run_id",
        table_name="market_ingestion_run_items",
    )
    op.drop_table("market_ingestion_run_items")
    op.drop_index("ix_market_ingestion_runs_status", table_name="market_ingestion_runs")
    op.drop_index("ix_market_ingestion_runs_endpoint_id", table_name="market_ingestion_runs")
    op.drop_index("ix_market_ingestion_runs_source_id", table_name="market_ingestion_runs")
    op.drop_table("market_ingestion_runs")
    op.drop_index("ix_market_raw_artifacts_captured_at", table_name="market_raw_artifacts")
    op.drop_index("ix_market_raw_artifacts_content_sha256", table_name="market_raw_artifacts")
    op.drop_index("ix_market_raw_artifacts_endpoint_id", table_name="market_raw_artifacts")
    op.drop_index("ix_market_raw_artifacts_source_id", table_name="market_raw_artifacts")
    op.drop_table("market_raw_artifacts")
    op.drop_index(
        "ix_market_source_endpoints_lifecycle_status",
        table_name="market_source_endpoints",
    )
    op.drop_index("ix_market_source_endpoints_source_id", table_name="market_source_endpoints")
    op.drop_table("market_source_endpoints")
    op.drop_table("market_data_sources")
