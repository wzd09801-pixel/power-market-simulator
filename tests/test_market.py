from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.market import (
    MarketArtifactReview,
    MarketDataSource,
    MarketIngestionRun,
    MarketIngestionRunItem,
    MarketObservation,
    MarketParsingRun,
    MarketQualityIssue,
    MarketRawArtifact,
    MarketSourceEndpoint,
)

REPORTS_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "reports_weekly_market_report_example.html"
)


@pytest.fixture(autouse=True)
def seeded_market_sources(db_session_factory: sessionmaker[Session]) -> Iterator[None]:
    with db_session_factory.begin() as session:
        session.add_all(
            [
                MarketDataSource(
                    source_id="example_province_power_trading_portal",
                    name="Example Province Power Trading Portal",
                    operator_name="Example Market Exchange",
                    official_url="https://portal.market.example.invalid/portal/",
                    market_scope="example_province_power_market_disclosure_candidate",
                    notes="Anonymous frontend shell only.",
                    data_mode="public_derived",
                ),
                MarketDataSource(
                    source_id="example_region_power_exchange_center",
                    name="Example Regional Exchange",
                    operator_name="Example Regional Exchange Co., Ltd.",
                    official_url="https://reports.market.example.invalid/",
                    market_scope="southern_regional_market_disclosure",
                    notes="Regional disclosure source.",
                    data_mode="public_derived",
                ),
            ]
        )
        session.add_all(
            [
                MarketSourceEndpoint(
                    endpoint_id="example_province_portal_home",
                    source_id="example_province_power_trading_portal",
                    name="Example Province portal public frontend",
                    canonical_url="https://portal.market.example.invalid/portal/",
                    endpoint_kind="public_frontend",
                    allowed_domains_json=["portal.market.example.invalid"],
                    visibility_scope="internet_public",
                    access_mode="anonymous_https",
                    lifecycle_status="candidate_unverified",
                    content_formats_json=["text/html"],
                    data_granularity="frontend_shell_only",
                    health_check_enabled=True,
                    manual_submission_enabled=True,
                    collection_enabled=False,
                    notes="Structured API remains unverified.",
                ),
                MarketSourceEndpoint(
                    endpoint_id="reports_market_research",
                    source_id="example_region_power_exchange_center",
                    name="REPORTS market research column",
                    canonical_url="http://reports.market.example.invalid/news/scyj/",
                    endpoint_kind="html_listing",
                    allowed_domains_json=["reports.market.example.invalid"],
                    visibility_scope="internet_public",
                    access_mode="anonymous_http_only",
                    lifecycle_status="blocked_tls",
                    content_formats_json=["text/html"],
                    data_granularity="weekly_and_monthly_regional_reports",
                    parser_key="reports_weekly_market_report",
                    health_check_enabled=True,
                    manual_submission_enabled=True,
                    collection_enabled=False,
                    cadence="weekly",
                    notes="Trusted HTTPS currently fails hostname validation.",
                ),
                MarketSourceEndpoint(
                    endpoint_id="reports_market_research_https_candidate",
                    source_id="example_region_power_exchange_center",
                    name="REPORTS market research HTTPS candidate",
                    canonical_url="https://reports.market.example.invalid/news/scyj/",
                    endpoint_kind="html_listing_https_candidate",
                    allowed_domains_json=["reports.market.example.invalid"],
                    visibility_scope="internet_public",
                    access_mode="anonymous_https",
                    lifecycle_status="blocked_tls",
                    content_formats_json=["text/html"],
                    data_granularity="weekly_and_monthly_regional_reports",
                    health_check_enabled=True,
                    manual_submission_enabled=False,
                    collection_enabled=False,
                    cadence="weekly",
                    notes="Read-only health-check candidate.",
                ),
            ]
        )
    yield


def artifact_payload() -> dict[str, object]:
    return {
        "endpoint_id": "example_province_portal_home",
        "source_url": "https://portal.market.example.invalid/portal/disclosures/example",
        "title": "Public market artifact example",
        "media_type": "text/html",
        "inline_text": "<html><body>public artifact example</body></html>",
        "published_at": "2026-05-30T08:00:00+08:00",
    }


def reports_report_payload() -> dict[str, object]:
    return {
        "endpoint_id": "reports_market_research",
        "source_url": "http://reports.market.example.invalid/news/scyj/202605/t20260529_36410.html",
        "title": "Southern regional weekly market report",
        "media_type": "text/html",
        "inline_text": REPORTS_FIXTURE_PATH.read_text(encoding="utf-8"),
        "published_at": "2026-05-26T08:00:00+08:00",
    }


def test_market_source_and_endpoint_lists_keep_access_policy_separate(
    client: TestClient,
) -> None:
    sources_response = client.get("/v1/market/sources")
    endpoints_response = client.get("/v1/market/endpoints")

    assert sources_response.status_code == 200
    sources = {item["source_id"]: item for item in sources_response.json()["items"]}
    assert sources["example_region_power_exchange_center"]["market_scope"] == (
        "southern_regional_market_disclosure"
    )
    assert endpoints_response.status_code == 200
    endpoints = {item["endpoint_id"]: item for item in endpoints_response.json()["items"]}
    assert endpoints["example_province_portal_home"]["visibility_scope"] == "internet_public"
    assert endpoints["example_province_portal_home"]["access_mode"] == "anonymous_https"
    assert endpoints["example_province_portal_home"]["manual_submission_enabled"] is True
    assert endpoints["reports_market_research"]["lifecycle_status"] == "blocked_tls"
    assert endpoints["reports_market_research"]["collection_enabled"] is False
    assert endpoints["reports_market_research_https_candidate"]["health_check_enabled"] is True
    assert (
        endpoints["reports_market_research_https_candidate"]["manual_submission_enabled"] is False
    )


def test_manual_market_artifact_preserves_text_and_deduplicates_by_source(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    first = client.post("/v1/market/artifacts/manual", json=artifact_payload())
    second = client.post("/v1/market/artifacts/manual", json=artifact_payload())

    assert first.status_code == 200
    assert first.json()["duplicate_artifact"] is False
    assert first.json()["item_status"] == "inserted"
    assert first.json()["quality_status"] == "warning"
    assert first.json()["quality_issue_count"] == 1
    assert first.json()["data_mode"] == "public_observed"
    assert second.status_code == 200
    assert second.json()["artifact_id"] == first.json()["artifact_id"]
    assert second.json()["duplicate_artifact"] is True
    assert second.json()["item_status"] == "duplicate"
    assert second.json()["quality_issue_count"] == 2

    artifacts = client.get(
        "/v1/market/artifacts",
        params={"source_id": "example_province_power_trading_portal"},
    )
    assert artifacts.status_code == 200
    assert len(artifacts.json()["items"]) == 1
    artifact = artifacts.json()["items"][0]
    assert artifact["inline_text"] == artifact_payload()["inline_text"]
    assert artifact["storage_backend"] == "postgres_inline"
    assert artifact["object_key"] is None
    assert artifact["transport_security_status"] == "tls_verified_source_url"

    runs = client.get("/v1/market/ingestion/runs")
    assert runs.status_code == 200
    assert len(runs.json()["items"]) == 2
    with db_session_factory() as session:
        artifact_count = session.scalar(select(func.count()).select_from(MarketRawArtifact))
        run_count = session.scalar(select(func.count()).select_from(MarketIngestionRun))
        item_count = session.scalar(select(func.count()).select_from(MarketIngestionRunItem))
        issue_count = session.scalar(select(func.count()).select_from(MarketQualityIssue))

    assert artifact_count == 1
    assert run_count == 2
    assert item_count == 2
    assert issue_count == 3


def test_market_artifact_review_package_summarizes_artifact_without_raw_body(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact = client.post("/v1/market/artifacts/manual", json=artifact_payload()).json()
    artifact_id = artifact["artifact_id"]
    with db_session_factory() as session:
        before_counts = _market_counts(session)

    response = client.get(f"/v1/market/artifacts/{artifact_id}/review-package")

    with db_session_factory() as session:
        after_counts = _market_counts(session)
    assert response.status_code == 200
    assert before_counts == after_counts
    body = response.json()
    assert body["package_version"] == "market_artifact_review_package_v1"
    assert body["artifact"]["artifact_id"] == artifact_id
    assert body["artifact"]["inline_text_available"] is True
    assert "inline_text" not in body["artifact"]
    assert body["source"]["source_id"] == "example_province_power_trading_portal"
    assert body["endpoint"]["endpoint_id"] == "example_province_portal_home"
    assert body["quality_issue_summary"]["total_count"] == 1
    assert body["quality_issue_summary"]["issue_code_counts"] == {
        "endpoint_candidate_unverified": 1,
    }
    assert body["reviews"] == []
    assert body["parsing_runs"] == []
    assert body["no_auto_trading"] is True
    assert body["recommendation_chain_isolated"] is True
    assert body["network_probe_performed"] is False
    assert body["fetch_performed"] is False
    assert body["parse_performed"] is False


def test_market_artifact_review_package_includes_reviews_and_parse_history(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact = client.post("/v1/market/artifacts/manual", json=reports_report_payload()).json()
    artifact_id = artifact["artifact_id"]
    review = client.post(
        f"/v1/market/artifacts/{artifact_id}/reviews",
        json={"review_status": "approved", "note": "Reviewed preserved public HTML."},
    )
    parsing = client.post(f"/v1/market/artifacts/{artifact_id}/parse/reports-weekly-report")
    with db_session_factory() as session:
        before_counts = _market_counts(session)

    response = client.get(f"/v1/market/artifacts/{artifact_id}/review-package")

    with db_session_factory() as session:
        after_counts = _market_counts(session)
    assert review.status_code == 200
    assert parsing.status_code == 200
    assert response.status_code == 200
    assert before_counts == after_counts
    body = response.json()
    assert body["artifact"]["human_review_status"] == "approved"
    assert body["reviews"][0]["review_status"] == "approved"
    assert body["parsing_runs"][0]["parser_key"] == "reports_weekly_market_report"
    assert body["parsing_runs"][0]["parser_version"] == "v1"
    assert body["quality_issue_summary"]["issue_code_counts"] == {
        "endpoint_candidate_unverified": 1,
        "insecure_transport_source": 1,
        "power_type_section_not_normalized": 1,
    }
    assert body["parse_performed"] is False


def test_market_artifact_review_package_missing_artifact_returns_error(
    client: TestClient,
) -> None:
    response = client.get("/v1/market/artifacts/missing_artifact/review-package")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "market_raw_artifact_not_found"


def test_manual_market_artifact_preserves_missing_publication_warning(
    client: TestClient,
) -> None:
    payload = {**artifact_payload()}
    payload.pop("published_at")

    response = client.post("/v1/market/artifacts/manual", json=payload)

    assert response.status_code == 200
    assert response.json()["quality_status"] == "warning"
    assert response.json()["quality_issue_count"] == 2
    issues = client.get(
        "/v1/market/quality/issues",
        params={"issue_code": "missing_published_at"},
    )
    assert issues.status_code == 200
    assert len(issues.json()["items"]) == 1
    assert issues.json()["items"][0]["issue_scope"] == "artifact"
    assert issues.json()["items"][0]["data_mode"] == "public_derived"


def test_manual_market_artifact_accepts_registered_http_source_with_warning(
    client: TestClient,
) -> None:
    payload = {
        "endpoint_id": "reports_market_research",
        "source_url": "http://reports.market.example.invalid/news/scyj/202605/t20260529_36410.html",
        "title": "Southern regional weekly market report",
        "media_type": "text/html",
        "inline_text": "<html><body>weekly regional public report</body></html>",
        "published_at": "2026-05-26T08:00:00+08:00",
    }

    response = client.post("/v1/market/artifacts/manual", json=payload)

    assert response.status_code == 200
    assert response.json()["quality_issue_count"] == 2
    artifacts = client.get(
        "/v1/market/artifacts",
        params={"endpoint_id": "reports_market_research"},
    )
    assert artifacts.json()["items"][0]["transport_security_status"] == "insecure_http_source"
    issues = client.get(
        "/v1/market/quality/issues",
        params={"issue_code": "insecure_transport_source"},
    )
    assert len(issues.json()["items"]) == 1


def test_manual_market_artifact_deduplicates_same_text_separately_for_each_source(
    client: TestClient,
) -> None:
    first = client.post("/v1/market/artifacts/manual", json=artifact_payload())
    second_payload = {
        **artifact_payload(),
        "endpoint_id": "reports_market_research",
        "source_url": "http://reports.market.example.invalid/news/scyj/example.html",
    }
    second = client.post("/v1/market/artifacts/manual", json=second_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["artifact_id"] != second.json()["artifact_id"]
    assert second.json()["duplicate_artifact"] is False


def test_manual_market_artifact_rejects_unknown_endpoint(client: TestClient) -> None:
    payload = {**artifact_payload(), "endpoint_id": "unknown_endpoint"}

    response = client.post("/v1/market/artifacts/manual", json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "market_source_endpoint_not_found"


def test_manual_market_artifact_rejects_unregistered_domain_and_records_run_item(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    payload = {**artifact_payload(), "source_url": "https://example.com/public-data"}

    response = client.post("/v1/market/artifacts/manual", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "market_source_url_not_allowed"
    with db_session_factory() as session:
        run = session.scalar(select(MarketIngestionRun))
        item = session.scalar(select(MarketIngestionRunItem))

    assert run is not None
    assert run.status == "failed"
    assert run.rejected_items == 1
    assert run.error_code == "market_source_url_not_allowed"
    assert item is not None
    assert item.artifact_id is None
    assert item.item_status == "rejected"


def test_manual_market_artifact_rejects_http_for_https_endpoint(client: TestClient) -> None:
    payload = {
        **artifact_payload(),
        "source_url": "http://portal.market.example.invalid/portal/disclosures/example",
    }

    response = client.post("/v1/market/artifacts/manual", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "market_source_url_not_allowed"


def test_manual_market_artifact_rejects_health_only_https_candidate(client: TestClient) -> None:
    payload = {
        **artifact_payload(),
        "endpoint_id": "reports_market_research_https_candidate",
        "source_url": "https://reports.market.example.invalid/news/scyj/example.html",
    }

    response = client.post("/v1/market/artifacts/manual", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "market_endpoint_not_open_for_manual_submission"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("inline_text", "   "),
        ("media_type", "application/pdf"),
    ],
)
def test_manual_market_artifact_rejects_invalid_text_payload(
    client: TestClient,
    field: str,
    value: str,
) -> None:
    payload = {**artifact_payload(), field: value}

    response = client.post("/v1/market/artifacts/manual", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_market_quality_issue_can_record_endpoint_problem_without_artifact(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        session.add(
            MarketQualityIssue(
                quality_issue_id="market_quality_tls_example",
                source_id="example_region_power_exchange_center",
                endpoint_id="reports_market_research",
                ingestion_run_id=None,
                ingestion_run_item_id=None,
                artifact_id=None,
                issue_scope="endpoint",
                issue_code="tls_hostname_mismatch",
                severity="warning",
                message="Trusted HTTPS hostname validation failed.",
                details_json={},
                data_mode="public_derived",
            )
        )

    issues = client.get(
        "/v1/market/quality/issues",
        params={"endpoint_id": "reports_market_research"},
    )

    assert issues.status_code == 200
    assert issues.json()["items"][0]["artifact_id"] is None
    assert issues.json()["items"][0]["issue_scope"] == "endpoint"


def test_reports_weekly_report_requires_approved_artifact(client: TestClient) -> None:
    artifact = client.post("/v1/market/artifacts/manual", json=reports_report_payload()).json()

    response = client.post(
        f"/v1/market/artifacts/{artifact['artifact_id']}/parse/reports-weekly-report"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "market_artifact_not_usable"


def test_reports_weekly_report_review_parse_and_idempotent_replay(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact = client.post("/v1/market/artifacts/manual", json=reports_report_payload()).json()
    artifact_id = artifact["artifact_id"]
    review = client.post(
        f"/v1/market/artifacts/{artifact_id}/reviews",
        json={"review_status": "approved", "note": "Reviewed against the official HTML page."},
    )

    first = client.post(f"/v1/market/artifacts/{artifact_id}/parse/reports-weekly-report")
    second = client.post(f"/v1/market/artifacts/{artifact_id}/parse/reports-weekly-report")

    assert review.status_code == 200
    assert review.json()["review_status"] == "approved"
    assert first.status_code == 200
    assert first.json()["observations_parsed"] == 24
    assert first.json()["observations_inserted"] == 24
    assert first.json()["duplicate_observations"] == 0
    assert first.json()["quality_issue_count"] == 1
    assert second.status_code == 200
    assert second.json()["observations_inserted"] == 0
    assert second.json()["duplicate_observations"] == 24

    observations = client.get(
        "/v1/market/observations",
        params={
            "area_code": "GD",
            "market_stage": "real_time",
            "metric": "weighted_average_price",
        },
    )
    assert observations.status_code == 200
    assert len(observations.json()["items"]) == 1
    observation = observations.json()["items"][0]
    assert observation["value"] == "416.0000"
    assert observation["unit"] == "cny_per_mwh"
    assert observation["settlement_status"] == "preliminary_flash"
    assert observation["participant_side"] == "generation"

    artifacts = client.get(
        "/v1/market/artifacts", params={"endpoint_id": "reports_market_research"}
    )
    assert artifacts.json()["items"][0]["human_review_status"] == "approved"
    issues = client.get(
        "/v1/market/quality/issues",
        params={"issue_code": "power_type_section_not_normalized"},
    )
    assert len(issues.json()["items"]) == 2
    assert issues.json()["items"][0]["parsing_run_id"] is not None

    with db_session_factory() as session:
        observation_count = session.scalar(select(func.count()).select_from(MarketObservation))
        parsing_run_count = session.scalar(select(func.count()).select_from(MarketParsingRun))

    assert observation_count == 24
    assert parsing_run_count == 2


def test_reports_weekly_report_format_failure_records_parsing_run(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    payload = {
        **reports_report_payload(),
        "inline_text": "<html><body>format changed</body></html>",
    }
    artifact = client.post("/v1/market/artifacts/manual", json=payload).json()
    artifact_id = artifact["artifact_id"]
    client.post(
        f"/v1/market/artifacts/{artifact_id}/reviews",
        json={"review_status": "approved", "note": "Preserve parser failure for review."},
    )

    response = client.post(f"/v1/market/artifacts/{artifact_id}/parse/reports-weekly-report")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reports_weekly_report_period_missing"
    with db_session_factory() as session:
        run = session.scalar(select(MarketParsingRun))
    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "reports_weekly_report_period_missing"


def _market_counts(session: Session) -> dict[str, int]:
    return {
        "artifacts": int(session.scalar(select(func.count()).select_from(MarketRawArtifact)) or 0),
        "reviews": int(session.scalar(select(func.count()).select_from(MarketArtifactReview)) or 0),
        "parsing_runs": int(
            session.scalar(select(func.count()).select_from(MarketParsingRun)) or 0
        ),
        "quality_issues": int(
            session.scalar(select(func.count()).select_from(MarketQualityIssue)) or 0
        ),
        "observations": int(
            session.scalar(select(func.count()).select_from(MarketObservation)) or 0
        ),
    }
