from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.adapters.market_endpoint_health import (
    MarketEndpointProbeResult,
    MarketEndpointProbeTarget,
)
from backend.app.models.market import (
    MarketDataSource,
    MarketEndpointHealthCheck,
    MarketQualityIssue,
    MarketSourceEndpoint,
)
from backend.app.services.market_health import get_market_endpoint_health_client


class StaticProbeClient:
    def __init__(self, result: MarketEndpointProbeResult) -> None:
        self.result = result
        self.calls: list[MarketEndpointProbeTarget] = []

    def probe(self, target: MarketEndpointProbeTarget) -> MarketEndpointProbeResult:
        self.calls.append(target)
        return self.result


@pytest.fixture(autouse=True)
def seeded_market_endpoints(db_session_factory: sessionmaker[Session]) -> Iterator[None]:
    with db_session_factory.begin() as session:
        session.add(
            MarketDataSource(
                source_id="official_market_source",
                name="Official market source",
                operator_name="Official operator",
                official_url="https://example.com/",
                market_scope="public_market_candidate",
                notes="Test source.",
                data_mode="public_derived",
            )
        )
        session.add_all(
            [
                MarketSourceEndpoint(
                    endpoint_id="public_https",
                    source_id="official_market_source",
                    name="Public HTTPS endpoint",
                    canonical_url="https://example.com/public/",
                    endpoint_kind="public_frontend",
                    allowed_domains_json=["example.com"],
                    visibility_scope="internet_public",
                    access_mode="anonymous_https",
                    lifecycle_status="candidate_unverified",
                    content_formats_json=["text/html"],
                    data_granularity="frontend_shell_only",
                    health_check_enabled=True,
                    manual_submission_enabled=True,
                    collection_enabled=False,
                    notes="Health probe candidate.",
                ),
                MarketSourceEndpoint(
                    endpoint_id="public_http",
                    source_id="official_market_source",
                    name="Public HTTP endpoint",
                    canonical_url="http://example.com/public/",
                    endpoint_kind="html_listing",
                    allowed_domains_json=["example.com"],
                    visibility_scope="internet_public",
                    access_mode="anonymous_http_only",
                    lifecycle_status="blocked_tls",
                    content_formats_json=["text/html"],
                    data_granularity="public_reports",
                    health_check_enabled=True,
                    manual_submission_enabled=True,
                    collection_enabled=False,
                    notes="Manual preservation only.",
                ),
                MarketSourceEndpoint(
                    endpoint_id="member_login",
                    source_id="official_market_source",
                    name="Member login endpoint",
                    canonical_url="https://example.com/member/",
                    endpoint_kind="member_portal",
                    allowed_domains_json=["example.com"],
                    visibility_scope="market_participant_public",
                    access_mode="member_login_required",
                    lifecycle_status="disabled",
                    content_formats_json=["text/html"],
                    data_granularity="restricted",
                    health_check_enabled=False,
                    manual_submission_enabled=False,
                    collection_enabled=False,
                    notes="Must never be health probed.",
                ),
                MarketSourceEndpoint(
                    endpoint_id="health_only_https",
                    source_id="official_market_source",
                    name="Health-only HTTPS endpoint",
                    canonical_url="https://example.com/health-only/",
                    endpoint_kind="https_candidate",
                    allowed_domains_json=["example.com"],
                    visibility_scope="internet_public",
                    access_mode="anonymous_https",
                    lifecycle_status="blocked_tls",
                    content_formats_json=["text/html"],
                    data_granularity="candidate",
                    health_check_enabled=True,
                    manual_submission_enabled=False,
                    collection_enabled=False,
                    notes="Health probe only.",
                ),
            ]
        )
    yield


def result(
    *,
    endpoint_id: str = "public_https",
    probe_url: str = "https://example.com/public/",
    health_status: str = "healthy",
    dns_status: str = "succeeded",
    tcp_status: str = "succeeded",
    tls_status: str = "succeeded",
    http_status: str = "succeeded",
    status_code: int | None = 200,
    connected_address: str | None = "93.184.216.34",
    redirect_location: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> MarketEndpointProbeResult:
    return MarketEndpointProbeResult(
        endpoint_id=endpoint_id,
        probe_url=probe_url,
        probe_method="HEAD",
        health_status=health_status,
        dns_status=dns_status,
        tcp_status=tcp_status,
        tls_status=tls_status,
        http_status=http_status,
        status_code=status_code,
        resolved_addresses=("93.184.216.34",),
        connected_address=connected_address,
        attempt_count=1,
        duration_ms=12,
        redirect_location=redirect_location,
        error_code=error_code,
        error_message=error_message,
    )


def override_health_client(client: TestClient, probe_client: StaticProbeClient) -> None:
    cast(FastAPI, client.app).dependency_overrides[get_market_endpoint_health_client] = lambda: (
        probe_client
    )


def test_public_https_health_check_persists_result_without_enabling_collection(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    probe_client = StaticProbeClient(result())
    override_health_client(client, probe_client)

    response = client.post("/v1/market/endpoints/public_https/health-checks")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint_id"] == "public_https"
    assert body["health_status"] == "healthy"
    assert body["resolved_addresses"] == ["93.184.216.34"]
    assert body["connected_address"] == "93.184.216.34"
    assert body["data_mode"] == "public_derived"
    assert probe_client.calls == [
        MarketEndpointProbeTarget(
            endpoint_id="public_https",
            canonical_url="https://example.com/public/",
            allowed_domains=("example.com",),
        )
    ]
    checks = client.get("/v1/market/health/checks", params={"endpoint_id": "public_https"})
    assert checks.status_code == 200
    assert (
        checks.json()["items"][0]["endpoint_health_check_id"] == (body["endpoint_health_check_id"])
    )
    with db_session_factory() as session:
        endpoint = session.get(MarketSourceEndpoint, "public_https")
        persisted = session.scalar(select(MarketEndpointHealthCheck))
    assert endpoint is not None
    assert endpoint.collection_enabled is False
    assert endpoint.lifecycle_status == "candidate_unverified"
    assert persisted is not None
    assert persisted.probe_method == "HEAD"
    assert persisted.connected_address == "93.184.216.34"


def test_tls_failure_persists_linked_quality_issue(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    probe_client = StaticProbeClient(
        result(
            health_status="failed",
            tls_status="failed",
            http_status="skipped",
            status_code=None,
            error_code="market_endpoint_tls_validation_failed",
            error_message="TLS certificate validation failed.",
        )
    )
    override_health_client(client, probe_client)

    response = client.post("/v1/market/endpoints/public_https/health-checks")

    assert response.status_code == 200
    assert response.json()["error_code"] == "market_endpoint_tls_validation_failed"
    with db_session_factory() as session:
        check = session.scalar(select(MarketEndpointHealthCheck))
        issue = session.scalar(select(MarketQualityIssue))
    assert check is not None
    assert issue is not None
    assert issue.endpoint_health_check_id == check.endpoint_health_check_id
    assert issue.artifact_id is None
    assert issue.issue_code == "market_endpoint_tls_validation_failed"


def test_http_only_probe_persists_transport_warning(client: TestClient) -> None:
    probe_client = StaticProbeClient(
        result(
            endpoint_id="public_http",
            probe_url="http://example.com/public/",
            health_status="warning",
            tls_status="not_applicable",
        )
    )
    override_health_client(client, probe_client)

    response = client.post("/v1/market/endpoints/public_http/health-checks")
    issues = client.get(
        "/v1/market/quality/issues",
        params={"issue_code": "market_endpoint_insecure_http_transport"},
    )

    assert response.status_code == 200
    assert response.json()["health_status"] == "warning"
    assert len(issues.json()["items"]) == 1
    assert (
        issues.json()["items"][0]["endpoint_health_check_id"]
        == (response.json()["endpoint_health_check_id"])
    )


def test_unknown_endpoint_returns_404_without_probe(client: TestClient) -> None:
    probe_client = StaticProbeClient(result())
    override_health_client(client, probe_client)

    response = client.post("/v1/market/endpoints/missing/health-checks")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "market_source_endpoint_not_found"
    assert probe_client.calls == []


def test_member_login_endpoint_returns_409_without_probe(client: TestClient) -> None:
    probe_client = StaticProbeClient(result())
    override_health_client(client, probe_client)

    response = client.post("/v1/market/endpoints/member_login/health-checks")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "market_endpoint_probe_not_allowed"
    assert probe_client.calls == []


def test_health_check_post_rejects_caller_supplied_url_body(client: TestClient) -> None:
    probe_client = StaticProbeClient(result())
    override_health_client(client, probe_client)

    response = client.post(
        "/v1/market/endpoints/public_https/health-checks",
        json={"url": "http://127.0.0.1/admin"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert probe_client.calls == []


def test_health_only_https_candidate_can_be_probed(client: TestClient) -> None:
    probe_client = StaticProbeClient(
        result(
            endpoint_id="health_only_https",
            probe_url="https://example.com/health-only/",
        )
    )
    override_health_client(client, probe_client)

    response = client.post("/v1/market/endpoints/health_only_https/health-checks")

    assert response.status_code == 200
    assert response.json()["endpoint_id"] == "health_only_https"
    assert len(probe_client.calls) == 1


def test_immediate_repeat_is_rate_limited_without_external_probe(client: TestClient) -> None:
    probe_client = StaticProbeClient(result())
    override_health_client(client, probe_client)

    first = client.post("/v1/market/endpoints/public_https/health-checks")
    second = client.post("/v1/market/endpoints/public_https/health-checks")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "market_endpoint_probe_rate_limited"
    assert len(probe_client.calls) == 1


def test_probe_resumes_after_persisted_cooldown_expires(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    probe_client = StaticProbeClient(result())
    override_health_client(client, probe_client)

    first = client.post("/v1/market/endpoints/public_https/health-checks")
    with db_session_factory.begin() as session:
        endpoint = session.get(MarketSourceEndpoint, "public_https")
        assert endpoint is not None
        endpoint.health_probe_not_before = datetime.now(tz=ZoneInfo("Asia/Shanghai")) - timedelta(
            seconds=1
        )
    second = client.post("/v1/market/endpoints/public_https/health-checks")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(probe_client.calls) == 2


def test_redirect_without_location_persists_quality_warning(client: TestClient) -> None:
    probe_client = StaticProbeClient(
        result(
            health_status="warning",
            status_code=302,
            redirect_location=None,
        )
    )
    override_health_client(client, probe_client)

    response = client.post("/v1/market/endpoints/public_https/health-checks")
    issues = client.get(
        "/v1/market/quality/issues",
        params={"issue_code": "market_endpoint_http_redirect"},
    )

    assert response.status_code == 200
    assert response.json()["health_status"] == "warning"
    assert response.json()["redirect_location"] is None
    assert len(issues.json()["items"]) == 1
