from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.weather import (
    WeatherFeatureReview,
    WeatherFeatureSnapshot,
    WeatherIngestionRun,
    WeatherLocation,
    WeatherQualityIssue,
    WeatherRawPayload,
    WeatherRecord,
)


def add_weather_location(
    session: Session,
    *,
    location_id: str,
    name: str,
    latitude: float,
    longitude: float,
    timezone: str,
    data_mode: str,
    collection_enabled: bool = False,
    verification_status: str = "manual_input",
    source_url: str | None = None,
    notes: str = "",
) -> WeatherLocation:
    location = WeatherLocation(
        location_id=location_id,
        name=name,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        data_mode=data_mode,
        collection_enabled=collection_enabled,
        verification_status=verification_status,
        source_url=source_url,
        notes=notes,
    )
    session.add(location)
    return location


def get_weather_location(session: Session, location_id: str) -> WeatherLocation | None:
    return session.get(WeatherLocation, location_id)


def list_collection_enabled_weather_locations(session: Session) -> list[WeatherLocation]:
    statement = (
        select(WeatherLocation)
        .where(WeatherLocation.collection_enabled.is_(True))
        .order_by(WeatherLocation.location_id)
    )
    return list(session.scalars(statement))


def add_weather_raw_payload(
    session: Session,
    *,
    raw_payload_id: str,
    provider: str,
    location_id: str,
    fetched_at: datetime,
    request_url: str,
    request_params_json: dict[str, Any],
    payload_json: dict[str, Any] | None,
    raw_content: str,
    content_hash: str,
    data_mode: str,
    quality_flag: str,
) -> WeatherRawPayload:
    payload = WeatherRawPayload(
        raw_payload_id=raw_payload_id,
        provider=provider,
        location_id=location_id,
        fetched_at=fetched_at,
        request_url=request_url,
        request_params_json=request_params_json,
        payload_json=payload_json,
        raw_content=raw_content,
        content_hash=content_hash,
        data_mode=data_mode,
        quality_flag=quality_flag,
    )
    session.add(payload)
    return payload


def get_weather_raw_payload(session: Session, content_hash: str) -> WeatherRawPayload | None:
    statement = select(WeatherRawPayload).where(WeatherRawPayload.content_hash == content_hash)
    return session.scalar(statement)


def add_weather_ingestion_run(
    session: Session,
    *,
    ingestion_run_id: str,
    provider: str,
    location_id: str,
    started_at: datetime,
    completed_at: datetime,
    status: str,
    request_url: str,
    raw_payload_id: str | None,
    records_received: int,
    records_inserted: int,
    duplicate_records: int,
    quality_status: str,
    quality_issue_count: int,
    error_code: str | None = None,
    error_message: str | None = None,
) -> WeatherIngestionRun:
    run = WeatherIngestionRun(
        ingestion_run_id=ingestion_run_id,
        provider=provider,
        location_id=location_id,
        started_at=started_at,
        completed_at=completed_at,
        status=status,
        request_url=request_url,
        raw_payload_id=raw_payload_id,
        records_received=records_received,
        records_inserted=records_inserted,
        duplicate_records=duplicate_records,
        quality_status=quality_status,
        quality_issue_count=quality_issue_count,
        error_code=error_code,
        error_message=error_message,
    )
    session.add(run)
    return run


def add_weather_record(
    session: Session,
    *,
    weather_record_id: str,
    raw_payload_id: str,
    provider: str,
    location_id: str,
    issue_time: datetime,
    forecast_time: datetime,
    variable: str,
    value: float | None,
    unit: str,
    data_mode: str,
    quality_flag: str,
    content_hash: str,
) -> WeatherRecord:
    record = WeatherRecord(
        weather_record_id=weather_record_id,
        raw_payload_id=raw_payload_id,
        provider=provider,
        location_id=location_id,
        issue_time=issue_time,
        forecast_time=forecast_time,
        variable=variable,
        value=value,
        unit=unit,
        data_mode=data_mode,
        quality_flag=quality_flag,
        content_hash=content_hash,
    )
    session.add(record)
    return record


def get_weather_record(session: Session, content_hash: str) -> WeatherRecord | None:
    statement = select(WeatherRecord).where(WeatherRecord.content_hash == content_hash)
    return session.scalar(statement)


def list_weather_records(
    session: Session,
    *,
    location_id: str,
    variable: str | None,
    limit: int,
) -> list[WeatherRecord]:
    statement = select(WeatherRecord).where(WeatherRecord.location_id == location_id)
    if variable is not None:
        statement = statement.where(WeatherRecord.variable == variable)
    statement = statement.order_by(
        WeatherRecord.forecast_time.desc(),
        WeatherRecord.created_at.desc(),
    ).limit(limit)
    return list(session.scalars(statement))


def add_weather_quality_issue(
    session: Session,
    *,
    quality_issue_id: str,
    ingestion_run_id: str,
    raw_payload_id: str,
    weather_record_id: str | None,
    provider: str,
    location_id: str,
    forecast_time: datetime | None,
    variable: str | None,
    issue_code: str,
    severity: str,
    message: str,
    details_json: dict[str, object],
    data_mode: str,
) -> WeatherQualityIssue:
    issue = WeatherQualityIssue(
        quality_issue_id=quality_issue_id,
        ingestion_run_id=ingestion_run_id,
        raw_payload_id=raw_payload_id,
        weather_record_id=weather_record_id,
        provider=provider,
        location_id=location_id,
        forecast_time=forecast_time,
        variable=variable,
        issue_code=issue_code,
        severity=severity,
        message=message,
        details_json=details_json,
        data_mode=data_mode,
    )
    session.add(issue)
    return issue


def add_weather_feature_snapshot(
    session: Session,
    *,
    feature_snapshot_id: str,
    ingestion_run_id: str,
    raw_payload_id: str,
    provider: str,
    location_id: str,
    generated_at: datetime,
    forecast_start: datetime,
    feature_version: str,
    quality_status: str,
    features_json: dict[str, Any],
    evidence_json: list[dict[str, Any]],
    missing_data_warnings_json: list[str],
    content_hash: str,
    data_mode: str,
) -> WeatherFeatureSnapshot:
    snapshot = WeatherFeatureSnapshot(
        feature_snapshot_id=feature_snapshot_id,
        ingestion_run_id=ingestion_run_id,
        raw_payload_id=raw_payload_id,
        provider=provider,
        location_id=location_id,
        generated_at=generated_at,
        forecast_start=forecast_start,
        feature_version=feature_version,
        quality_status=quality_status,
        features_json=features_json,
        evidence_json=evidence_json,
        missing_data_warnings_json=missing_data_warnings_json,
        content_hash=content_hash,
        data_mode=data_mode,
    )
    session.add(snapshot)
    return snapshot


def get_weather_feature_snapshot(
    session: Session, content_hash: str
) -> WeatherFeatureSnapshot | None:
    statement = select(WeatherFeatureSnapshot).where(
        WeatherFeatureSnapshot.content_hash == content_hash
    )
    return session.scalar(statement)


def get_weather_feature_snapshot_by_id(
    session: Session, feature_snapshot_id: str
) -> WeatherFeatureSnapshot | None:
    return session.get(WeatherFeatureSnapshot, feature_snapshot_id)


def get_latest_weather_feature_snapshot(
    session: Session, location_id: str
) -> WeatherFeatureSnapshot | None:
    statement = (
        select(WeatherFeatureSnapshot)
        .where(WeatherFeatureSnapshot.location_id == location_id)
        .order_by(WeatherFeatureSnapshot.generated_at.desc())
        .limit(1)
    )
    return session.scalar(statement)


def list_weather_quality_issues(
    session: Session,
    *,
    location_id: str,
    issue_code: str | None,
    limit: int,
) -> list[WeatherQualityIssue]:
    statement = select(WeatherQualityIssue).where(WeatherQualityIssue.location_id == location_id)
    if issue_code is not None:
        statement = statement.where(WeatherQualityIssue.issue_code == issue_code)
    statement = statement.order_by(WeatherQualityIssue.created_at.desc()).limit(limit)
    return list(session.scalars(statement))


def add_weather_feature_review(
    session: Session,
    *,
    review_id: str,
    feature_snapshot_id: str,
    created_at: datetime,
    review_status: str,
    note: str,
    actor: str,
) -> WeatherFeatureReview:
    review = WeatherFeatureReview(
        review_id=review_id,
        feature_snapshot_id=feature_snapshot_id,
        created_at=created_at,
        actor=actor,
        review_status=review_status,
        note=note,
    )
    session.add(review)
    return review


def list_weather_feature_reviews(
    session: Session,
    feature_snapshot_id: str,
) -> list[WeatherFeatureReview]:
    statement = (
        select(WeatherFeatureReview)
        .where(WeatherFeatureReview.feature_snapshot_id == feature_snapshot_id)
        .order_by(WeatherFeatureReview.created_at.desc())
    )
    return list(session.scalars(statement))
