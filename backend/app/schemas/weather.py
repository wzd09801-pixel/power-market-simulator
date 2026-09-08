from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_OPEN_METEO_HOURLY_VARIABLES = [
    "temperature_2m",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
]
SUPPORTED_OPEN_METEO_HOURLY_VARIABLES = frozenset(DEFAULT_OPEN_METEO_HOURLY_VARIABLES)
WeatherFeatureReviewStatus = Literal["pending_review", "approved", "rejected", "needs_revision"]
WeatherFeatureReviewAction = Literal["approved", "rejected", "needs_revision"]


class OpenMeteoForecastIngestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    location_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    location_name: str = Field(min_length=1, max_length=160)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    forecast_days: int = Field(default=3, ge=1, le=16)
    hourly_variables: list[str] = Field(
        default_factory=lambda: list(DEFAULT_OPEN_METEO_HOURLY_VARIABLES),
        min_length=1,
        max_length=len(SUPPORTED_OPEN_METEO_HOURLY_VARIABLES),
    )

    @field_validator("location_name")
    @classmethod
    def location_name_must_not_be_blank(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Location name must not be blank.")
        return name

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_supported(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone must be a valid IANA timezone name.") from exc
        return value

    @field_validator("hourly_variables")
    @classmethod
    def variables_must_be_supported_and_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Hourly weather variables must be unique.")
        unsupported = sorted(set(value) - SUPPORTED_OPEN_METEO_HOURLY_VARIABLES)
        if unsupported:
            raise ValueError(f"Unsupported Open-Meteo hourly variables: {unsupported}.")
        return value


class WeatherIngestionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingestion_run_id: str
    provider: str
    location_id: str
    status: str
    started_at: datetime
    completed_at: datetime
    raw_payload_id: str
    records_received: int
    records_inserted: int
    duplicate_records: int
    quality_status: str
    quality_issue_count: int
    feature_snapshot_id: str
    data_mode: str


class WeatherRecordResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    weather_record_id: str
    raw_payload_id: str
    provider: str
    location_id: str
    issue_time: datetime
    forecast_time: datetime
    variable: str
    value: float | None
    unit: str
    data_mode: str
    quality_flag: str


class WeatherRecordListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[WeatherRecordResponse]


class WeatherQualityIssueResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    quality_issue_id: str
    ingestion_run_id: str
    raw_payload_id: str
    weather_record_id: str | None
    provider: str
    location_id: str
    forecast_time: datetime | None
    variable: str | None
    issue_code: str
    severity: str
    message: str
    details: dict[str, object]
    data_mode: str


class WeatherQualityIssueListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[WeatherQualityIssueResponse]


class WeatherFeatureSnapshotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature_snapshot_id: str
    ingestion_run_id: str
    raw_payload_id: str
    provider: str
    location_id: str
    generated_at: datetime
    forecast_start: datetime | None
    feature_version: str
    quality_status: str
    human_review_status: WeatherFeatureReviewStatus
    features: dict[str, float | None]
    evidence: list[dict[str, object]]
    missing_data_warnings: list[str]
    data_mode: str


class WeatherFeatureReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_status: WeatherFeatureReviewAction
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("Weather feature review note must not be blank.")
        return note


class WeatherFeatureReviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    feature_snapshot_id: str
    created_at: datetime
    actor: str
    review_status: WeatherFeatureReviewAction
    note: str


class WeatherQualityIssueSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_count: int
    severity_counts: dict[str, int]
    issue_code_counts: dict[str, int]
    displayed_issue_count: int


class WeatherFeatureApprovalSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    can_approve: bool
    blockers: list[str]
    required_features: list[str]


class WeatherFeatureReviewPackageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_version: str
    generated_at: datetime
    snapshot: WeatherFeatureSnapshotResponse
    quality_issue_summary: WeatherQualityIssueSummary
    quality_issues: list[WeatherQualityIssueResponse]
    reviews: list[WeatherFeatureReviewResponse]
    approval: WeatherFeatureApprovalSummary
    no_auto_trading: bool
    recommendation_chain_requires_approved_snapshot: bool
    network_probe_performed: bool
    fetch_performed: bool
