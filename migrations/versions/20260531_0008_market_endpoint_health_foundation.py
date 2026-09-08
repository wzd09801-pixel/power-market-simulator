"""add auditable market endpoint health foundation

Revision ID: 20260531_0008
Revises: 20260531_0007
Create Date: 2026-05-31 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260531_0008"
down_revision = "20260531_0007"
branch_labels = None
depends_on = None

HTTPS_CANDIDATE_ENDPOINT_ID = "reports_market_research_https_candidate"


def upgrade() -> None:
    op.add_column(
        "market_source_endpoints",
        sa.Column(
            "health_check_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "market_source_endpoints",
        sa.Column(
            "manual_submission_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "market_source_endpoints",
        sa.Column("health_probe_not_before", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE market_source_endpoints
        SET health_check_enabled = true
        WHERE endpoint_id IN (
            'example_province_portal_home',
            'reports_market_research',
            'southern_spot_public_frontend'
        )
        """
    )
    op.execute(
        """
        UPDATE market_source_endpoints
        SET manual_submission_enabled = true
        WHERE endpoint_id IN (
            'example_province_portal_home',
            'reports_market_research'
        )
        """
    )

    op.add_column(
        "market_endpoint_health_checks",
        sa.Column("probe_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column("probe_method", sa.String(length=20), server_default="HEAD", nullable=False),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column("health_status", sa.String(length=40), server_default="unknown", nullable=False),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column(
            "resolved_addresses_json",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column("redirect_location", sa.Text(), nullable=True),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column("connected_address", sa.String(length=45), nullable=True),
    )
    op.add_column(
        "market_endpoint_health_checks",
        sa.Column(
            "data_mode",
            sa.String(length=40),
            server_default="public_derived",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE market_endpoint_health_checks AS checks
        SET probe_url = endpoints.canonical_url
        FROM market_source_endpoints AS endpoints
        WHERE checks.endpoint_id = endpoints.endpoint_id
          AND checks.probe_url IS NULL
        """
    )
    op.alter_column("market_endpoint_health_checks", "probe_url", nullable=False)
    op.create_index(
        "ix_market_endpoint_health_checks_health_status",
        "market_endpoint_health_checks",
        ["health_status"],
    )

    op.add_column(
        "market_quality_issues",
        sa.Column(
            "endpoint_health_check_id",
            sa.String(length=64),
            sa.ForeignKey("market_endpoint_health_checks.endpoint_health_check_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_market_quality_issues_endpoint_health_check_id",
        "market_quality_issues",
        ["endpoint_health_check_id"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO market_source_endpoints (
                endpoint_id,
                source_id,
                name,
                canonical_url,
                endpoint_kind,
                allowed_domains_json,
                visibility_scope,
                access_mode,
                lifecycle_status,
                content_formats_json,
                data_granularity,
                adapter_key,
                parser_key,
                parser_version,
                health_check_enabled,
                manual_submission_enabled,
                collection_enabled,
                health_probe_not_before,
                cadence,
                notes
            )
            VALUES (
                :endpoint_id,
                'example_region_power_exchange_center',
                'REPORTS market research HTTPS candidate',
                'https://reports.market.example.invalid/news/scyj/',
                'html_listing_https_candidate',
                '["reports.market.example.invalid"]'::json,
                'internet_public',
                'anonymous_https',
                'blocked_tls',
                '["text/html"]'::json,
                'weekly_and_monthly_regional_reports',
                NULL,
                NULL,
                NULL,
                true,
                false,
                false,
                NULL,
                'weekly',
                :notes
            )
            ON CONFLICT (endpoint_id) DO NOTHING
            """
        ).bindparams(
            endpoint_id=HTTPS_CANDIDATE_ENDPOINT_ID,
            notes=(
                "Read-only health-check candidate. Trusted HTTPS currently fails hostname "
                "validation. Automated collection remains disabled."
            ),
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE market_source_endpoints
            SET health_check_enabled = true,
                manual_submission_enabled = false,
                collection_enabled = false
            WHERE endpoint_id = :endpoint_id
            """
        ).bindparams(endpoint_id=HTTPS_CANDIDATE_ENDPOINT_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM market_source_endpoints
            WHERE endpoint_id = :endpoint_id
              AND NOT EXISTS (
                  SELECT 1
                  FROM market_raw_artifacts
                  WHERE endpoint_id = :endpoint_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM market_ingestion_runs
                  WHERE endpoint_id = :endpoint_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM market_quality_issues
                  WHERE endpoint_id = :endpoint_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM market_endpoint_health_checks
                  WHERE endpoint_id = :endpoint_id
              )
            """
        ).bindparams(endpoint_id=HTTPS_CANDIDATE_ENDPOINT_ID)
    )

    op.drop_index(
        "ix_market_quality_issues_endpoint_health_check_id",
        table_name="market_quality_issues",
    )
    op.drop_column("market_quality_issues", "endpoint_health_check_id")
    op.drop_index(
        "ix_market_endpoint_health_checks_health_status",
        table_name="market_endpoint_health_checks",
    )
    op.drop_column("market_endpoint_health_checks", "data_mode")
    op.drop_column("market_endpoint_health_checks", "connected_address")
    op.drop_column("market_endpoint_health_checks", "redirect_location")
    op.drop_column("market_endpoint_health_checks", "duration_ms")
    op.drop_column("market_endpoint_health_checks", "attempt_count")
    op.drop_column("market_endpoint_health_checks", "resolved_addresses_json")
    op.drop_column("market_endpoint_health_checks", "health_status")
    op.drop_column("market_endpoint_health_checks", "probe_method")
    op.drop_column("market_endpoint_health_checks", "probe_url")
    op.drop_column("market_source_endpoints", "health_probe_not_before")
    op.drop_column("market_source_endpoints", "manual_submission_enabled")
    op.drop_column("market_source_endpoints", "health_check_enabled")
