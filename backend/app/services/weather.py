from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.adapters.open_meteo import (
    NormalizedWeatherRecord,
    OpenMeteoAdapterError,
    OpenMeteoClient,
    OpenMeteoFetchResult,
    OpenMeteoForecastQuery,
)
from backend.app.core.config import get_settings
from backend.app.core.errors import (
    WeatherFeatureSnapshotNotFoundError,
    WeatherFeatureSnapshotNotUsableError,
    WeatherLocationConflictError,
    WeatherProviderError,
)
from backend.app.models.weather import (
    WeatherFeatureReview,
    WeatherFeatureSnapshot,
    WeatherLocation,
    WeatherQualityIssue,
    WeatherRawPayload,
    WeatherRecord,
)
from backend.app.repositories.weather import (
    add_weather_feature_review,
    add_weather_feature_snapshot,
    add_weather_ingestion_run,
    add_weather_location,
    add_weather_quality_issue,
    add_weather_raw_payload,
    add_weather_record,
    get_latest_weather_feature_snapshot,
    get_weather_feature_snapshot,
    get_weather_feature_snapshot_by_id,
    get_weather_location,
    get_weather_raw_payload,
    get_weather_record,
    list_weather_feature_reviews,
    list_weather_quality_issues,
    list_weather_records,
)
from backend.app.schemas.weather import (
    OpenMeteoForecastIngestRequest,
    WeatherFeatureApprovalSummary,
    WeatherFeatureReviewAction,
    WeatherFeatureReviewPackageResponse,
    WeatherFeatureReviewRequest,
    WeatherFeatureReviewResponse,
    WeatherFeatureSnapshotResponse,
    WeatherIngestionResponse,
    WeatherQualityIssueListResponse,
    WeatherQualityIssueResponse,
    WeatherQualityIssueSummary,
    WeatherRecordListResponse,
    WeatherRecordResponse,
)
from backend.app.services.weather_features import (
    REQUIRED_HYDRO_WEATHER_FEATURES,
    WeatherFeatureDraft,
    derive_hydro_weather_features,
)
from backend.app.services.weather_quality import (
    WeatherQualityAssessment,
    assess_weather_records,
)

logger = logging.getLogger(__name__)

PUBLIC_OBSERVED = "public_observed"
PUBLIC_DERIVED = "public_derived"
WEATHER_REVIEW_PACKAGE_VERSION = "weather_feature_review_package_v1"


def _now() -> datetime:
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def get_open_meteo_client() -> OpenMeteoClient:
    settings = get_settings()
    return OpenMeteoClient(
        forecast_url=settings.open_meteo_forecast_url,
        timeout_seconds=settings.open_meteo_timeout_seconds,
        max_retries=settings.open_meteo_max_retries,
        retry_backoff_seconds=settings.open_meteo_retry_backoff_seconds,
    )


def ingest_open_meteo_forecast(
    request: OpenMeteoForecastIngestRequest,
    *,
    session: Session,
    client: OpenMeteoClient,
) -> WeatherIngestionResponse:
    # Open-Meteo does not expose a separate forecast issue timestamp.
    # Preserve retrieval start as the explicit issue-time proxy for this provider.
    started_at = _now()
    query = OpenMeteoForecastQuery(
        location_id=request.location_id,
        latitude=request.latitude,
        longitude=request.longitude,
        timezone=request.timezone,
        forecast_days=request.forecast_days,
        hourly_variables=tuple(request.hourly_variables),
    )

    with session.begin():
        _validate_existing_location(session, request)

    try:
        result = client.fetch_forecast(query, issue_time=started_at)
    except OpenMeteoAdapterError as exc:
        _persist_failed_run(
            request=request,
            session=session,
            started_at=started_at,
            completed_at=_now(),
            error=exc,
        )
        raise WeatherProviderError(code=exc.code, message=exc.message) from exc

    completed_at = _now()
    ingestion_run_id = _new_id("weather_ingest")
    assessment = assess_weather_records(result.records)
    with session.begin():
        _get_or_add_location(session, request)
        raw_payload = _get_or_add_raw_payload(
            session,
            request=request,
            result=result,
            fetched_at=completed_at,
        )
        inserted = _add_new_records(
            session,
            request=request,
            records=assessment.records,
            provider=result.provider,
            raw_payload_id=raw_payload.raw_payload_id,
        )
        duplicate_records = len(result.records) - inserted
        add_weather_ingestion_run(
            session,
            ingestion_run_id=ingestion_run_id,
            provider=result.provider,
            location_id=request.location_id,
            started_at=started_at,
            completed_at=completed_at,
            status="succeeded",
            request_url=result.request_url,
            raw_payload_id=raw_payload.raw_payload_id,
            records_received=len(result.records),
            records_inserted=inserted,
            duplicate_records=duplicate_records,
            quality_status=assessment.quality_status,
            quality_issue_count=len(assessment.issues),
        )
        _add_quality_issues(
            session,
            ingestion_run_id=ingestion_run_id,
            raw_payload_id=raw_payload.raw_payload_id,
            provider=result.provider,
            location_id=request.location_id,
            assessment=assessment,
        )
        feature_draft = derive_hydro_weather_features(
            assessment.records,
            provider=result.provider,
            location_id=request.location_id,
            raw_payload_id=raw_payload.raw_payload_id,
            source_quality_status=assessment.quality_status,
        )
        feature_snapshot = _get_or_add_feature_snapshot(
            session,
            draft=feature_draft,
            ingestion_run_id=ingestion_run_id,
            raw_payload_id=raw_payload.raw_payload_id,
            provider=result.provider,
            location_id=request.location_id,
            generated_at=completed_at,
        )

    logger.info(
        "Completed Open-Meteo ingestion run=%s location=%s inserted=%s duplicates=%s",
        ingestion_run_id,
        request.location_id,
        inserted,
        duplicate_records,
    )
    return WeatherIngestionResponse(
        ingestion_run_id=ingestion_run_id,
        provider=result.provider,
        location_id=request.location_id,
        status="succeeded",
        started_at=started_at,
        completed_at=completed_at,
        raw_payload_id=raw_payload.raw_payload_id,
        records_received=len(result.records),
        records_inserted=inserted,
        duplicate_records=duplicate_records,
        quality_status=assessment.quality_status,
        quality_issue_count=len(assessment.issues),
        feature_snapshot_id=feature_snapshot.feature_snapshot_id,
        data_mode=PUBLIC_OBSERVED,
    )


def get_weather_records(
    *,
    location_id: str,
    variable: str | None,
    limit: int,
    session: Session,
) -> WeatherRecordListResponse:
    records = list_weather_records(
        session,
        location_id=location_id,
        variable=variable,
        limit=limit,
    )
    return WeatherRecordListResponse(items=[_to_record_response(record) for record in records])


def get_latest_weather_features(
    *,
    location_id: str,
    session: Session,
) -> WeatherFeatureSnapshotResponse:
    snapshot = get_latest_weather_feature_snapshot(session, location_id)
    if snapshot is None:
        raise WeatherFeatureSnapshotNotFoundError(location_id)
    return _to_feature_snapshot_response(snapshot)


def get_weather_quality_issues(
    *,
    location_id: str,
    issue_code: str | None,
    limit: int,
    session: Session,
) -> WeatherQualityIssueListResponse:
    issues = list_weather_quality_issues(
        session,
        location_id=location_id,
        issue_code=issue_code,
        limit=limit,
    )
    return WeatherQualityIssueListResponse(
        items=[_to_quality_issue_response(issue) for issue in issues]
    )


def review_weather_feature_snapshot(
    feature_snapshot_id: str,
    request: WeatherFeatureReviewRequest,
    *,
    session: Session,
) -> WeatherFeatureReviewResponse:
    created_at = _now()
    with session.begin():
        snapshot = get_weather_feature_snapshot_by_id(session, feature_snapshot_id)
        if snapshot is None:
            raise WeatherFeatureSnapshotNotFoundError(
                feature_snapshot_id, identifier_type="snapshot"
            )
        if request.review_status == "approved":
            _ensure_weather_feature_snapshot_can_be_approved(snapshot)
        review = add_weather_feature_review(
            session,
            review_id=_new_id("weather_feature_review"),
            feature_snapshot_id=feature_snapshot_id,
            created_at=created_at,
            review_status=request.review_status,
            note=request.note,
            actor="local_operator",
        )
        snapshot.human_review_status = request.review_status
    return _to_feature_review_response(review)


def get_weather_feature_review_package(
    feature_snapshot_id: str,
    *,
    session: Session,
    issue_limit: int = 50,
) -> WeatherFeatureReviewPackageResponse:
    snapshot = get_weather_feature_snapshot_by_id(session, feature_snapshot_id)
    if snapshot is None:
        raise WeatherFeatureSnapshotNotFoundError(
            feature_snapshot_id,
            identifier_type="snapshot",
        )
    issues = list_weather_quality_issues(
        session,
        location_id=snapshot.location_id,
        issue_code=None,
        limit=1000,
    )
    related_issues = [issue for issue in issues if issue.raw_payload_id == snapshot.raw_payload_id]
    displayed_issues = related_issues[:issue_limit]
    reviews = list_weather_feature_reviews(session, feature_snapshot_id)
    blockers = _weather_feature_approval_blockers(snapshot)
    return WeatherFeatureReviewPackageResponse(
        package_version=WEATHER_REVIEW_PACKAGE_VERSION,
        generated_at=_now(),
        snapshot=_to_feature_snapshot_response(snapshot),
        quality_issue_summary=_quality_issue_summary(
            related_issues,
            displayed_count=len(displayed_issues),
        ),
        quality_issues=[_to_quality_issue_response(issue) for issue in displayed_issues],
        reviews=[_to_feature_review_response(review) for review in reviews],
        approval=WeatherFeatureApprovalSummary(
            can_approve=not blockers,
            blockers=blockers,
            required_features=list(REQUIRED_HYDRO_WEATHER_FEATURES),
        ),
        no_auto_trading=True,
        recommendation_chain_requires_approved_snapshot=True,
        network_probe_performed=False,
        fetch_performed=False,
    )


def _persist_failed_run(
    *,
    request: OpenMeteoForecastIngestRequest,
    session: Session,
    started_at: datetime,
    completed_at: datetime,
    error: OpenMeteoAdapterError,
) -> None:
    ingestion_run_id = _new_id("weather_ingest")
    with session.begin():
        _get_or_add_location(session, request)
        raw_payload_id = _persist_failed_raw_payload(
            request=request,
            session=session,
            fetched_at=completed_at,
            error=error,
        )
        add_weather_ingestion_run(
            session,
            ingestion_run_id=ingestion_run_id,
            provider=OpenMeteoClient.provider,
            location_id=request.location_id,
            started_at=started_at,
            completed_at=completed_at,
            status="failed",
            request_url=error.request_url,
            raw_payload_id=raw_payload_id,
            records_received=0,
            records_inserted=0,
            duplicate_records=0,
            quality_status="failed",
            quality_issue_count=0,
            error_code=error.code,
            error_message=error.message,
        )
    logger.warning(
        "Open-Meteo ingestion failed run=%s location=%s code=%s",
        ingestion_run_id,
        request.location_id,
        error.code,
    )


def _get_or_add_location(
    session: Session,
    request: OpenMeteoForecastIngestRequest,
) -> WeatherLocation:
    location = get_weather_location(session, request.location_id)
    if location is None:
        return add_weather_location(
            session,
            location_id=request.location_id,
            name=request.location_name,
            latitude=request.latitude,
            longitude=request.longitude,
            timezone=request.timezone,
            data_mode=PUBLIC_DERIVED,
        )
    _validate_location_identity(location, request)
    return location


def _validate_existing_location(
    session: Session,
    request: OpenMeteoForecastIngestRequest,
) -> None:
    location = get_weather_location(session, request.location_id)
    if location is not None:
        _validate_location_identity(location, request)


def _validate_location_identity(
    location: WeatherLocation,
    request: OpenMeteoForecastIngestRequest,
) -> None:
    if (
        abs(location.latitude - request.latitude) > 1e-7
        or abs(location.longitude - request.longitude) > 1e-7
        or location.timezone != request.timezone
    ):
        raise WeatherLocationConflictError(request.location_id)


def _get_or_add_raw_payload(
    session: Session,
    *,
    request: OpenMeteoForecastIngestRequest,
    result: OpenMeteoFetchResult,
    fetched_at: datetime,
) -> WeatherRawPayload:
    payload = get_weather_raw_payload(session, result.payload_hash)
    if payload is not None:
        return payload
    return add_weather_raw_payload(
        session,
        raw_payload_id=result.payload_hash,
        provider=result.provider,
        location_id=request.location_id,
        fetched_at=fetched_at,
        request_url=result.request_url,
        request_params_json=result.request_params,
        payload_json=result.payload_json,
        raw_content=result.raw_content,
        content_hash=result.payload_hash,
        data_mode=PUBLIC_OBSERVED,
        quality_flag="valid",
    )


def _persist_failed_raw_payload(
    *,
    request: OpenMeteoForecastIngestRequest,
    session: Session,
    fetched_at: datetime,
    error: OpenMeteoAdapterError,
) -> str | None:
    if error.raw_content is None:
        return None
    content_hash = _hash_failed_payload(
        provider=OpenMeteoClient.provider,
        location_id=request.location_id,
        raw_content=error.raw_content,
    )
    payload = get_weather_raw_payload(session, content_hash)
    if payload is not None:
        return payload.raw_payload_id
    payload = add_weather_raw_payload(
        session,
        raw_payload_id=content_hash,
        provider=OpenMeteoClient.provider,
        location_id=request.location_id,
        fetched_at=fetched_at,
        request_url=error.request_url,
        request_params_json=error.request_params,
        payload_json=error.payload_json,
        raw_content=error.raw_content,
        content_hash=content_hash,
        data_mode=PUBLIC_OBSERVED,
        quality_flag="invalid",
    )
    return payload.raw_payload_id


def _add_new_records(
    session: Session,
    *,
    request: OpenMeteoForecastIngestRequest,
    records: tuple[NormalizedWeatherRecord, ...],
    provider: str,
    raw_payload_id: str,
) -> int:
    inserted = 0
    for item in records:
        if get_weather_record(session, item.content_hash) is not None:
            continue
        add_weather_record(
            session,
            weather_record_id=item.content_hash,
            raw_payload_id=raw_payload_id,
            provider=provider,
            location_id=request.location_id,
            issue_time=item.issue_time,
            forecast_time=item.forecast_time,
            variable=item.variable,
            value=item.value,
            unit=item.unit,
            data_mode=PUBLIC_OBSERVED,
            quality_flag=item.quality_flag,
            content_hash=item.content_hash,
        )
        inserted += 1
    return inserted


def _add_quality_issues(
    session: Session,
    *,
    ingestion_run_id: str,
    raw_payload_id: str,
    provider: str,
    location_id: str,
    assessment: WeatherQualityAssessment,
) -> None:
    for issue in assessment.issues:
        add_weather_quality_issue(
            session,
            quality_issue_id=_new_id("weather_quality"),
            ingestion_run_id=ingestion_run_id,
            raw_payload_id=raw_payload_id,
            weather_record_id=issue.record_content_hash,
            provider=provider,
            location_id=location_id,
            forecast_time=issue.forecast_time,
            variable=issue.variable,
            issue_code=issue.issue_code,
            severity=issue.severity,
            message=issue.message,
            details_json=issue.details or {},
            data_mode=PUBLIC_DERIVED,
        )


def _get_or_add_feature_snapshot(
    session: Session,
    *,
    draft: WeatherFeatureDraft,
    ingestion_run_id: str,
    raw_payload_id: str,
    provider: str,
    location_id: str,
    generated_at: datetime,
) -> WeatherFeatureSnapshot:
    snapshot = get_weather_feature_snapshot(session, draft.content_hash)
    if snapshot is not None:
        if snapshot.forecast_start is None:
            snapshot.forecast_start = draft.forecast_start
        return snapshot
    return add_weather_feature_snapshot(
        session,
        feature_snapshot_id=draft.content_hash,
        ingestion_run_id=ingestion_run_id,
        raw_payload_id=raw_payload_id,
        provider=provider,
        location_id=location_id,
        generated_at=generated_at,
        forecast_start=draft.forecast_start,
        feature_version=draft.feature_version,
        quality_status=draft.quality_status,
        features_json=draft.features,
        evidence_json=draft.evidence,
        missing_data_warnings_json=draft.missing_data_warnings,
        content_hash=draft.content_hash,
        data_mode=PUBLIC_DERIVED,
    )


def _to_record_response(record: WeatherRecord) -> WeatherRecordResponse:
    return WeatherRecordResponse(
        weather_record_id=record.weather_record_id,
        raw_payload_id=record.raw_payload_id,
        provider=record.provider,
        location_id=record.location_id,
        issue_time=record.issue_time,
        forecast_time=record.forecast_time,
        variable=record.variable,
        value=record.value,
        unit=record.unit,
        data_mode=record.data_mode,
        quality_flag=record.quality_flag,
    )


def _to_feature_snapshot_response(
    snapshot: WeatherFeatureSnapshot,
) -> WeatherFeatureSnapshotResponse:
    return WeatherFeatureSnapshotResponse.model_validate(
        {
            "feature_snapshot_id": snapshot.feature_snapshot_id,
            "ingestion_run_id": snapshot.ingestion_run_id,
            "raw_payload_id": snapshot.raw_payload_id,
            "provider": snapshot.provider,
            "location_id": snapshot.location_id,
            "generated_at": snapshot.generated_at,
            "forecast_start": snapshot.forecast_start,
            "feature_version": snapshot.feature_version,
            "quality_status": snapshot.quality_status,
            "human_review_status": snapshot.human_review_status,
            "features": snapshot.features_json,
            "evidence": snapshot.evidence_json,
            "missing_data_warnings": snapshot.missing_data_warnings_json,
            "data_mode": snapshot.data_mode,
        }
    )


def _ensure_weather_feature_snapshot_can_be_approved(snapshot: WeatherFeatureSnapshot) -> None:
    blockers = _weather_feature_approval_blockers(snapshot)
    if blockers:
        raise WeatherFeatureSnapshotNotUsableError(
            snapshot.feature_snapshot_id,
            "; ".join(blockers),
        )


def _weather_feature_approval_blockers(snapshot: WeatherFeatureSnapshot) -> list[str]:
    blockers: list[str] = []
    if snapshot.quality_status != "valid":
        blockers.append("quality status must be valid before approval")
    if snapshot.forecast_start is None:
        blockers.append("forecast window start is missing")
    missing = sorted(
        feature
        for feature in REQUIRED_HYDRO_WEATHER_FEATURES
        if snapshot.features_json.get(feature) is None
    )
    if missing:
        blockers.append(f"required derived features are missing: {', '.join(missing)}")
    return blockers


def _quality_issue_summary(
    issues: list[WeatherQualityIssue],
    *,
    displayed_count: int,
) -> WeatherQualityIssueSummary:
    severity_counts = Counter(issue.severity for issue in issues)
    issue_code_counts = Counter(issue.issue_code for issue in issues)
    return WeatherQualityIssueSummary(
        total_count=len(issues),
        severity_counts=dict(severity_counts),
        issue_code_counts=dict(issue_code_counts),
        displayed_issue_count=displayed_count,
    )


def _to_feature_review_response(review: WeatherFeatureReview) -> WeatherFeatureReviewResponse:
    return WeatherFeatureReviewResponse(
        review_id=review.review_id,
        feature_snapshot_id=review.feature_snapshot_id,
        created_at=review.created_at,
        actor=review.actor,
        review_status=cast(WeatherFeatureReviewAction, review.review_status),
        note=review.note,
    )


def _to_quality_issue_response(issue: WeatherQualityIssue) -> WeatherQualityIssueResponse:
    return WeatherQualityIssueResponse(
        quality_issue_id=issue.quality_issue_id,
        ingestion_run_id=issue.ingestion_run_id,
        raw_payload_id=issue.raw_payload_id,
        weather_record_id=issue.weather_record_id,
        provider=issue.provider,
        location_id=issue.location_id,
        forecast_time=issue.forecast_time,
        variable=issue.variable,
        issue_code=issue.issue_code,
        severity=issue.severity,
        message=issue.message,
        details=issue.details_json,
        data_mode=issue.data_mode,
    )


def _hash_failed_payload(*, provider: str, location_id: str, raw_content: str) -> str:
    serialized = json.dumps(
        {
            "provider": provider,
            "location_id": location_id,
            "raw_content": raw_content,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()
