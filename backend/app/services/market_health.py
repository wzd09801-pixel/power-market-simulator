from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.adapters.market_endpoint_health import (
    MarketEndpointHealthClient,
    MarketEndpointProbeResult,
    MarketEndpointProbeTarget,
)
from backend.app.core.config import get_settings
from backend.app.core.errors import (
    MarketEndpointProbeNotAllowedError,
    MarketEndpointProbeRateLimitedError,
    MarketSourceEndpointNotFoundError,
)
from backend.app.models.market import MarketEndpointHealthCheck, MarketSourceEndpoint
from backend.app.repositories.market import (
    acquire_market_endpoint_health_probe_lease,
    add_market_endpoint_health_check,
    add_market_quality_issue,
    get_market_endpoint,
    list_market_endpoint_health_checks,
)
from backend.app.schemas.market import (
    MarketEndpointHealthCheckListResponse,
    MarketEndpointHealthCheckResponse,
)

logger = logging.getLogger(__name__)

PUBLIC_DERIVED = "public_derived"
PROBEABLE_ACCESS_MODES = frozenset({"anonymous_https", "anonymous_http_only"})
BLOCKED_VISIBILITY_SCOPES = frozenset({"market_participant_public", "restricted"})


@dataclass(frozen=True)
class MarketHealthFinding:
    issue_code: str
    message: str
    details: dict[str, object]


def _now() -> datetime:
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def get_market_endpoint_health_client() -> MarketEndpointHealthClient:
    settings = get_settings()
    return MarketEndpointHealthClient(
        timeout_seconds=settings.market_health_timeout_seconds,
        max_retries=settings.market_health_max_retries,
        retry_backoff_seconds=settings.market_health_retry_backoff_seconds,
    )


def probe_market_endpoint(
    endpoint_id: str,
    *,
    session: Session,
    client: MarketEndpointHealthClient,
) -> MarketEndpointHealthCheckResponse:
    checked_at = _now()
    settings = get_settings()
    with session.begin():
        endpoint = get_market_endpoint(session, endpoint_id)
        if endpoint is None:
            raise MarketSourceEndpointNotFoundError(endpoint_id)
        _ensure_endpoint_can_be_probed(endpoint)
        source_id = endpoint.source_id
        probe_target = MarketEndpointProbeTarget(
            endpoint_id=endpoint.endpoint_id,
            canonical_url=endpoint.canonical_url,
            allowed_domains=tuple(endpoint.allowed_domains_json),
        )
        lease_acquired = acquire_market_endpoint_health_probe_lease(
            session,
            endpoint_id=endpoint.endpoint_id,
            acquired_at=checked_at,
            probe_not_before=checked_at
            + timedelta(seconds=settings.market_health_min_interval_seconds),
        )
    if not lease_acquired:
        raise MarketEndpointProbeRateLimitedError(endpoint_id)

    result = client.probe(probe_target)
    endpoint_health_check_id = _new_id("market_health")
    findings = _assess_result(result)
    with session.begin():
        check = add_market_endpoint_health_check(
            session,
            endpoint_health_check_id=endpoint_health_check_id,
            endpoint_id=endpoint_id,
            checked_at=checked_at,
            probe_url=result.probe_url,
            probe_method=result.probe_method,
            health_status=result.health_status,
            dns_status=result.dns_status,
            tcp_status=result.tcp_status,
            tls_status=result.tls_status,
            http_status=result.http_status,
            status_code=result.status_code,
            resolved_addresses_json=list(result.resolved_addresses),
            connected_address=result.connected_address,
            attempt_count=result.attempt_count,
            duration_ms=result.duration_ms,
            redirect_location=result.redirect_location,
            error_code=result.error_code,
            error_message=result.error_message,
            data_mode=result.data_mode,
        )
        for finding in findings:
            add_market_quality_issue(
                session,
                quality_issue_id=_new_id("market_quality"),
                source_id=source_id,
                endpoint_id=endpoint_id,
                ingestion_run_id=None,
                ingestion_run_item_id=None,
                parsing_run_id=None,
                endpoint_health_check_id=check.endpoint_health_check_id,
                artifact_id=None,
                issue_scope="endpoint_health_check",
                issue_code=finding.issue_code,
                severity="warning",
                message=finding.message,
                details_json=finding.details,
                data_mode=PUBLIC_DERIVED,
            )
    logger.info(
        "Completed market endpoint health probe check=%s endpoint=%s status=%s issues=%s",
        endpoint_health_check_id,
        endpoint_id,
        result.health_status,
        len(findings),
    )
    return _to_health_check_response(check)


def get_market_endpoint_health_checks(
    *,
    endpoint_id: str | None,
    limit: int,
    session: Session,
) -> MarketEndpointHealthCheckListResponse:
    return MarketEndpointHealthCheckListResponse(
        items=[
            _to_health_check_response(check)
            for check in list_market_endpoint_health_checks(
                session,
                endpoint_id=endpoint_id,
                limit=limit,
            )
        ]
    )


def _ensure_endpoint_can_be_probed(endpoint: MarketSourceEndpoint) -> None:
    if not endpoint.health_check_enabled:
        raise MarketEndpointProbeNotAllowedError(
            endpoint.endpoint_id,
            "health checking is disabled",
        )
    if endpoint.visibility_scope in BLOCKED_VISIBILITY_SCOPES:
        raise MarketEndpointProbeNotAllowedError(
            endpoint.endpoint_id,
            f"visibility scope is {endpoint.visibility_scope}",
        )
    if endpoint.access_mode not in PROBEABLE_ACCESS_MODES:
        raise MarketEndpointProbeNotAllowedError(
            endpoint.endpoint_id,
            f"access mode is {endpoint.access_mode}",
        )


def _assess_result(result: MarketEndpointProbeResult) -> list[MarketHealthFinding]:
    findings: list[MarketHealthFinding] = []
    if result.error_code is not None:
        findings.append(
            MarketHealthFinding(
                issue_code=result.error_code,
                message=result.error_message or "Market endpoint health probe failed.",
                details={
                    "dns_status": result.dns_status,
                    "tcp_status": result.tcp_status,
                    "tls_status": result.tls_status,
                    "http_status": result.http_status,
                    "resolved_addresses": list(result.resolved_addresses),
                    "connected_address": result.connected_address,
                },
            )
        )
    if urlparse(result.probe_url).scheme == "http":
        findings.append(
            MarketHealthFinding(
                issue_code="market_endpoint_insecure_http_transport",
                message="The registered public market endpoint is reachable only over HTTP.",
                details={"probe_url": result.probe_url},
            )
        )
    if result.status_code is not None and 300 <= result.status_code < 400:
        findings.append(
            MarketHealthFinding(
                issue_code="market_endpoint_http_redirect",
                message=(
                    "The market endpoint returned a redirect that was recorded but not followed."
                ),
                details={
                    "status_code": result.status_code,
                    "redirect_location": result.redirect_location,
                },
            )
        )
    elif result.status_code is not None and result.status_code >= 400:
        findings.append(
            MarketHealthFinding(
                issue_code="market_endpoint_http_unhealthy_status",
                message=f"The market endpoint returned HTTP {result.status_code}.",
                details={"status_code": result.status_code},
            )
        )
    return findings


def _to_health_check_response(
    check: MarketEndpointHealthCheck,
) -> MarketEndpointHealthCheckResponse:
    return MarketEndpointHealthCheckResponse(
        endpoint_health_check_id=check.endpoint_health_check_id,
        endpoint_id=check.endpoint_id,
        checked_at=check.checked_at,
        probe_url=check.probe_url,
        probe_method=check.probe_method,
        health_status=check.health_status,
        dns_status=check.dns_status,
        tcp_status=check.tcp_status,
        tls_status=check.tls_status,
        http_status=check.http_status,
        status_code=check.status_code,
        resolved_addresses=check.resolved_addresses_json,
        connected_address=check.connected_address,
        attempt_count=check.attempt_count,
        duration_ms=check.duration_ms,
        redirect_location=check.redirect_location,
        error_code=check.error_code,
        error_message=check.error_message,
        data_mode=check.data_mode,
    )
