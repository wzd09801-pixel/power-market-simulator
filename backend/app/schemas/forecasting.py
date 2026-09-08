from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

ForecastResearchDataMode = Literal[
    "public_observed",
    "public_derived",
    "scenario_simulated",
    "user_uploaded",
]
ForecastResearchMarketStage = Literal["day_ahead", "real_time", "other"]
ForecastResearchModelKey = Literal["seasonal_naive", "calendar_mean"]
BenchDispatchRegionId = Literal["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]


class ForecastResearchPricePointRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval_start: datetime
    price: Decimal = Field(ge=-100_000, le=100_000, max_digits=18, decimal_places=4)

    @field_validator("interval_start")
    @classmethod
    def interval_start_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Interval start must include a timezone offset.")
        return value


class ManualForecastResearchDatasetRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=160)
    source_name: str = Field(min_length=1, max_length=160)
    source_url: HttpUrl
    region_code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    region_name: str = Field(min_length=1, max_length=120)
    market_scope: str = Field(min_length=1, max_length=80)
    market_stage: ForecastResearchMarketStage
    price_scope: str = Field(min_length=1, max_length=80)
    interval_minutes: Literal[15] = 15
    timezone: str = Field(min_length=1, max_length=80)
    currency: str = Field(min_length=1, max_length=16, pattern=r"^[A-Z]{3}$")
    price_unit: str = Field(min_length=1, max_length=40)
    data_mode: ForecastResearchDataMode
    usage_scope: Literal["research_only"] = "research_only"
    notes: str = Field(min_length=1, max_length=2000)
    points: list[ForecastResearchPricePointRequest] = Field(min_length=1, max_length=35_040)

    @field_validator("name", "source_name", "region_name", "market_scope", "price_scope", "notes")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Text fields must not be blank.")
        return text

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_known(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone must be a known IANA timezone.") from exc
        return value


class BenchDispatchBenchmarkImportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    archive_filenames: list[str] = Field(min_length=1, max_length=31)
    region_id: BenchDispatchRegionId

    @field_validator("archive_filenames")
    @classmethod
    def archive_filenames_must_be_unique_and_allowlisted(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("BENCH Dispatch archive filenames must be unique.")
        for filename in value:
            if not (
                len(filename) == len("PUBLIC_DISPATCHIS_YYYYMMDD.zip")
                and filename.startswith("PUBLIC_DISPATCHIS_")
                and filename.endswith(".zip")
                and filename[18:26].isdigit()
            ):
                raise ValueError(
                    "BENCH Dispatch archive filenames must match 'PUBLIC_DISPATCHIS_YYYYMMDD.zip'."
                )
        return value


class ManualForecastResearchDatasetResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    import_run_id: str
    dataset_id: str
    status: str
    duplicate_dataset: bool
    quality_status: str
    quality_issue_count: int
    submitted_point_count: int
    normalized_point_count: int
    trade_date_count: int
    content_sha256: str
    data_mode: ForecastResearchDataMode
    usage_scope: Literal["research_only"]


class ForecastResearchDatasetResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    name: str
    source_name: str
    source_url: str
    region_code: str
    region_name: str
    market_scope: str
    market_stage: str
    price_scope: str
    interval_minutes: int
    timezone: str
    currency: str
    price_unit: str
    data_mode: str
    usage_scope: str
    content_sha256: str
    imported_at: datetime
    quality_status: str
    quality_issue_count: int
    normalized_point_count: int
    trade_date_count: int
    notes: str


class ForecastResearchDatasetListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ForecastResearchDatasetResponse]


class ForecastResearchDatasetSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    name: str
    region_code: str
    region_name: str
    market_scope: str
    market_stage: str
    quality_status: str
    quality_issue_count: int
    normalized_point_count: int
    trade_date_count: int
    imported_at: datetime
    data_mode: str
    usage_scope: str


class ForecastResearchModelRunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_run_id: str
    dataset_id: str
    model_key: str
    status: str
    registry_status: str
    completed_at: datetime
    metrics: dict[str, object]
    usage_scope: str
    data_mode: str


class ForecastResearchQualitySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    quality_issue_id: str
    dataset_id: str
    issue_code: str
    severity: str
    message: str
    created_at: datetime
    data_mode: str


class ForecastResearchDatasetImportRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    import_run_id: str
    dataset_id: str
    started_at: datetime
    completed_at: datetime
    status: str
    submitted_point_count: int
    normalized_point_count: int
    quality_status: str
    quality_issue_count: int
    data_mode: str
    error_code: str | None
    error_message: str | None


class ForecastResearchDatasetImportRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ForecastResearchDatasetImportRunResponse]


class ForecastResearchOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    status: Literal["healthy", "warning", "critical"]
    message: str
    dataset_count: int
    valid_dataset_count: int
    invalid_dataset_count: int
    research_only_dataset_count: int
    candidate_model_run_count: int
    succeeded_model_run_count: int
    bench_expected_regions: list[str]
    bench_available_regions: list[str]
    bench_missing_regions: list[str]
    bench_region_count: int
    datasets: list[ForecastResearchDatasetSummary]
    recent_import_runs: list[ForecastResearchDatasetImportRunResponse]
    recent_model_runs: list[ForecastResearchModelRunSummary]
    recent_quality_issues: list[ForecastResearchQualitySummary]
    no_auto_trading: bool
    recommendation_chain_isolated: bool
    network_probe_performed: bool
    fetch_performed: bool


class ForecastResearchPricePointResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    point_id: str
    dataset_id: str
    interval_start: datetime
    trade_date: date
    interval_index: int
    price: Decimal
    data_mode: str


class ForecastResearchPricePointListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ForecastResearchPricePointResponse]


class ForecastResearchQualityIssueResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    quality_issue_id: str
    dataset_id: str
    import_run_id: str | None
    issue_code: str
    severity: str
    message: str
    details: dict[str, object]
    data_mode: str


class ForecastResearchQualityIssueListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ForecastResearchQualityIssueResponse]


class ForecastResearchQualityIssueSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_count: int
    severity_counts: dict[str, int]
    issue_code_counts: dict[str, int]
    displayed_issue_count: int


class ForecastResearchReviewPackageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_version: str
    generated_at: datetime
    dataset: ForecastResearchDatasetResponse
    import_runs: list[ForecastResearchDatasetImportRunResponse]
    quality_issue_summary: ForecastResearchQualityIssueSummary
    quality_issues: list[ForecastResearchQualityIssueResponse]
    model_runs: list[ForecastResearchModelRunResponse]
    no_auto_trading: bool
    recommendation_chain_isolated: bool
    network_probe_performed: bool
    fetch_performed: bool


class ForecastResearchBacktestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_key: ForecastResearchModelKey
    evaluation_days: int = Field(default=3, ge=1, le=30)
    lag_days: int = Field(default=7, ge=1, le=30)
    lookback_days: int = Field(default=7, ge=2, le=30)


class ForecastResearchModelRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_run_id: str
    dataset_id: str
    model_key: str
    model_version: str
    feature_version: str
    started_at: datetime
    completed_at: datetime
    status: str
    registry_status: str
    train_start: date
    train_end: date
    evaluation_start: date
    evaluation_end: date
    horizon_intervals: int
    parameters: dict[str, object]
    metrics: dict[str, object]
    artifact_path: str | None
    usage_scope: str
    data_mode: str
    error_code: str | None
    error_message: str | None


class ForecastResearchModelRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ForecastResearchModelRunResponse]


class ForecastResearchPredictionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    prediction_id: str
    model_run_id: str
    target_interval_start: datetime
    trade_date: date
    interval_index: int
    actual_price: Decimal
    predicted_price: Decimal
    data_mode: str


class ForecastResearchPredictionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ForecastResearchPredictionResponse]
