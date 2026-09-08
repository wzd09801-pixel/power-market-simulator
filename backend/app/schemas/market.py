from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

SupportedManualArtifactMediaType = Literal[
    "application/json",
    "application/xml",
    "text/csv",
    "text/html",
    "text/plain",
    "text/xml",
]


class MarketDataSourceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    name: str
    operator_name: str
    official_url: str
    market_scope: str
    notes: str
    data_mode: str
    trust_tier: str
    attribution_text: str
    collection_permission_note: str


class MarketDataSourceListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketDataSourceResponse]


class MarketSourceEndpointResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_id: str
    source_id: str
    name: str
    canonical_url: str
    endpoint_kind: str
    allowed_domains: list[str]
    visibility_scope: str
    access_mode: str
    lifecycle_status: str
    content_formats: list[str]
    data_granularity: str
    adapter_key: str | None
    parser_key: str | None
    parser_version: str | None
    health_check_enabled: bool
    manual_submission_enabled: bool
    collection_enabled: bool
    health_probe_not_before: datetime | None
    cadence: str | None
    notes: str


class MarketSourceEndpointListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketSourceEndpointResponse]


class ManualMarketArtifactRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    source_url: HttpUrl
    title: str | None = Field(default=None, max_length=300)
    media_type: SupportedManualArtifactMediaType
    inline_text: str = Field(min_length=1, max_length=2_000_000)
    published_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError("Artifact title must not be blank.")
        return title

    @field_validator("inline_text")
    @classmethod
    def inline_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Artifact inline text must not be blank.")
        return value


class ManualMarketArtifactResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingestion_run_id: str
    ingestion_run_item_id: str
    artifact_id: str
    source_id: str
    endpoint_id: str
    status: str
    item_status: str
    captured_at: datetime
    content_sha256: str
    duplicate_artifact: bool
    quality_status: str
    quality_issue_count: int
    data_mode: str


class MarketRawArtifactResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    source_id: str
    endpoint_id: str
    source_url: str
    title: str | None
    media_type: str
    storage_backend: str
    inline_text: str | None
    object_key: str | None
    content_sha256: str
    byte_length: int
    published_at: datetime | None
    captured_at: datetime
    ingestion_method: str
    transport_security_status: str
    human_review_status: str
    data_mode: str


class MarketRawArtifactListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketRawArtifactResponse]


class MarketIngestionRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingestion_run_id: str
    source_id: str
    endpoint_id: str
    trigger_mode: str
    adapter_key: str | None
    adapter_version: str | None
    started_at: datetime
    completed_at: datetime
    status: str
    items_received: int
    items_inserted: int
    duplicate_items: int
    rejected_items: int
    quality_status: str
    quality_issue_count: int
    error_code: str | None
    error_message: str | None


class MarketIngestionRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketIngestionRunResponse]


class MarketQualityIssueResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    quality_issue_id: str
    source_id: str
    endpoint_id: str | None
    ingestion_run_id: str | None
    ingestion_run_item_id: str | None
    parsing_run_id: str | None
    endpoint_health_check_id: str | None
    artifact_id: str | None
    issue_scope: str
    issue_code: str
    severity: str
    message: str
    details: dict[str, object]
    data_mode: str


class MarketQualityIssueListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketQualityIssueResponse]


class MarketQualityIssueSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_count: int
    severity_counts: dict[str, int]
    issue_code_counts: dict[str, int]
    displayed_issue_count: int


class MarketEndpointHealthCheckResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_health_check_id: str
    endpoint_id: str
    checked_at: datetime
    probe_url: str
    probe_method: str
    health_status: str
    dns_status: str
    tcp_status: str
    tls_status: str
    http_status: str
    status_code: int | None
    resolved_addresses: list[str]
    connected_address: str | None
    attempt_count: int
    duration_ms: int
    redirect_location: str | None
    error_code: str | None
    error_message: str | None
    data_mode: str


class MarketEndpointHealthCheckListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketEndpointHealthCheckResponse]


MarketArtifactReviewAction = Literal["approved", "rejected", "needs_revision"]


class MarketArtifactReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_status: MarketArtifactReviewAction
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("Review note must not be blank.")
        return note


class MarketArtifactReviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    artifact_id: str
    created_at: datetime
    actor: str
    review_status: MarketArtifactReviewAction
    note: str


class MarketArtifactReviewPackageArtifactResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    source_id: str
    endpoint_id: str
    source_url: str
    title: str | None
    media_type: str
    storage_backend: str
    inline_text_available: bool
    object_key: str | None
    content_sha256: str
    byte_length: int
    published_at: datetime | None
    captured_at: datetime
    ingestion_method: str
    transport_security_status: str
    human_review_status: str
    data_mode: str


class MarketArtifactReviewPackageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_version: str
    generated_at: datetime
    artifact: MarketArtifactReviewPackageArtifactResponse
    source: MarketDataSourceResponse | None
    endpoint: MarketSourceEndpointResponse | None
    quality_issue_summary: MarketQualityIssueSummary
    quality_issues: list[MarketQualityIssueResponse]
    reviews: list[MarketArtifactReviewResponse]
    parsing_runs: list[MarketParsingRunResponse]
    no_auto_trading: bool
    recommendation_chain_isolated: bool
    network_probe_performed: bool
    fetch_performed: bool
    parse_performed: bool


class MarketParsingRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    parsing_run_id: str
    artifact_id: str
    parser_key: str
    parser_version: str
    started_at: datetime
    completed_at: datetime
    status: str
    observations_parsed: int
    observations_inserted: int
    duplicate_observations: int
    quality_status: str
    quality_issue_count: int
    error_code: str | None
    error_message: str | None


class MarketParsingRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketParsingRunResponse]


class MarketObservationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_id: str
    artifact_id: str
    parsing_run_id: str
    parser_key: str
    parser_version: str
    period_start: date
    period_end: date
    area_scope: str
    area_code: str
    area_name: str
    market_stage: str
    participant_side: str
    metric: str
    value: Decimal
    unit: str
    settlement_status: str
    data_mode: str


class MarketObservationListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MarketObservationResponse]
