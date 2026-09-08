from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from backend.app.models.market import (
    MarketArtifactReview,
    MarketDataSource,
    MarketEndpointHealthCheck,
    MarketIngestionRun,
    MarketIngestionRunItem,
    MarketObservation,
    MarketParsingRun,
    MarketQualityIssue,
    MarketRawArtifact,
    MarketSourceEndpoint,
)


def get_market_source(session: Session, source_id: str) -> MarketDataSource | None:
    return session.get(MarketDataSource, source_id)


def list_market_sources(session: Session) -> list[MarketDataSource]:
    return list(session.scalars(select(MarketDataSource).order_by(MarketDataSource.source_id)))


def get_market_endpoint(session: Session, endpoint_id: str) -> MarketSourceEndpoint | None:
    return session.get(MarketSourceEndpoint, endpoint_id)


def list_market_endpoints(session: Session, *, source_id: str | None) -> list[MarketSourceEndpoint]:
    statement = select(MarketSourceEndpoint)
    if source_id is not None:
        statement = statement.where(MarketSourceEndpoint.source_id == source_id)
    return list(session.scalars(statement.order_by(MarketSourceEndpoint.endpoint_id)))


def acquire_market_endpoint_health_probe_lease(
    session: Session,
    *,
    endpoint_id: str,
    acquired_at: datetime,
    probe_not_before: datetime,
) -> bool:
    statement = (
        update(MarketSourceEndpoint)
        .where(
            MarketSourceEndpoint.endpoint_id == endpoint_id,
            MarketSourceEndpoint.health_check_enabled.is_(True),
            or_(
                MarketSourceEndpoint.health_probe_not_before.is_(None),
                MarketSourceEndpoint.health_probe_not_before <= acquired_at,
            ),
        )
        .values(health_probe_not_before=probe_not_before)
        .returning(MarketSourceEndpoint.endpoint_id)
        .execution_options(synchronize_session=False)
    )
    return session.scalar(statement) is not None


def add_market_raw_artifact(
    session: Session,
    *,
    artifact_id: str,
    source_id: str,
    endpoint_id: str,
    source_url: str,
    title: str | None,
    media_type: str,
    storage_backend: str,
    inline_text: str | None,
    object_key: str | None,
    content_sha256: str,
    byte_length: int,
    published_at: datetime | None,
    captured_at: datetime,
    ingestion_method: str,
    transport_security_status: str,
    data_mode: str,
) -> MarketRawArtifact:
    artifact = MarketRawArtifact(
        artifact_id=artifact_id,
        source_id=source_id,
        endpoint_id=endpoint_id,
        source_url=source_url,
        title=title,
        media_type=media_type,
        storage_backend=storage_backend,
        inline_text=inline_text,
        object_key=object_key,
        content_sha256=content_sha256,
        byte_length=byte_length,
        published_at=published_at,
        captured_at=captured_at,
        ingestion_method=ingestion_method,
        transport_security_status=transport_security_status,
        data_mode=data_mode,
    )
    session.add(artifact)
    return artifact


def get_market_raw_artifact_by_source_hash(
    session: Session, *, source_id: str, content_sha256: str
) -> MarketRawArtifact | None:
    statement = select(MarketRawArtifact).where(
        MarketRawArtifact.source_id == source_id,
        MarketRawArtifact.content_sha256 == content_sha256,
    )
    return session.scalar(statement)


def get_market_raw_artifact(session: Session, artifact_id: str) -> MarketRawArtifact | None:
    return session.get(MarketRawArtifact, artifact_id)


def list_market_raw_artifacts(
    session: Session,
    *,
    source_id: str | None,
    endpoint_id: str | None,
    limit: int,
) -> list[MarketRawArtifact]:
    statement = select(MarketRawArtifact)
    if source_id is not None:
        statement = statement.where(MarketRawArtifact.source_id == source_id)
    if endpoint_id is not None:
        statement = statement.where(MarketRawArtifact.endpoint_id == endpoint_id)
    statement = statement.order_by(MarketRawArtifact.captured_at.desc()).limit(limit)
    return list(session.scalars(statement))


def add_market_ingestion_run(
    session: Session,
    *,
    ingestion_run_id: str,
    source_id: str,
    endpoint_id: str,
    trigger_mode: str,
    adapter_key: str | None,
    adapter_version: str | None,
    started_at: datetime,
    completed_at: datetime,
    status: str,
    items_received: int,
    items_inserted: int,
    duplicate_items: int,
    rejected_items: int,
    quality_status: str,
    quality_issue_count: int,
    error_code: str | None = None,
    error_message: str | None = None,
) -> MarketIngestionRun:
    run = MarketIngestionRun(
        ingestion_run_id=ingestion_run_id,
        source_id=source_id,
        endpoint_id=endpoint_id,
        trigger_mode=trigger_mode,
        adapter_key=adapter_key,
        adapter_version=adapter_version,
        started_at=started_at,
        completed_at=completed_at,
        status=status,
        items_received=items_received,
        items_inserted=items_inserted,
        duplicate_items=duplicate_items,
        rejected_items=rejected_items,
        quality_status=quality_status,
        quality_issue_count=quality_issue_count,
        error_code=error_code,
        error_message=error_message,
    )
    session.add(run)
    return run


def add_market_ingestion_run_item(
    session: Session,
    *,
    ingestion_run_item_id: str,
    ingestion_run_id: str,
    artifact_id: str | None,
    source_url: str,
    item_status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> MarketIngestionRunItem:
    item = MarketIngestionRunItem(
        ingestion_run_item_id=ingestion_run_item_id,
        ingestion_run_id=ingestion_run_id,
        artifact_id=artifact_id,
        source_url=source_url,
        item_status=item_status,
        error_code=error_code,
        error_message=error_message,
    )
    session.add(item)
    return item


def list_market_ingestion_runs(
    session: Session,
    *,
    source_id: str | None,
    endpoint_id: str | None,
    status: str | None,
    limit: int,
) -> list[MarketIngestionRun]:
    statement = select(MarketIngestionRun)
    if source_id is not None:
        statement = statement.where(MarketIngestionRun.source_id == source_id)
    if endpoint_id is not None:
        statement = statement.where(MarketIngestionRun.endpoint_id == endpoint_id)
    if status is not None:
        statement = statement.where(MarketIngestionRun.status == status)
    statement = statement.order_by(MarketIngestionRun.completed_at.desc()).limit(limit)
    return list(session.scalars(statement))


def add_market_quality_issue(
    session: Session,
    *,
    quality_issue_id: str,
    source_id: str,
    endpoint_id: str | None,
    ingestion_run_id: str | None,
    ingestion_run_item_id: str | None,
    parsing_run_id: str | None,
    endpoint_health_check_id: str | None,
    artifact_id: str | None,
    issue_scope: str,
    issue_code: str,
    severity: str,
    message: str,
    details_json: dict[str, Any],
    data_mode: str,
) -> MarketQualityIssue:
    issue = MarketQualityIssue(
        quality_issue_id=quality_issue_id,
        source_id=source_id,
        endpoint_id=endpoint_id,
        ingestion_run_id=ingestion_run_id,
        ingestion_run_item_id=ingestion_run_item_id,
        parsing_run_id=parsing_run_id,
        endpoint_health_check_id=endpoint_health_check_id,
        artifact_id=artifact_id,
        issue_scope=issue_scope,
        issue_code=issue_code,
        severity=severity,
        message=message,
        details_json=details_json,
        data_mode=data_mode,
    )
    session.add(issue)
    return issue


def list_market_quality_issues(
    session: Session,
    *,
    source_id: str | None,
    endpoint_id: str | None,
    issue_code: str | None,
    limit: int,
) -> list[MarketQualityIssue]:
    statement = select(MarketQualityIssue)
    if source_id is not None:
        statement = statement.where(MarketQualityIssue.source_id == source_id)
    if endpoint_id is not None:
        statement = statement.where(MarketQualityIssue.endpoint_id == endpoint_id)
    if issue_code is not None:
        statement = statement.where(MarketQualityIssue.issue_code == issue_code)
    statement = statement.order_by(MarketQualityIssue.created_at.desc()).limit(limit)
    return list(session.scalars(statement))


def list_market_quality_issues_for_artifact(
    session: Session,
    artifact_id: str,
    *,
    limit: int,
) -> list[MarketQualityIssue]:
    statement = (
        select(MarketQualityIssue)
        .where(MarketQualityIssue.artifact_id == artifact_id)
        .order_by(MarketQualityIssue.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def add_market_endpoint_health_check(
    session: Session,
    *,
    endpoint_health_check_id: str,
    endpoint_id: str,
    checked_at: datetime,
    probe_url: str,
    probe_method: str,
    health_status: str,
    dns_status: str,
    tcp_status: str,
    tls_status: str,
    http_status: str,
    status_code: int | None,
    resolved_addresses_json: list[str],
    connected_address: str | None,
    attempt_count: int,
    duration_ms: int,
    redirect_location: str | None,
    error_code: str | None,
    error_message: str | None,
    data_mode: str,
) -> MarketEndpointHealthCheck:
    check = MarketEndpointHealthCheck(
        endpoint_health_check_id=endpoint_health_check_id,
        endpoint_id=endpoint_id,
        checked_at=checked_at,
        probe_url=probe_url,
        probe_method=probe_method,
        health_status=health_status,
        dns_status=dns_status,
        tcp_status=tcp_status,
        tls_status=tls_status,
        http_status=http_status,
        status_code=status_code,
        resolved_addresses_json=resolved_addresses_json,
        connected_address=connected_address,
        attempt_count=attempt_count,
        duration_ms=duration_ms,
        redirect_location=redirect_location,
        error_code=error_code,
        error_message=error_message,
        data_mode=data_mode,
    )
    session.add(check)
    return check


def list_market_endpoint_health_checks(
    session: Session,
    *,
    endpoint_id: str | None,
    limit: int,
) -> list[MarketEndpointHealthCheck]:
    statement = select(MarketEndpointHealthCheck)
    if endpoint_id is not None:
        statement = statement.where(MarketEndpointHealthCheck.endpoint_id == endpoint_id)
    statement = statement.order_by(MarketEndpointHealthCheck.checked_at.desc()).limit(limit)
    return list(session.scalars(statement))


def add_market_artifact_review(
    session: Session,
    *,
    review_id: str,
    artifact_id: str,
    created_at: datetime,
    actor: str,
    review_status: str,
    note: str,
) -> MarketArtifactReview:
    review = MarketArtifactReview(
        review_id=review_id,
        artifact_id=artifact_id,
        created_at=created_at,
        actor=actor,
        review_status=review_status,
        note=note,
    )
    session.add(review)
    return review


def list_market_artifact_reviews(
    session: Session,
    artifact_id: str,
) -> list[MarketArtifactReview]:
    statement = (
        select(MarketArtifactReview)
        .where(MarketArtifactReview.artifact_id == artifact_id)
        .order_by(MarketArtifactReview.created_at.desc())
    )
    return list(session.scalars(statement))


def add_market_parsing_run(
    session: Session,
    *,
    parsing_run_id: str,
    artifact_id: str,
    parser_key: str,
    parser_version: str,
    started_at: datetime,
    completed_at: datetime,
    status: str,
    observations_parsed: int,
    observations_inserted: int,
    duplicate_observations: int,
    quality_status: str,
    quality_issue_count: int,
    error_code: str | None = None,
    error_message: str | None = None,
) -> MarketParsingRun:
    run = MarketParsingRun(
        parsing_run_id=parsing_run_id,
        artifact_id=artifact_id,
        parser_key=parser_key,
        parser_version=parser_version,
        started_at=started_at,
        completed_at=completed_at,
        status=status,
        observations_parsed=observations_parsed,
        observations_inserted=observations_inserted,
        duplicate_observations=duplicate_observations,
        quality_status=quality_status,
        quality_issue_count=quality_issue_count,
        error_code=error_code,
        error_message=error_message,
    )
    session.add(run)
    return run


def list_market_parsing_runs(
    session: Session, *, artifact_id: str | None, limit: int
) -> list[MarketParsingRun]:
    statement = select(MarketParsingRun)
    if artifact_id is not None:
        statement = statement.where(MarketParsingRun.artifact_id == artifact_id)
    statement = statement.order_by(MarketParsingRun.completed_at.desc()).limit(limit)
    return list(session.scalars(statement))


def get_market_observation(
    session: Session,
    *,
    artifact_id: str,
    parser_key: str,
    parser_version: str,
    area_code: str,
    market_stage: str,
    metric: str,
) -> MarketObservation | None:
    statement = select(MarketObservation).where(
        MarketObservation.artifact_id == artifact_id,
        MarketObservation.parser_key == parser_key,
        MarketObservation.parser_version == parser_version,
        MarketObservation.area_code == area_code,
        MarketObservation.market_stage == market_stage,
        MarketObservation.metric == metric,
    )
    return session.scalar(statement)


def add_market_observation(
    session: Session,
    *,
    observation_id: str,
    artifact_id: str,
    parsing_run_id: str,
    parser_key: str,
    parser_version: str,
    period_start: date,
    period_end: date,
    area_scope: str,
    area_code: str,
    area_name: str,
    market_stage: str,
    participant_side: str,
    metric: str,
    value: Decimal,
    unit: str,
    settlement_status: str,
    data_mode: str,
) -> MarketObservation:
    observation = MarketObservation(
        observation_id=observation_id,
        artifact_id=artifact_id,
        parsing_run_id=parsing_run_id,
        parser_key=parser_key,
        parser_version=parser_version,
        period_start=period_start,
        period_end=period_end,
        area_scope=area_scope,
        area_code=area_code,
        area_name=area_name,
        market_stage=market_stage,
        participant_side=participant_side,
        metric=metric,
        value=value,
        unit=unit,
        settlement_status=settlement_status,
        data_mode=data_mode,
    )
    session.add(observation)
    return observation


def list_market_observations(
    session: Session,
    *,
    artifact_id: str | None,
    area_code: str | None,
    market_stage: str | None,
    metric: str | None,
    limit: int,
) -> list[MarketObservation]:
    statement = select(MarketObservation)
    if artifact_id is not None:
        statement = statement.where(MarketObservation.artifact_id == artifact_id)
    if area_code is not None:
        statement = statement.where(MarketObservation.area_code == area_code)
    if market_stage is not None:
        statement = statement.where(MarketObservation.market_stage == market_stage)
    if metric is not None:
        statement = statement.where(MarketObservation.metric == metric)
    statement = statement.order_by(
        MarketObservation.period_end.desc(),
        MarketObservation.area_code,
        MarketObservation.market_stage,
        MarketObservation.metric,
    ).limit(limit)
    return list(session.scalars(statement))
