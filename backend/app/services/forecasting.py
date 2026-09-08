from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from backend.app.adapters.bench_dispatch import (
    BENCH_DISPATCH_ARCHIVE_BASE_URL,
    BENCH_MARKET_TIMEZONE,
    PUBLIC_DERIVED,
    BenchDispatchAdapterError,
    BenchDispatchBenchmarkDraft,
    BenchDispatchClient,
    FetchedBenchDispatchDailyArchive,
    build_bench_dispatch_benchmarks,
)
from backend.app.core.config import get_settings
from backend.app.core.errors import (
    ForecastResearchDatasetNotFoundError,
    ForecastResearchDatasetNotUsableError,
    ForecastResearchModelRunNotFoundError,
    ForecastResearchProviderError,
)
from backend.app.forecasting.baselines import (
    FEATURE_VERSION,
    INTERVALS_PER_DAY,
    MODEL_VERSION,
    InsufficientResearchHistoryError,
    ResearchPricePoint,
    run_research_backtest,
)
from backend.app.models.forecasting import (
    ForecastResearchDataset,
    ForecastResearchDatasetImportRun,
    ForecastResearchModelRun,
    ForecastResearchPrediction,
    ForecastResearchPricePoint,
    ForecastResearchQualityIssue,
)
from backend.app.repositories.forecasting import (
    add_forecast_research_dataset,
    add_forecast_research_dataset_import_run,
    add_forecast_research_model_run,
    add_forecast_research_prediction,
    add_forecast_research_price_point,
    add_forecast_research_quality_issue,
    get_forecast_research_dataset,
    get_forecast_research_dataset_by_hash,
    get_forecast_research_model_run,
    list_forecast_research_dataset_import_runs,
    list_forecast_research_datasets,
    list_forecast_research_model_runs,
    list_forecast_research_predictions,
    list_forecast_research_price_points,
    list_forecast_research_quality_issues,
)
from backend.app.schemas.forecasting import (
    BenchDispatchBenchmarkImportRequest,
    ForecastResearchBacktestRequest,
    ForecastResearchDataMode,
    ForecastResearchDatasetImportRunListResponse,
    ForecastResearchDatasetImportRunResponse,
    ForecastResearchDatasetListResponse,
    ForecastResearchDatasetResponse,
    ForecastResearchDatasetSummary,
    ForecastResearchModelRunListResponse,
    ForecastResearchModelRunResponse,
    ForecastResearchModelRunSummary,
    ForecastResearchOverviewResponse,
    ForecastResearchPredictionListResponse,
    ForecastResearchPredictionResponse,
    ForecastResearchPricePointListResponse,
    ForecastResearchPricePointResponse,
    ForecastResearchQualityIssueListResponse,
    ForecastResearchQualityIssueResponse,
    ForecastResearchQualityIssueSummary,
    ForecastResearchQualitySummary,
    ForecastResearchReviewPackageResponse,
    ManualForecastResearchDatasetRequest,
    ManualForecastResearchDatasetResponse,
)

logger = logging.getLogger(__name__)

RESEARCH_ONLY: Literal["research_only"] = "research_only"
REVIEW_PACKAGE_VERSION = "forecast_research_review_package_v1"
REVIEW_PACKAGE_IMPORT_RUN_LIMIT = 20
REVIEW_PACKAGE_MODEL_RUN_LIMIT = 20
REVIEW_PACKAGE_QUALITY_ISSUE_LIMIT = 100
BENCH_EXPECTED_REGIONS = ("NSW1", "QLD1", "SA1", "TAS1", "VIC1")
BENCH_MARKET_SCOPE = "bench_nem_dispatch_benchmark"


@dataclass(frozen=True)
class QualityIssueDraft:
    issue_code: str
    severity: str
    message: str
    details: dict[str, object]


@dataclass(frozen=True)
class NormalizedPointDraft:
    interval_start: datetime
    trade_date: date
    interval_index: int
    price: Decimal


def get_bench_dispatch_client() -> BenchDispatchClient:
    settings = get_settings()
    return BenchDispatchClient(
        timeout_seconds=settings.bench_dispatch_timeout_seconds,
        max_retries=settings.bench_dispatch_max_retries,
        retry_backoff_seconds=settings.bench_dispatch_retry_backoff_seconds,
    )


def import_bench_dispatch_benchmark(
    request: BenchDispatchBenchmarkImportRequest,
    *,
    session: Session,
    client: BenchDispatchClient,
) -> ManualForecastResearchDatasetResponse:
    try:
        archives = [
            client.fetch_daily_archive(filename, fetched_at=_now())
            for filename in request.archive_filenames
        ]
    except BenchDispatchAdapterError as exc:
        raise ForecastResearchProviderError(code=exc.code, message=exc.message) from exc
    return import_fetched_bench_dispatch_benchmarks(
        archives,
        region_ids=(request.region_id,),
        session=session,
    )[request.region_id]


def import_fetched_bench_dispatch_benchmarks(
    archives: Sequence[FetchedBenchDispatchDailyArchive],
    *,
    region_ids: Sequence[str],
    session: Session,
    raw_object_metadata: Sequence[dict[str, object]] = (),
) -> dict[str, ManualForecastResearchDatasetResponse]:
    try:
        drafts = build_bench_dispatch_benchmarks(archives, region_ids=region_ids)
    except BenchDispatchAdapterError as exc:
        raise ForecastResearchProviderError(code=exc.code, message=exc.message) from exc
    return {
        region_id: _import_bench_dispatch_draft(
            draft,
            session=session,
            raw_object_metadata=raw_object_metadata,
        )
        for region_id, draft in drafts.items()
    }


def _import_bench_dispatch_draft(
    draft: BenchDispatchBenchmarkDraft,
    *,
    session: Session,
    raw_object_metadata: Sequence[dict[str, object]],
) -> ManualForecastResearchDatasetResponse:
    # Keep the source-specific draft construction inside the adapter. This layer only
    # maps the isolated research benchmark into the shared manual import contract.
    source_metadata = draft.to_source_metadata()
    source_metadata["raw_objects"] = list(raw_object_metadata)
    return import_manual_forecast_research_dataset(
        ManualForecastResearchDatasetRequest.model_validate(
            {
                "name": (f"BENCH NEM {draft.region_id} Dispatch RRP 15-minute research benchmark"),
                "source_name": "Australian Energy Market Operator (BENCH) NEM DispatchIS",
                "source_url": BENCH_DISPATCH_ARCHIVE_BASE_URL,
                "region_code": f"BENCH_NEM_{draft.region_id}",
                "region_name": f"BENCH NEM region {draft.region_id}",
                "market_scope": "bench_nem_dispatch_benchmark",
                "market_stage": "real_time",
                "price_scope": "regional_reference_price_15_minute_arithmetic_mean",
                "interval_minutes": 15,
                "timezone": BENCH_MARKET_TIMEZONE,
                "currency": "AUD",
                "price_unit": "AUD_per_MWh",
                "data_mode": PUBLIC_DERIVED,
                "usage_scope": RESEARCH_ONLY,
                "notes": (
                    "BENCH NEM DispatchIS public benchmark only. Derived from source-native "
                    "five-minute regional RRP values by explicit arithmetic mean aggregation. "
                    "It is not Example Province market data and must remain research_only."
                ),
                "points": [
                    {
                        "interval_start": point.interval_start,
                        "price": point.price,
                    }
                    for point in draft.points
                ],
            }
        ),
        session=session,
        content_sha256_override=draft.content_sha256,
        source_metadata_override=source_metadata,
    )


def import_manual_forecast_research_dataset(
    request: ManualForecastResearchDatasetRequest,
    *,
    session: Session,
    content_sha256_override: str | None = None,
    source_metadata_override: dict[str, object] | None = None,
) -> ManualForecastResearchDatasetResponse:
    started_at = _now()
    raw_payload = cast(dict[str, object], request.model_dump(mode="json"))
    if source_metadata_override is not None:
        raw_payload["source_metadata"] = source_metadata_override
    content_sha256 = content_sha256_override or _content_hash(raw_payload)
    import_run_id = _new_id("forecast_import")
    with session.begin():
        existing = get_forecast_research_dataset_by_hash(session, content_sha256)
        if existing is not None:
            run = add_forecast_research_dataset_import_run(
                session,
                import_run_id=import_run_id,
                dataset_id=existing.dataset_id,
                started_at=started_at,
                completed_at=_now(),
                status="duplicate",
                submitted_point_count=len(request.points),
                normalized_point_count=existing.normalized_point_count,
                quality_status=existing.quality_status,
                quality_issue_count=existing.quality_issue_count,
                data_mode=request.data_mode,
            )
            return _to_manual_import_response(existing, run, duplicate_dataset=True)

        dataset_id = f"forecast_dataset_{content_sha256[:32]}"
        normalized_points, issues, trade_date_count = _validate_and_normalize_points(request)
        quality_status = "invalid" if issues else "valid"
        normalized_point_count = 0 if issues else len(normalized_points)
        dataset = add_forecast_research_dataset(
            session,
            dataset_id=dataset_id,
            name=request.name,
            source_name=request.source_name,
            source_url=str(request.source_url),
            region_code=request.region_code,
            region_name=request.region_name,
            market_scope=request.market_scope,
            market_stage=request.market_stage,
            price_scope=request.price_scope,
            interval_minutes=request.interval_minutes,
            timezone=request.timezone,
            currency=request.currency,
            price_unit=request.price_unit,
            data_mode=request.data_mode,
            usage_scope=RESEARCH_ONLY,
            content_sha256=content_sha256,
            raw_payload_json=raw_payload,
            imported_at=started_at,
            quality_status=quality_status,
            quality_issue_count=len(issues),
            normalized_point_count=normalized_point_count,
            trade_date_count=trade_date_count,
            notes=request.notes,
        )
        run = add_forecast_research_dataset_import_run(
            session,
            import_run_id=import_run_id,
            dataset_id=dataset_id,
            started_at=started_at,
            completed_at=_now(),
            status="rejected" if issues else "accepted",
            submitted_point_count=len(request.points),
            normalized_point_count=normalized_point_count,
            quality_status=quality_status,
            quality_issue_count=len(issues),
            data_mode=request.data_mode,
            error_code="forecast_research_dataset_quality_failed" if issues else None,
            error_message="Research dataset failed interval quality checks." if issues else None,
        )
        if not issues:
            for point in normalized_points:
                _add_price_point(
                    session,
                    dataset_id=dataset_id,
                    data_mode=request.data_mode,
                    point=point,
                )
        for issue in issues:
            add_forecast_research_quality_issue(
                session,
                quality_issue_id=_new_id("forecast_quality"),
                dataset_id=dataset_id,
                import_run_id=import_run_id,
                issue_code=issue.issue_code,
                severity=issue.severity,
                message=issue.message,
                details_json=issue.details,
                data_mode=PUBLIC_DERIVED,
            )
    logger.info(
        "Imported forecast research dataset=%s status=%s submitted=%s normalized=%s issues=%s",
        dataset.dataset_id,
        run.status,
        len(request.points),
        normalized_point_count,
        len(issues),
    )
    return _to_manual_import_response(dataset, run, duplicate_dataset=False)


def get_forecast_research_datasets(
    *, limit: int, session: Session
) -> ForecastResearchDatasetListResponse:
    return ForecastResearchDatasetListResponse(
        items=[
            _to_dataset_response(dataset)
            for dataset in list_forecast_research_datasets(session, limit=limit)
        ]
    )


def get_forecast_research_overview(*, session: Session) -> ForecastResearchOverviewResponse:
    generated_at = _now()
    datasets = list_forecast_research_datasets(session, limit=200)
    import_runs = list_forecast_research_dataset_import_runs(
        session,
        dataset_id=None,
        limit=5,
    )
    model_runs = list_forecast_research_model_runs(session, dataset_id=None, limit=5)
    quality_issues = list_forecast_research_quality_issues(
        session,
        dataset_id=None,
        issue_code=None,
        limit=5,
    )
    dataset_count = _scalar_count(
        session,
        select(func.count()).select_from(ForecastResearchDataset),
    )
    valid_dataset_count = _scalar_count(
        session,
        select(func.count())
        .select_from(ForecastResearchDataset)
        .where(ForecastResearchDataset.quality_status == "valid"),
    )
    invalid_dataset_count = _scalar_count(
        session,
        select(func.count())
        .select_from(ForecastResearchDataset)
        .where(ForecastResearchDataset.quality_status != "valid"),
    )
    research_only_dataset_count = _scalar_count(
        session,
        select(func.count())
        .select_from(ForecastResearchDataset)
        .where(ForecastResearchDataset.usage_scope == RESEARCH_ONLY),
    )
    candidate_model_run_count = _scalar_count(
        session,
        select(func.count())
        .select_from(ForecastResearchModelRun)
        .where(ForecastResearchModelRun.registry_status == "candidate"),
    )
    succeeded_model_run_count = _scalar_count(
        session,
        select(func.count())
        .select_from(ForecastResearchModelRun)
        .where(ForecastResearchModelRun.status == "succeeded"),
    )
    bench_available_regions = sorted(
        {
            _short_bench_region(region_code)
            for region_code in session.scalars(
                select(ForecastResearchDataset.region_code).where(
                    ForecastResearchDataset.market_scope == BENCH_MARKET_SCOPE,
                    ForecastResearchDataset.usage_scope == RESEARCH_ONLY,
                )
            )
        }
    )
    bench_missing_regions = [
        region for region in BENCH_EXPECTED_REGIONS if region not in bench_available_regions
    ]
    status = _forecast_overview_status(
        dataset_count=dataset_count,
        invalid_dataset_count=invalid_dataset_count,
        bench_available_count=len(bench_available_regions),
        bench_missing_count=len(bench_missing_regions),
    )
    return ForecastResearchOverviewResponse(
        generated_at=generated_at,
        status=status,
        message=_forecast_overview_message(status, dataset_count, invalid_dataset_count),
        dataset_count=dataset_count,
        valid_dataset_count=valid_dataset_count,
        invalid_dataset_count=invalid_dataset_count,
        research_only_dataset_count=research_only_dataset_count,
        candidate_model_run_count=candidate_model_run_count,
        succeeded_model_run_count=succeeded_model_run_count,
        bench_expected_regions=list(BENCH_EXPECTED_REGIONS),
        bench_available_regions=bench_available_regions,
        bench_missing_regions=bench_missing_regions,
        bench_region_count=len(bench_available_regions),
        datasets=[_to_dataset_summary(dataset) for dataset in datasets],
        recent_import_runs=[_to_import_run_response(run) for run in import_runs],
        recent_model_runs=[_to_model_run_summary(run) for run in model_runs],
        recent_quality_issues=[_to_quality_summary(issue) for issue in quality_issues],
        no_auto_trading=True,
        recommendation_chain_isolated=True,
        network_probe_performed=False,
        fetch_performed=False,
    )


def get_forecast_research_import_runs(
    *, dataset_id: str | None, limit: int, session: Session
) -> ForecastResearchDatasetImportRunListResponse:
    return ForecastResearchDatasetImportRunListResponse(
        items=[
            _to_import_run_response(run)
            for run in list_forecast_research_dataset_import_runs(
                session,
                dataset_id=dataset_id,
                limit=limit,
            )
        ]
    )


def get_forecast_research_price_points(
    dataset_id: str, *, limit: int, session: Session
) -> ForecastResearchPricePointListResponse:
    _require_dataset(session, dataset_id)
    return ForecastResearchPricePointListResponse(
        items=[
            _to_price_point_response(point)
            for point in list_forecast_research_price_points(
                session,
                dataset_id=dataset_id,
                limit=limit,
            )
        ]
    )


def get_forecast_research_quality_issues(
    *,
    dataset_id: str | None,
    issue_code: str | None,
    limit: int,
    session: Session,
) -> ForecastResearchQualityIssueListResponse:
    return ForecastResearchQualityIssueListResponse(
        items=[
            _to_quality_issue_response(issue)
            for issue in list_forecast_research_quality_issues(
                session,
                dataset_id=dataset_id,
                issue_code=issue_code,
                limit=limit,
            )
        ]
    )


def get_forecast_research_review_package(
    dataset_id: str, *, session: Session
) -> ForecastResearchReviewPackageResponse:
    dataset = _require_dataset(session, dataset_id)
    import_runs = list_forecast_research_dataset_import_runs(
        session,
        dataset_id=dataset_id,
        limit=REVIEW_PACKAGE_IMPORT_RUN_LIMIT,
    )
    quality_issues = list_forecast_research_quality_issues(
        session,
        dataset_id=dataset_id,
        issue_code=None,
        limit=REVIEW_PACKAGE_QUALITY_ISSUE_LIMIT,
    )
    model_runs = list_forecast_research_model_runs(
        session,
        dataset_id=dataset_id,
        limit=REVIEW_PACKAGE_MODEL_RUN_LIMIT,
    )
    return ForecastResearchReviewPackageResponse(
        package_version=REVIEW_PACKAGE_VERSION,
        generated_at=_now(),
        dataset=_to_dataset_response(dataset),
        import_runs=[_to_import_run_response(run) for run in import_runs],
        quality_issue_summary=_quality_issue_summary(
            session,
            dataset_id=dataset_id,
            displayed_issue_count=len(quality_issues),
        ),
        quality_issues=[_to_quality_issue_response(issue) for issue in quality_issues],
        model_runs=[_to_model_run_response(run) for run in model_runs],
        no_auto_trading=True,
        recommendation_chain_isolated=True,
        network_probe_performed=False,
        fetch_performed=False,
    )


def run_forecast_research_backtest(
    dataset_id: str,
    request: ForecastResearchBacktestRequest,
    *,
    session: Session,
) -> ForecastResearchModelRunResponse:
    started_at = _now()
    with session.begin():
        dataset = _require_dataset(session, dataset_id)
        if dataset.quality_status != "valid":
            raise ForecastResearchDatasetNotUsableError(dataset_id, "quality status must be valid")
        stored_points = list_forecast_research_price_points(session, dataset_id=dataset_id)
    points = [
        ResearchPricePoint(
            interval_start=point.interval_start,
            trade_date=point.trade_date,
            interval_index=point.interval_index,
            price=point.price,
        )
        for point in stored_points
    ]
    try:
        result = run_research_backtest(
            points,
            model_key=request.model_key,
            evaluation_days=request.evaluation_days,
            lag_days=request.lag_days,
            lookback_days=request.lookback_days,
        )
    except InsufficientResearchHistoryError as exc:
        raise ForecastResearchDatasetNotUsableError(dataset_id, str(exc)) from exc

    model_run_id = _new_id("forecast_model")
    completed_at = _now()
    with session.begin():
        run = add_forecast_research_model_run(
            session,
            model_run_id=model_run_id,
            dataset_id=dataset_id,
            model_key=request.model_key,
            model_version=MODEL_VERSION,
            feature_version=FEATURE_VERSION,
            started_at=started_at,
            completed_at=completed_at,
            status="succeeded",
            registry_status="candidate",
            train_start=result.train_start,
            train_end=result.train_end,
            evaluation_start=result.evaluation_start,
            evaluation_end=result.evaluation_end,
            horizon_intervals=INTERVALS_PER_DAY,
            parameters_json=result.parameters,
            metrics_json=result.metrics,
            artifact_path=None,
            usage_scope=RESEARCH_ONLY,
            data_mode=PUBLIC_DERIVED,
        )
        for prediction in result.predictions:
            add_forecast_research_prediction(
                session,
                prediction_id=_prediction_id(model_run_id, prediction.target_interval_start),
                model_run_id=model_run_id,
                target_interval_start=prediction.target_interval_start,
                trade_date=prediction.trade_date,
                interval_index=prediction.interval_index,
                actual_price=prediction.actual_price,
                predicted_price=prediction.predicted_price,
                data_mode=PUBLIC_DERIVED,
            )
    logger.info(
        "Ran forecast research backtest run=%s dataset=%s model=%s predictions=%s",
        model_run_id,
        dataset_id,
        request.model_key,
        len(result.predictions),
    )
    return _to_model_run_response(run)


def get_forecast_research_model_runs(
    *, dataset_id: str | None, limit: int, session: Session
) -> ForecastResearchModelRunListResponse:
    return ForecastResearchModelRunListResponse(
        items=[
            _to_model_run_response(run)
            for run in list_forecast_research_model_runs(
                session,
                dataset_id=dataset_id,
                limit=limit,
            )
        ]
    )


def get_forecast_research_predictions(
    model_run_id: str, *, limit: int, session: Session
) -> ForecastResearchPredictionListResponse:
    if get_forecast_research_model_run(session, model_run_id) is None:
        raise ForecastResearchModelRunNotFoundError(model_run_id)
    return ForecastResearchPredictionListResponse(
        items=[
            _to_prediction_response(prediction)
            for prediction in list_forecast_research_predictions(
                session,
                model_run_id=model_run_id,
                limit=limit,
            )
        ]
    )


def _validate_and_normalize_points(
    request: ManualForecastResearchDatasetRequest,
) -> tuple[list[NormalizedPointDraft], list[QualityIssueDraft], int]:
    timezone = ZoneInfo(request.timezone)
    issues: list[QualityIssueDraft] = []
    normalized: list[NormalizedPointDraft] = []
    seen_times: set[datetime] = set()
    grouped: dict[date, list[NormalizedPointDraft]] = {}
    for source_point in request.points:
        local_start = source_point.interval_start.astimezone(timezone)
        if local_start in seen_times:
            issues.append(
                QualityIssueDraft(
                    issue_code="duplicate_interval_start",
                    severity="error",
                    message="Research dataset contains a duplicate interval timestamp.",
                    details={"interval_start": local_start.isoformat()},
                )
            )
        seen_times.add(local_start)
        if local_start.second or local_start.microsecond or local_start.minute % 15:
            issues.append(
                QualityIssueDraft(
                    issue_code="unexpected_interval_alignment",
                    severity="error",
                    message="Research dataset timestamps must align to exact 15-minute boundaries.",
                    details={"interval_start": local_start.isoformat()},
                )
            )
        interval_index = (local_start.hour * 60 + local_start.minute) // 15 + 1
        point = NormalizedPointDraft(
            interval_start=local_start,
            trade_date=local_start.date(),
            interval_index=interval_index,
            price=source_point.price,
        )
        normalized.append(point)
        grouped.setdefault(point.trade_date, []).append(point)

    for trade_date, daily_points in sorted(grouped.items()):
        daily_indexes = sorted(point.interval_index for point in daily_points)
        if len(daily_points) != INTERVALS_PER_DAY:
            issues.append(
                QualityIssueDraft(
                    issue_code="incomplete_trade_date",
                    severity="error",
                    message="Each research trade date must contain exactly 96 interval points.",
                    details={
                        "trade_date": trade_date.isoformat(),
                        "point_count": len(daily_points),
                        "expected_point_count": INTERVALS_PER_DAY,
                    },
                )
            )
        if daily_indexes != list(range(1, INTERVALS_PER_DAY + 1)):
            issues.append(
                QualityIssueDraft(
                    issue_code="unexpected_daily_interval_coverage",
                    severity="error",
                    message="Research dataset trade-date interval indexes must cover 1 through 96.",
                    details={
                        "trade_date": trade_date.isoformat(),
                        "interval_indexes": daily_indexes,
                    },
                )
            )
    return sorted(normalized, key=lambda item: item.interval_start), issues, len(grouped)


def _add_price_point(
    session: Session,
    *,
    dataset_id: str,
    data_mode: ForecastResearchDataMode,
    point: NormalizedPointDraft,
) -> None:
    add_forecast_research_price_point(
        session,
        point_id=_price_point_id(dataset_id, point.interval_start),
        dataset_id=dataset_id,
        interval_start=point.interval_start,
        trade_date=point.trade_date,
        interval_index=point.interval_index,
        price=point.price,
        data_mode=data_mode,
    )


def _require_dataset(session: Session, dataset_id: str) -> ForecastResearchDataset:
    dataset = get_forecast_research_dataset(session, dataset_id)
    if dataset is None:
        raise ForecastResearchDatasetNotFoundError(dataset_id)
    return dataset


def _to_manual_import_response(
    dataset: ForecastResearchDataset,
    run: ForecastResearchDatasetImportRun,
    *,
    duplicate_dataset: bool,
) -> ManualForecastResearchDatasetResponse:
    return ManualForecastResearchDatasetResponse(
        import_run_id=run.import_run_id,
        dataset_id=dataset.dataset_id,
        status=run.status,
        duplicate_dataset=duplicate_dataset,
        quality_status=dataset.quality_status,
        quality_issue_count=dataset.quality_issue_count,
        submitted_point_count=run.submitted_point_count,
        normalized_point_count=dataset.normalized_point_count,
        trade_date_count=dataset.trade_date_count,
        content_sha256=dataset.content_sha256,
        data_mode=cast(ForecastResearchDataMode, dataset.data_mode),
        usage_scope=RESEARCH_ONLY,
    )


def _to_dataset_response(dataset: ForecastResearchDataset) -> ForecastResearchDatasetResponse:
    return ForecastResearchDatasetResponse(
        dataset_id=dataset.dataset_id,
        name=dataset.name,
        source_name=dataset.source_name,
        source_url=dataset.source_url,
        region_code=dataset.region_code,
        region_name=dataset.region_name,
        market_scope=dataset.market_scope,
        market_stage=dataset.market_stage,
        price_scope=dataset.price_scope,
        interval_minutes=dataset.interval_minutes,
        timezone=dataset.timezone,
        currency=dataset.currency,
        price_unit=dataset.price_unit,
        data_mode=dataset.data_mode,
        usage_scope=dataset.usage_scope,
        content_sha256=dataset.content_sha256,
        imported_at=dataset.imported_at,
        quality_status=dataset.quality_status,
        quality_issue_count=dataset.quality_issue_count,
        normalized_point_count=dataset.normalized_point_count,
        trade_date_count=dataset.trade_date_count,
        notes=dataset.notes,
    )


def _to_dataset_summary(dataset: ForecastResearchDataset) -> ForecastResearchDatasetSummary:
    return ForecastResearchDatasetSummary(
        dataset_id=dataset.dataset_id,
        name=dataset.name,
        region_code=dataset.region_code,
        region_name=dataset.region_name,
        market_scope=dataset.market_scope,
        market_stage=dataset.market_stage,
        quality_status=dataset.quality_status,
        quality_issue_count=dataset.quality_issue_count,
        normalized_point_count=dataset.normalized_point_count,
        trade_date_count=dataset.trade_date_count,
        imported_at=dataset.imported_at,
        data_mode=dataset.data_mode,
        usage_scope=dataset.usage_scope,
    )


def _to_import_run_response(
    run: ForecastResearchDatasetImportRun,
) -> ForecastResearchDatasetImportRunResponse:
    return ForecastResearchDatasetImportRunResponse(
        import_run_id=run.import_run_id,
        dataset_id=run.dataset_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        submitted_point_count=run.submitted_point_count,
        normalized_point_count=run.normalized_point_count,
        quality_status=run.quality_status,
        quality_issue_count=run.quality_issue_count,
        data_mode=run.data_mode,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _to_price_point_response(
    point: ForecastResearchPricePoint,
) -> ForecastResearchPricePointResponse:
    return ForecastResearchPricePointResponse(
        point_id=point.point_id,
        dataset_id=point.dataset_id,
        interval_start=point.interval_start,
        trade_date=point.trade_date,
        interval_index=point.interval_index,
        price=point.price,
        data_mode=point.data_mode,
    )


def _to_quality_issue_response(
    issue: ForecastResearchQualityIssue,
) -> ForecastResearchQualityIssueResponse:
    return ForecastResearchQualityIssueResponse(
        quality_issue_id=issue.quality_issue_id,
        dataset_id=issue.dataset_id,
        import_run_id=issue.import_run_id,
        issue_code=issue.issue_code,
        severity=issue.severity,
        message=issue.message,
        details=issue.details_json,
        data_mode=issue.data_mode,
    )


def _to_model_run_response(run: ForecastResearchModelRun) -> ForecastResearchModelRunResponse:
    return ForecastResearchModelRunResponse(
        model_run_id=run.model_run_id,
        dataset_id=run.dataset_id,
        model_key=run.model_key,
        model_version=run.model_version,
        feature_version=run.feature_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        registry_status=run.registry_status,
        train_start=run.train_start,
        train_end=run.train_end,
        evaluation_start=run.evaluation_start,
        evaluation_end=run.evaluation_end,
        horizon_intervals=run.horizon_intervals,
        parameters=run.parameters_json,
        metrics=run.metrics_json,
        artifact_path=run.artifact_path,
        usage_scope=run.usage_scope,
        data_mode=run.data_mode,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _to_model_run_summary(run: ForecastResearchModelRun) -> ForecastResearchModelRunSummary:
    return ForecastResearchModelRunSummary(
        model_run_id=run.model_run_id,
        dataset_id=run.dataset_id,
        model_key=run.model_key,
        status=run.status,
        registry_status=run.registry_status,
        completed_at=run.completed_at,
        metrics=run.metrics_json,
        usage_scope=run.usage_scope,
        data_mode=run.data_mode,
    )


def _to_quality_summary(issue: ForecastResearchQualityIssue) -> ForecastResearchQualitySummary:
    return ForecastResearchQualitySummary(
        quality_issue_id=issue.quality_issue_id,
        dataset_id=issue.dataset_id,
        issue_code=issue.issue_code,
        severity=issue.severity,
        message=issue.message,
        created_at=issue.created_at,
        data_mode=issue.data_mode,
    )


def _quality_issue_summary(
    session: Session,
    *,
    dataset_id: str,
    displayed_issue_count: int,
) -> ForecastResearchQualityIssueSummary:
    return ForecastResearchQualityIssueSummary(
        total_count=_scalar_count(
            session,
            select(func.count())
            .select_from(ForecastResearchQualityIssue)
            .where(ForecastResearchQualityIssue.dataset_id == dataset_id),
        ),
        severity_counts=_quality_issue_count_by(
            session,
            dataset_id=dataset_id,
            field_name="severity",
        ),
        issue_code_counts=_quality_issue_count_by(
            session,
            dataset_id=dataset_id,
            field_name="issue_code",
        ),
        displayed_issue_count=displayed_issue_count,
    )


def _quality_issue_count_by(
    session: Session,
    *,
    dataset_id: str,
    field_name: Literal["severity", "issue_code"],
) -> dict[str, int]:
    field = (
        ForecastResearchQualityIssue.severity
        if field_name == "severity"
        else ForecastResearchQualityIssue.issue_code
    )
    statement = (
        select(field, func.count())
        .where(ForecastResearchQualityIssue.dataset_id == dataset_id)
        .group_by(field)
        .order_by(field)
    )
    return {str(key): int(count) for key, count in session.execute(statement)}


def _forecast_overview_status(
    *,
    dataset_count: int,
    invalid_dataset_count: int,
    bench_available_count: int,
    bench_missing_count: int,
) -> Literal["healthy", "warning", "critical"]:
    if dataset_count == 0:
        return "warning"
    if invalid_dataset_count > 0:
        return "warning"
    if bench_available_count > 0 and bench_missing_count > 0:
        return "warning"
    return "healthy"


def _forecast_overview_message(
    status: str,
    dataset_count: int,
    invalid_dataset_count: int,
) -> str:
    if dataset_count == 0:
        return "No forecast research datasets are available yet."
    if invalid_dataset_count > 0:
        return "Forecast research has datasets with quality issues that need review."
    if status == "warning":
        return "Forecast research is available, but benchmark coverage is incomplete."
    return "Forecast research datasets and candidate model runs are available for review."


def _short_bench_region(region_code: str) -> str:
    return region_code.removeprefix("BENCH_NEM_")


def _scalar_count(session: Session, statement: Select[tuple[int]]) -> int:
    value = session.scalar(statement)
    return int(value or 0)


def _to_prediction_response(
    prediction: ForecastResearchPrediction,
) -> ForecastResearchPredictionResponse:
    return ForecastResearchPredictionResponse(
        prediction_id=prediction.prediction_id,
        model_run_id=prediction.model_run_id,
        target_interval_start=prediction.target_interval_start,
        trade_date=prediction.trade_date,
        interval_index=prediction.interval_index,
        actual_price=prediction.actual_price,
        predicted_price=prediction.predicted_price,
        data_mode=prediction.data_mode,
    )


def _content_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _price_point_id(dataset_id: str, interval_start: datetime) -> str:
    return _hash_parts(dataset_id, interval_start.isoformat())


def _prediction_id(model_run_id: str, target_interval_start: datetime) -> str:
    return _hash_parts(model_run_id, target_interval_start.isoformat())


def _hash_parts(*parts: str) -> str:
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _now() -> datetime:
    return datetime.now(UTC)
