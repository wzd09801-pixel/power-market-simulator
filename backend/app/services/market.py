from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import cast
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.core.errors import (
    MarketArtifactRejectedError,
    MarketSourceEndpointNotFoundError,
)
from backend.app.models.market import (
    MarketArtifactReview,
    MarketDataSource,
    MarketIngestionRun,
    MarketParsingRun,
    MarketQualityIssue,
    MarketRawArtifact,
    MarketSourceEndpoint,
)
from backend.app.repositories.market import (
    add_market_ingestion_run,
    add_market_ingestion_run_item,
    add_market_quality_issue,
    add_market_raw_artifact,
    get_market_endpoint,
    get_market_raw_artifact,
    get_market_raw_artifact_by_source_hash,
    get_market_source,
    list_market_artifact_reviews,
    list_market_endpoints,
    list_market_ingestion_runs,
    list_market_parsing_runs,
    list_market_quality_issues,
    list_market_quality_issues_for_artifact,
    list_market_raw_artifacts,
    list_market_sources,
)
from backend.app.schemas.market import (
    ManualMarketArtifactRequest,
    ManualMarketArtifactResponse,
    MarketArtifactReviewAction,
    MarketArtifactReviewPackageArtifactResponse,
    MarketArtifactReviewPackageResponse,
    MarketArtifactReviewResponse,
    MarketDataSourceListResponse,
    MarketDataSourceResponse,
    MarketIngestionRunListResponse,
    MarketIngestionRunResponse,
    MarketParsingRunResponse,
    MarketQualityIssueListResponse,
    MarketQualityIssueResponse,
    MarketQualityIssueSummary,
    MarketRawArtifactListResponse,
    MarketRawArtifactResponse,
    MarketSourceEndpointListResponse,
    MarketSourceEndpointResponse,
)

logger = logging.getLogger(__name__)

PUBLIC_OBSERVED = "public_observed"
PUBLIC_DERIVED = "public_derived"
MANUAL_SUBMISSION = "manual_submission"
POSTGRES_INLINE = "postgres_inline"
MARKET_ARTIFACT_REVIEW_PACKAGE_VERSION = "market_artifact_review_package_v1"


@dataclass(frozen=True)
class MarketQualityFinding:
    issue_scope: str
    issue_code: str
    severity: str
    message: str
    details: dict[str, object]


def _now() -> datetime:
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def get_market_sources(*, session: Session) -> MarketDataSourceListResponse:
    return MarketDataSourceListResponse(
        items=[_to_source_response(source) for source in list_market_sources(session)]
    )


def get_market_endpoints(
    *, source_id: str | None, session: Session
) -> MarketSourceEndpointListResponse:
    return MarketSourceEndpointListResponse(
        items=[
            _to_endpoint_response(endpoint)
            for endpoint in list_market_endpoints(session, source_id=source_id)
        ]
    )


def preserve_manual_market_artifact(
    request: ManualMarketArtifactRequest,
    *,
    session: Session,
) -> ManualMarketArtifactResponse:
    started_at = _now()
    source_url = str(request.source_url)
    with session.begin():
        endpoint = get_market_endpoint(session, request.endpoint_id)
        source = get_market_source(session, endpoint.source_id) if endpoint is not None else None
    if endpoint is None or source is None:
        raise MarketSourceEndpointNotFoundError(request.endpoint_id)

    validation_error = _get_source_url_validation_error(endpoint, source_url)
    if validation_error is not None:
        code, message = validation_error
        _persist_rejected_manual_item(
            session=session,
            source=source,
            endpoint=endpoint,
            source_url=source_url,
            started_at=started_at,
            code=code,
            message=message,
        )
        raise MarketArtifactRejectedError(code=code, message=message)

    captured_at = _now()
    content_sha256 = sha256(request.inline_text.encode("utf-8")).hexdigest()
    ingestion_run_id = _new_id("market_ingest")
    ingestion_run_item_id = _new_id("market_item")
    with session.begin():
        artifact = get_market_raw_artifact_by_source_hash(
            session,
            source_id=source.source_id,
            content_sha256=content_sha256,
        )
        duplicate_artifact = artifact is not None
        if artifact is None:
            artifact = add_market_raw_artifact(
                session,
                artifact_id=_new_id("market_artifact"),
                source_id=source.source_id,
                endpoint_id=endpoint.endpoint_id,
                source_url=source_url,
                title=request.title,
                media_type=request.media_type,
                storage_backend=POSTGRES_INLINE,
                inline_text=request.inline_text,
                object_key=None,
                content_sha256=content_sha256,
                byte_length=len(request.inline_text.encode("utf-8")),
                published_at=request.published_at,
                captured_at=captured_at,
                ingestion_method=MANUAL_SUBMISSION,
                transport_security_status=_transport_security_status(source_url),
                data_mode=PUBLIC_OBSERVED,
            )
        findings = _assess_artifact(
            endpoint,
            source_url=source_url,
            published_at=request.published_at,
            duplicate_artifact=duplicate_artifact,
        )
        quality_status = _quality_status(findings)
        add_market_ingestion_run(
            session,
            ingestion_run_id=ingestion_run_id,
            source_id=source.source_id,
            endpoint_id=endpoint.endpoint_id,
            trigger_mode=MANUAL_SUBMISSION,
            adapter_key=None,
            adapter_version=None,
            started_at=started_at,
            completed_at=captured_at,
            status="succeeded",
            items_received=1,
            items_inserted=0 if duplicate_artifact else 1,
            duplicate_items=1 if duplicate_artifact else 0,
            rejected_items=0,
            quality_status=quality_status,
            quality_issue_count=len(findings),
        )
        item = add_market_ingestion_run_item(
            session,
            ingestion_run_item_id=ingestion_run_item_id,
            ingestion_run_id=ingestion_run_id,
            artifact_id=artifact.artifact_id,
            source_url=source_url,
            item_status="duplicate" if duplicate_artifact else "inserted",
        )
        _add_quality_findings(
            session,
            source_id=source.source_id,
            endpoint_id=endpoint.endpoint_id,
            ingestion_run_id=ingestion_run_id,
            ingestion_run_item_id=item.ingestion_run_item_id,
            artifact_id=artifact.artifact_id,
            findings=findings,
        )

    logger.info(
        "Preserved manual market artifact run=%s source=%s endpoint=%s duplicate=%s issues=%s",
        ingestion_run_id,
        source.source_id,
        endpoint.endpoint_id,
        duplicate_artifact,
        len(findings),
    )
    return ManualMarketArtifactResponse(
        ingestion_run_id=ingestion_run_id,
        ingestion_run_item_id=ingestion_run_item_id,
        artifact_id=artifact.artifact_id,
        source_id=source.source_id,
        endpoint_id=endpoint.endpoint_id,
        status="succeeded",
        item_status="duplicate" if duplicate_artifact else "inserted",
        captured_at=captured_at,
        content_sha256=content_sha256,
        duplicate_artifact=duplicate_artifact,
        quality_status=quality_status,
        quality_issue_count=len(findings),
        data_mode=PUBLIC_OBSERVED,
    )


def get_market_artifacts(
    *,
    source_id: str | None,
    endpoint_id: str | None,
    limit: int,
    session: Session,
) -> MarketRawArtifactListResponse:
    artifacts = list_market_raw_artifacts(
        session,
        source_id=source_id,
        endpoint_id=endpoint_id,
        limit=limit,
    )
    return MarketRawArtifactListResponse(
        items=[_to_artifact_response(artifact) for artifact in artifacts]
    )


def get_market_ingestion_runs(
    *,
    source_id: str | None,
    endpoint_id: str | None,
    status: str | None,
    limit: int,
    session: Session,
) -> MarketIngestionRunListResponse:
    runs = list_market_ingestion_runs(
        session,
        source_id=source_id,
        endpoint_id=endpoint_id,
        status=status,
        limit=limit,
    )
    return MarketIngestionRunListResponse(items=[_to_run_response(run) for run in runs])


def get_market_quality_issues(
    *,
    source_id: str | None,
    endpoint_id: str | None,
    issue_code: str | None,
    limit: int,
    session: Session,
) -> MarketQualityIssueListResponse:
    issues = list_market_quality_issues(
        session,
        source_id=source_id,
        endpoint_id=endpoint_id,
        issue_code=issue_code,
        limit=limit,
    )
    return MarketQualityIssueListResponse(
        items=[_to_quality_issue_response(issue) for issue in issues]
    )


def get_market_artifact_review_package(
    artifact_id: str,
    *,
    session: Session,
    issue_limit: int = 50,
    parsing_run_limit: int = 20,
) -> MarketArtifactReviewPackageResponse:
    artifact = get_market_raw_artifact(session, artifact_id)
    if artifact is None:
        from backend.app.core.errors import MarketRawArtifactNotFoundError

        raise MarketRawArtifactNotFoundError(artifact_id)
    source = get_market_source(session, artifact.source_id)
    endpoint = get_market_endpoint(session, artifact.endpoint_id)
    all_issues = list_market_quality_issues_for_artifact(
        session,
        artifact_id,
        limit=1000,
    )
    displayed_issues = all_issues[:issue_limit]
    reviews = list_market_artifact_reviews(session, artifact_id)
    parsing_runs = list_market_parsing_runs(
        session,
        artifact_id=artifact_id,
        limit=parsing_run_limit,
    )
    return MarketArtifactReviewPackageResponse(
        package_version=MARKET_ARTIFACT_REVIEW_PACKAGE_VERSION,
        generated_at=_now(),
        artifact=_to_artifact_package_response(artifact),
        source=_to_source_response(source) if source is not None else None,
        endpoint=_to_endpoint_response(endpoint) if endpoint is not None else None,
        quality_issue_summary=_quality_issue_summary(
            all_issues,
            displayed_count=len(displayed_issues),
        ),
        quality_issues=[_to_quality_issue_response(issue) for issue in displayed_issues],
        reviews=[_to_artifact_review_response(review) for review in reviews],
        parsing_runs=[_to_parsing_run_response(run) for run in parsing_runs],
        no_auto_trading=True,
        recommendation_chain_isolated=True,
        network_probe_performed=False,
        fetch_performed=False,
        parse_performed=False,
    )


def _persist_rejected_manual_item(
    *,
    session: Session,
    source: MarketDataSource,
    endpoint: MarketSourceEndpoint,
    source_url: str,
    started_at: datetime,
    code: str,
    message: str,
) -> None:
    completed_at = _now()
    ingestion_run_id = _new_id("market_ingest")
    ingestion_run_item_id = _new_id("market_item")
    with session.begin():
        add_market_ingestion_run(
            session,
            ingestion_run_id=ingestion_run_id,
            source_id=source.source_id,
            endpoint_id=endpoint.endpoint_id,
            trigger_mode=MANUAL_SUBMISSION,
            adapter_key=None,
            adapter_version=None,
            started_at=started_at,
            completed_at=completed_at,
            status="failed",
            items_received=1,
            items_inserted=0,
            duplicate_items=0,
            rejected_items=1,
            quality_status="failed",
            quality_issue_count=0,
            error_code=code,
            error_message=message,
        )
        add_market_ingestion_run_item(
            session,
            ingestion_run_item_id=ingestion_run_item_id,
            ingestion_run_id=ingestion_run_id,
            artifact_id=None,
            source_url=source_url,
            item_status="rejected",
            error_code=code,
            error_message=message,
        )
    logger.warning(
        "Rejected manual market artifact run=%s source=%s endpoint=%s code=%s",
        ingestion_run_id,
        source.source_id,
        endpoint.endpoint_id,
        code,
    )


def _get_source_url_validation_error(
    endpoint: MarketSourceEndpoint, source_url: str
) -> tuple[str, str] | None:
    parsed = urlparse(source_url)
    if parsed.username is not None or parsed.password is not None:
        return (
            "market_source_url_not_allowed",
            "Manual market artifact source URLs must not include credentials.",
        )
    if parsed.scheme not in {"http", "https"}:
        return (
            "market_source_url_not_allowed",
            "Manual market artifact source URLs must use HTTP or HTTPS.",
        )
    if parsed.port not in {None, 80, 443}:
        return (
            "market_source_url_not_allowed",
            "Manual market artifact source URLs must not use custom ports.",
        )
    if parsed.scheme == "http" and parsed.port not in {None, 80}:
        return (
            "market_source_url_not_allowed",
            "HTTP source URLs must use the standard port.",
        )
    if parsed.scheme == "https" and parsed.port not in {None, 443}:
        return (
            "market_source_url_not_allowed",
            "HTTPS source URLs must use the standard port.",
        )
    hostname = parsed.hostname.lower() if parsed.hostname is not None else None
    allowed_domains = {domain.lower() for domain in endpoint.allowed_domains_json}
    if hostname not in allowed_domains:
        return (
            "market_source_url_not_allowed",
            f"Source URL host is not registered for endpoint '{endpoint.endpoint_id}'.",
        )
    if not endpoint.manual_submission_enabled:
        return (
            "market_endpoint_not_open_for_manual_submission",
            f"Endpoint '{endpoint.endpoint_id}' is not open for manual artifact submission.",
        )
    if endpoint.access_mode not in {
        "anonymous_https",
        "anonymous_http_only",
        "manual_submission_only",
    }:
        return (
            "market_endpoint_not_open_for_manual_submission",
            f"Endpoint '{endpoint.endpoint_id}' is not open for manual artifact submission.",
        )
    if parsed.scheme != "https" and endpoint.access_mode == "anonymous_https":
        return (
            "market_source_url_not_allowed",
            f"Endpoint '{endpoint.endpoint_id}' requires an HTTPS source URL.",
        )
    return None


def _assess_artifact(
    endpoint: MarketSourceEndpoint,
    *,
    source_url: str,
    published_at: datetime | None,
    duplicate_artifact: bool,
) -> list[MarketQualityFinding]:
    findings: list[MarketQualityFinding] = []
    if published_at is None:
        findings.append(
            MarketQualityFinding(
                issue_scope="artifact",
                issue_code="missing_published_at",
                severity="warning",
                message="The public artifact publication timestamp was not provided.",
                details={},
            )
        )
    if endpoint.lifecycle_status != "verified":
        findings.append(
            MarketQualityFinding(
                issue_scope="endpoint",
                issue_code="endpoint_candidate_unverified",
                severity="warning",
                message="The endpoint remains unverified for automated structured ingestion.",
                details={"lifecycle_status": endpoint.lifecycle_status},
            )
        )
    if urlparse(source_url).scheme == "http":
        findings.append(
            MarketQualityFinding(
                issue_scope="artifact",
                issue_code="insecure_transport_source",
                severity="warning",
                message=(
                    "The submitted public source URL uses HTTP because trusted HTTPS "
                    "is unavailable."
                ),
                details={"access_mode": endpoint.access_mode},
            )
        )
    if duplicate_artifact:
        findings.append(
            MarketQualityFinding(
                issue_scope="artifact",
                issue_code="duplicate_artifact",
                severity="info",
                message="The same source artifact content was already preserved.",
                details={},
            )
        )
    return findings


def _quality_status(findings: list[MarketQualityFinding]) -> str:
    return "warning" if any(finding.severity == "warning" for finding in findings) else "valid"


def _transport_security_status(source_url: str) -> str:
    if urlparse(source_url).scheme == "https":
        return "tls_verified_source_url"
    return "insecure_http_source"


def _add_quality_findings(
    session: Session,
    *,
    source_id: str,
    endpoint_id: str,
    ingestion_run_id: str,
    ingestion_run_item_id: str,
    artifact_id: str,
    findings: list[MarketQualityFinding],
) -> None:
    for finding in findings:
        add_market_quality_issue(
            session,
            quality_issue_id=_new_id("market_quality"),
            source_id=source_id,
            endpoint_id=endpoint_id,
            ingestion_run_id=ingestion_run_id,
            ingestion_run_item_id=ingestion_run_item_id,
            parsing_run_id=None,
            endpoint_health_check_id=None,
            artifact_id=artifact_id,
            issue_scope=finding.issue_scope,
            issue_code=finding.issue_code,
            severity=finding.severity,
            message=finding.message,
            details_json=finding.details,
            data_mode=PUBLIC_DERIVED,
        )


def _to_source_response(source: MarketDataSource) -> MarketDataSourceResponse:
    return MarketDataSourceResponse(
        source_id=source.source_id,
        name=source.name,
        operator_name=source.operator_name,
        official_url=source.official_url,
        market_scope=source.market_scope,
        notes=source.notes,
        data_mode=source.data_mode,
        trust_tier=source.trust_tier,
        attribution_text=source.attribution_text,
        collection_permission_note=source.collection_permission_note,
    )


def _to_endpoint_response(endpoint: MarketSourceEndpoint) -> MarketSourceEndpointResponse:
    return MarketSourceEndpointResponse(
        endpoint_id=endpoint.endpoint_id,
        source_id=endpoint.source_id,
        name=endpoint.name,
        canonical_url=endpoint.canonical_url,
        endpoint_kind=endpoint.endpoint_kind,
        allowed_domains=endpoint.allowed_domains_json,
        visibility_scope=endpoint.visibility_scope,
        access_mode=endpoint.access_mode,
        lifecycle_status=endpoint.lifecycle_status,
        content_formats=endpoint.content_formats_json,
        data_granularity=endpoint.data_granularity,
        adapter_key=endpoint.adapter_key,
        parser_key=endpoint.parser_key,
        parser_version=endpoint.parser_version,
        health_check_enabled=endpoint.health_check_enabled,
        manual_submission_enabled=endpoint.manual_submission_enabled,
        collection_enabled=endpoint.collection_enabled,
        health_probe_not_before=endpoint.health_probe_not_before,
        cadence=endpoint.cadence,
        notes=endpoint.notes,
    )


def _to_artifact_response(artifact: MarketRawArtifact) -> MarketRawArtifactResponse:
    return MarketRawArtifactResponse(
        artifact_id=artifact.artifact_id,
        source_id=artifact.source_id,
        endpoint_id=artifact.endpoint_id,
        source_url=artifact.source_url,
        title=artifact.title,
        media_type=artifact.media_type,
        storage_backend=artifact.storage_backend,
        inline_text=artifact.inline_text,
        object_key=artifact.object_key,
        content_sha256=artifact.content_sha256,
        byte_length=artifact.byte_length,
        published_at=artifact.published_at,
        captured_at=artifact.captured_at,
        ingestion_method=artifact.ingestion_method,
        transport_security_status=artifact.transport_security_status,
        human_review_status=artifact.human_review_status,
        data_mode=artifact.data_mode,
    )


def _to_artifact_package_response(
    artifact: MarketRawArtifact,
) -> MarketArtifactReviewPackageArtifactResponse:
    return MarketArtifactReviewPackageArtifactResponse(
        artifact_id=artifact.artifact_id,
        source_id=artifact.source_id,
        endpoint_id=artifact.endpoint_id,
        source_url=artifact.source_url,
        title=artifact.title,
        media_type=artifact.media_type,
        storage_backend=artifact.storage_backend,
        inline_text_available=artifact.inline_text is not None,
        object_key=artifact.object_key,
        content_sha256=artifact.content_sha256,
        byte_length=artifact.byte_length,
        published_at=artifact.published_at,
        captured_at=artifact.captured_at,
        ingestion_method=artifact.ingestion_method,
        transport_security_status=artifact.transport_security_status,
        human_review_status=artifact.human_review_status,
        data_mode=artifact.data_mode,
    )


def _to_run_response(run: MarketIngestionRun) -> MarketIngestionRunResponse:
    return MarketIngestionRunResponse(
        ingestion_run_id=run.ingestion_run_id,
        source_id=run.source_id,
        endpoint_id=run.endpoint_id,
        trigger_mode=run.trigger_mode,
        adapter_key=run.adapter_key,
        adapter_version=run.adapter_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        items_received=run.items_received,
        items_inserted=run.items_inserted,
        duplicate_items=run.duplicate_items,
        rejected_items=run.rejected_items,
        quality_status=run.quality_status,
        quality_issue_count=run.quality_issue_count,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _to_quality_issue_response(issue: MarketQualityIssue) -> MarketQualityIssueResponse:
    return MarketQualityIssueResponse(
        quality_issue_id=issue.quality_issue_id,
        source_id=issue.source_id,
        endpoint_id=issue.endpoint_id,
        ingestion_run_id=issue.ingestion_run_id,
        ingestion_run_item_id=issue.ingestion_run_item_id,
        parsing_run_id=issue.parsing_run_id,
        endpoint_health_check_id=issue.endpoint_health_check_id,
        artifact_id=issue.artifact_id,
        issue_scope=issue.issue_scope,
        issue_code=issue.issue_code,
        severity=issue.severity,
        message=issue.message,
        details=issue.details_json,
        data_mode=issue.data_mode,
    )


def _to_artifact_review_response(review: MarketArtifactReview) -> MarketArtifactReviewResponse:
    return MarketArtifactReviewResponse(
        review_id=review.review_id,
        artifact_id=review.artifact_id,
        created_at=review.created_at,
        actor=review.actor,
        review_status=cast(MarketArtifactReviewAction, review.review_status),
        note=review.note,
    )


def _to_parsing_run_response(run: MarketParsingRun) -> MarketParsingRunResponse:
    return MarketParsingRunResponse(
        parsing_run_id=run.parsing_run_id,
        artifact_id=run.artifact_id,
        parser_key=run.parser_key,
        parser_version=run.parser_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        observations_parsed=run.observations_parsed,
        observations_inserted=run.observations_inserted,
        duplicate_observations=run.duplicate_observations,
        quality_status=run.quality_status,
        quality_issue_count=run.quality_issue_count,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _quality_issue_summary(
    issues: list[MarketQualityIssue],
    *,
    displayed_count: int,
) -> MarketQualityIssueSummary:
    severity_counts = Counter(issue.severity for issue in issues)
    issue_code_counts = Counter(issue.issue_code for issue in issues)
    return MarketQualityIssueSummary(
        total_count=len(issues),
        severity_counts=dict(severity_counts),
        issue_code_counts=dict(issue_code_counts),
        displayed_issue_count=displayed_count,
    )
