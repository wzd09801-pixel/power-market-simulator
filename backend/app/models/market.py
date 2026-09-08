from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class MarketDataSource(Base):
    __tablename__ = "market_data_sources"

    source_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    operator_name: Mapped[str] = mapped_column(String(160))
    official_url: Mapped[str] = mapped_column(Text)
    market_scope: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text)
    data_mode: Mapped[str] = mapped_column(String(40))
    trust_tier: Mapped[str] = mapped_column(String(40), default="candidate")
    attribution_text: Mapped[str] = mapped_column(Text, default="")
    collection_permission_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketSourceEndpoint(Base):
    __tablename__ = "market_source_endpoints"

    endpoint_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("market_data_sources.source_id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    canonical_url: Mapped[str] = mapped_column(Text)
    endpoint_kind: Mapped[str] = mapped_column(String(60))
    allowed_domains_json: Mapped[list[str]] = mapped_column(JSON)
    visibility_scope: Mapped[str] = mapped_column(String(60))
    access_mode: Mapped[str] = mapped_column(String(60))
    lifecycle_status: Mapped[str] = mapped_column(String(60), index=True)
    content_formats_json: Mapped[list[str]] = mapped_column(JSON)
    data_granularity: Mapped[str] = mapped_column(String(120))
    adapter_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parser_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    health_check_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_submission_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    collection_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    health_probe_not_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cadence: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketRawArtifact(Base):
    __tablename__ = "market_raw_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "content_sha256",
            name="uq_market_raw_artifacts_source_hash",
        ),
    )

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("market_data_sources.source_id"), index=True)
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("market_source_endpoints.endpoint_id"), index=True
    )
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    media_type: Mapped[str] = mapped_column(String(80))
    storage_backend: Mapped[str] = mapped_column(String(40))
    inline_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_length: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingestion_method: Mapped[str] = mapped_column(String(40))
    transport_security_status: Mapped[str] = mapped_column(String(40))
    human_review_status: Mapped[str] = mapped_column(String(40), default="pending_review")
    data_mode: Mapped[str] = mapped_column(String(40))


class MarketIngestionRun(Base):
    __tablename__ = "market_ingestion_runs"

    ingestion_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("market_data_sources.source_id"), index=True)
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("market_source_endpoints.endpoint_id"), index=True
    )
    trigger_mode: Mapped[str] = mapped_column(String(40))
    adapter_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    adapter_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), index=True)
    items_received: Mapped[int] = mapped_column(Integer)
    items_inserted: Mapped[int] = mapped_column(Integer)
    duplicate_items: Mapped[int] = mapped_column(Integer)
    rejected_items: Mapped[int] = mapped_column(Integer)
    quality_status: Mapped[str] = mapped_column(String(40))
    quality_issue_count: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketIngestionRunItem(Base):
    __tablename__ = "market_ingestion_run_items"

    ingestion_run_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ingestion_run_id: Mapped[str] = mapped_column(
        ForeignKey("market_ingestion_runs.ingestion_run_id"), index=True
    )
    artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_raw_artifacts.artifact_id"), nullable=True, index=True
    )
    source_url: Mapped[str] = mapped_column(Text)
    item_status: Mapped[str] = mapped_column(String(40), index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketQualityIssue(Base):
    __tablename__ = "market_quality_issues"

    quality_issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("market_data_sources.source_id"), index=True)
    endpoint_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_source_endpoints.endpoint_id"), nullable=True, index=True
    )
    ingestion_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_ingestion_runs.ingestion_run_id"), nullable=True, index=True
    )
    ingestion_run_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_ingestion_run_items.ingestion_run_item_id"),
        nullable=True,
        index=True,
    )
    parsing_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_parsing_runs.parsing_run_id"), nullable=True, index=True
    )
    endpoint_health_check_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_endpoint_health_checks.endpoint_health_check_id"),
        nullable=True,
        index=True,
    )
    artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_raw_artifacts.artifact_id"), nullable=True, index=True
    )
    issue_scope: Mapped[str] = mapped_column(String(40))
    issue_code: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict[str, object]] = mapped_column(JSON)
    data_mode: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketEndpointHealthCheck(Base):
    __tablename__ = "market_endpoint_health_checks"

    endpoint_health_check_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("market_source_endpoints.endpoint_id"), index=True
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    probe_url: Mapped[str] = mapped_column(Text)
    probe_method: Mapped[str] = mapped_column(String(20))
    health_status: Mapped[str] = mapped_column(String(40), index=True)
    dns_status: Mapped[str] = mapped_column(String(40))
    tcp_status: Mapped[str] = mapped_column(String(40))
    tls_status: Mapped[str] = mapped_column(String(40))
    http_status: Mapped[str] = mapped_column(String(40))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_addresses_json: Mapped[list[str]] = mapped_column(JSON)
    connected_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    redirect_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(40))


class MarketArtifactReview(Base):
    __tablename__ = "market_artifact_reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("market_raw_artifacts.artifact_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(120), default="local_operator")
    review_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)


class MarketParsingRun(Base):
    __tablename__ = "market_parsing_runs"

    parsing_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("market_raw_artifacts.artifact_id"), index=True
    )
    parser_key: Mapped[str] = mapped_column(String(120), index=True)
    parser_version: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), index=True)
    observations_parsed: Mapped[int] = mapped_column(Integer)
    observations_inserted: Mapped[int] = mapped_column(Integer)
    duplicate_observations: Mapped[int] = mapped_column(Integer)
    quality_status: Mapped[str] = mapped_column(String(40))
    quality_issue_count: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketObservation(Base):
    __tablename__ = "market_observations"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "parser_key",
            "parser_version",
            "area_code",
            "market_stage",
            "metric",
            name="uq_market_observations_artifact_parser_dimension",
        ),
    )

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("market_raw_artifacts.artifact_id"), index=True
    )
    parsing_run_id: Mapped[str] = mapped_column(
        ForeignKey("market_parsing_runs.parsing_run_id"), index=True
    )
    parser_key: Mapped[str] = mapped_column(String(120))
    parser_version: Mapped[str] = mapped_column(String(80))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    area_scope: Mapped[str] = mapped_column(String(40))
    area_code: Mapped[str] = mapped_column(String(40), index=True)
    area_name: Mapped[str] = mapped_column(String(80))
    market_stage: Mapped[str] = mapped_column(String(40), index=True)
    participant_side: Mapped[str] = mapped_column(String(40))
    metric: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit: Mapped[str] = mapped_column(String(40))
    settlement_status: Mapped[str] = mapped_column(String(40))
    data_mode: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
