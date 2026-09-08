from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.forecasting import ForecastResearchDataset
from backend.app.models.intelligence import IntelligenceBrief
from backend.app.models.knowledge import KnowledgeDocument
from backend.app.models.market import MarketDataSource, MarketRawArtifact, MarketSourceEndpoint
from backend.app.models.operations import WorkflowRun
from backend.app.models.recommendation import RecommendationDecision, RecommendationRun
from backend.app.models.weather import WeatherFeatureSnapshot
from backend.app.schemas.operations import OperationsFreshnessItem, OperationsOverviewResponse
from backend.app.services.operations import (
    claim_operation_job,
    fail_operation_job,
    get_operations_overview,
    queue_operation_job,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
BENCH_REGIONS = ("NSW1", "QLD1", "SA1", "TAS1", "VIC1")


def test_operations_overview_empty_database_is_warning_without_probing(
    client: TestClient,
) -> None:
    response = client.get("/v1/operations/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] == "warning"
    assert body["workflow_overview"]["queued"] == 0
    assert body["no_auto_trading"] is True
    assert {item["key"] for item in body["freshness"]} == {
        "weather_features",
        "daily_brief",
        "bench_dispatch_research",
        "policy_documents",
    }
    endpoint_health = _json_item(body["health"], "endpoint_health")
    assert endpoint_health["details"]["network_probe_performed"] is False
    assert {item["job_key"] for item in body["actions"]} == {
        "weather_refresh",
        "policy_research_refresh",
        "bench_dispatch_research",
        "daily_intelligence_brief",
        "demo_research_workspace_seed",
    }


def test_operation_action_center_empty_database_returns_freshness_todos(
    client: TestClient,
) -> None:
    response = client.get("/v1/operations/action-center")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "warning"
    assert body["counts"]["warning"] >= 1
    assert body["no_auto_trading"] is True
    freshness_items = [item for item in body["items"] if item["category"] == "data_freshness"]
    freshness_targets = {item["target_id"] for item in freshness_items}
    assert {"weather_features", "bench_dispatch_research"}.issubset(freshness_targets)
    assert all(item["target_type"] == "freshness" for item in freshness_items)
    assert any(item["job_key"] == "weather_refresh" for item in freshness_items)
    assert any(item["job_key"] == "bench_dispatch_research" for item in freshness_items)


def test_operations_review_package_empty_database_is_read_only(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        before_counts = _table_counts(session)

    response = client.get("/v1/operations/review-package")

    with db_session_factory() as session:
        after_counts = _table_counts(session)
    assert response.status_code == 200
    assert before_counts == after_counts
    body = response.json()
    assert body["package_version"] == "operations_review_package_v1"
    assert body["no_auto_trading"] is True
    assert body["manual_job_keys_only"] is True
    assert body["network_probe_performed"] is False
    assert body["fetch_performed"] is False
    assert body["overview"]["no_auto_trading"] is True
    assert body["action_center"]["no_auto_trading"] is True
    assert body["system_readiness"]["no_auto_trading"] is True
    assert body["fixed_job_keys"] == [
        "weather_refresh",
        "policy_research_refresh",
        "bench_dispatch_research",
        "daily_intelligence_brief",
        "demo_research_workspace_seed",
    ]
    assert body["overview"]["health"][1]["details"]["network_probe_performed"] is False


def test_operations_review_package_includes_recent_runs_and_action_counts(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        queued = queue_operation_job("weather_refresh", session=session)
    with db_session_factory() as session:
        before_counts = _table_counts(session)

    response = client.get("/v1/operations/review-package")

    with db_session_factory() as session:
        after_counts = _table_counts(session)
    assert response.status_code == 200
    assert before_counts == after_counts
    body = response.json()
    assert body["overview"]["workflow_overview"]["queued"] == 1
    assert body["action_center"]["counts"]["total"] >= 1
    assert body["recent_runs"][0]["workflow_run_id"] == queued.workflow_run_id
    assert body["recent_runs"][0]["workflow_key"] == "weather_refresh"


def test_operations_overview_escalates_failed_and_retry_wait_workflows(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        failed_run = queue_operation_job("weather_refresh", session=session)
    now = failed_run.started_at + timedelta(seconds=1)
    with db_session_factory() as session:
        claimed = claim_operation_job(
            worker_id="worker-one",
            session=session,
            claimed_at=now,
        )
    assert claimed is not None
    with db_session_factory() as session:
        fail_operation_job(
            failed_run.workflow_run_id,
            worker_id="worker-one",
            lease_token=claimed.lease_token,
            code="open_meteo_network_error",
            message="offline",
            summary={"message": "offline"},
            transient=False,
            session=session,
            failed_at=now,
        )
    with db_session_factory() as session:
        retry_run = queue_operation_job("policy_research_refresh", session=session)
    with db_session_factory() as session:
        claimed_retry = claim_operation_job(
            worker_id="worker-two",
            session=session,
            claimed_at=now,
        )
    assert claimed_retry is not None
    with db_session_factory() as session:
        fail_operation_job(
            retry_run.workflow_run_id,
            worker_id="worker-two",
            lease_token=claimed_retry.lease_token,
            code="workstation_storage_error",
            message="temporary storage issue",
            summary={"message": "retry later"},
            transient=True,
            session=session,
            failed_at=now,
        )
    with db_session_factory() as session:
        overview = get_operations_overview(session=session, now=now)

    assert overview.overall_status == "critical"
    assert overview.workflow_overview["failed"] == 1
    assert overview.workflow_overview["retry_wait"] == 1
    assert overview.workflow_overview["failed_last_24h"] == 1
    assert {run.workflow_key for run in overview.recent_incidents} == {
        "weather_refresh",
        "policy_research_refresh",
    }
    recommended = {action.job_key for action in overview.actions if action.recommended}
    assert {"weather_refresh", "policy_research_refresh"}.issubset(recommended)


def test_operation_action_center_collects_operator_review_and_workflow_todos(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    decision = client.post(
        f"/v1/recommendations/{generated['recommendation_id']}/decisions",
        json={
            "decision_status": "deferred",
            "selected_windows": [],
            "note": "Wait for observed outcome.",
            "safety_boundary_acknowledged": True,
        },
    )
    assert decision.status_code == 200
    with db_session_factory.begin() as session:
        _add_today_brief(
            session,
            now=datetime(2026, 6, 3, 9, 0, tzinfo=SHANGHAI),
        )
    with db_session_factory() as session:
        failed_run = queue_operation_job("weather_refresh", session=session)
    now = failed_run.started_at + timedelta(seconds=1)
    with db_session_factory() as session:
        claimed = claim_operation_job(
            worker_id="action-center-worker",
            session=session,
            claimed_at=now,
        )
    assert claimed is not None
    with db_session_factory() as session:
        fail_operation_job(
            failed_run.workflow_run_id,
            worker_id="action-center-worker",
            lease_token=claimed.lease_token,
            code="open_meteo_network_error",
            message="offline",
            summary={"message": "offline"},
            transient=False,
            session=session,
            failed_at=now,
        )
    with db_session_factory() as session:
        before_counts = _table_counts(session)

    response = client.get("/v1/operations/action-center?limit=20")
    limited_response = client.get("/v1/operations/action-center?limit=1")

    with db_session_factory() as session:
        after_counts = _table_counts(session)
    assert response.status_code == 200
    assert limited_response.status_code == 200
    body = response.json()
    limited_body = limited_response.json()
    categories = {item["category"] for item in body["items"]}
    assert body["status"] == "critical"
    assert len(limited_body["items"]) == 1
    assert limited_body["counts"]["total"] > len(limited_body["items"])
    assert before_counts == after_counts
    assert {
        "workflow",
        "brief_review",
        "recommendation_review",
        "decision_feedback",
    }.issubset(categories)
    workflow_item = next(item for item in body["items"] if item["category"] == "workflow")
    assert workflow_item["severity"] == "critical"
    assert workflow_item["job_key"] == "weather_refresh"
    assert workflow_item["navigation_target_type"] is None
    assert workflow_item["navigation_target_id"] is None
    brief_item = next(item for item in body["items"] if item["category"] == "brief_review")
    assert brief_item["navigation_target_type"] == "intelligence_brief"
    assert brief_item["navigation_target_id"] == "brief_today"
    recommendation_item = next(
        item for item in body["items"] if item["category"] == "recommendation_review"
    )
    assert recommendation_item["target_id"] == generated["recommendation_id"]
    assert recommendation_item["navigation_target_type"] == "recommendation"
    assert recommendation_item["navigation_target_id"] == generated["recommendation_id"]
    decision_item = next(item for item in body["items"] if item["category"] == "decision_feedback")
    assert decision_item["target_type"] == "recommendation_decision"
    assert decision_item["navigation_target_type"] == "recommendation"
    assert decision_item["navigation_target_id"] == generated["recommendation_id"]
    assert decision_item["job_key"] is None


def test_operation_action_center_collects_data_review_todos_without_mutating_state(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    captured_at = datetime(2026, 6, 3, 8, 0, tzinfo=SHANGHAI)
    with db_session_factory.begin() as session:
        _add_weather_snapshot(session, generated_at=captured_at)
        _add_market_artifact(session, captured_at=captured_at)
        _add_policy_document(session, captured_at=captured_at)
    with db_session_factory() as session:
        before_counts = _data_review_counts(session)

    response = client.get("/v1/operations/action-center?limit=50")

    with db_session_factory() as session:
        after_counts = _data_review_counts(session)
    assert response.status_code == 200
    assert before_counts == after_counts
    body = response.json()
    categories = {item["category"] for item in body["items"]}
    assert {
        "weather_feature_review",
        "market_artifact_review",
        "policy_document_review",
    }.issubset(categories)
    weather_item = next(
        item for item in body["items"] if item["category"] == "weather_feature_review"
    )
    market_item = next(
        item for item in body["items"] if item["category"] == "market_artifact_review"
    )
    policy_item = next(
        item for item in body["items"] if item["category"] == "policy_document_review"
    )
    assert weather_item["target_type"] == "weather_feature_snapshot"
    assert weather_item["review_target_type"] == "weather_feature"
    assert market_item["target_type"] == "market_raw_artifact"
    assert market_item["review_target_type"] == "market_artifact"
    assert policy_item["target_type"] == "knowledge_document"
    assert policy_item["review_target_type"] == "policy_document"
    assert policy_item["allowed_review_statuses"] == [
        "approved",
        "needs_revision",
        "rejected",
    ]
    assert policy_item["default_review_note"] == "Reviewed from Action Center quick action."


def test_daily_brief_freshness_warns_on_workday_but_not_weekend(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        workday = get_operations_overview(
            session=session,
            now=datetime(2026, 6, 3, 9, 0, tzinfo=SHANGHAI),
        )
    with db_session_factory() as session:
        weekend = get_operations_overview(
            session=session,
            now=datetime(2026, 6, 6, 9, 0, tzinfo=SHANGHAI),
        )

    assert _freshness(workday, "daily_brief").status == "warning"
    assert _freshness(weekend, "daily_brief").status == "healthy"


def test_operations_overview_reports_data_freshness_and_bench_isolation(
    db_session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 3, 9, 0, tzinfo=SHANGHAI)
    with db_session_factory.begin() as session:
        _add_weather_snapshot(session, generated_at=now - timedelta(hours=40))
        _add_today_brief(session, now=now)
        _add_bench_research_datasets(session, imported_at=now - timedelta(hours=24))
        _add_policy_document(session, captured_at=now - timedelta(hours=2))
    with db_session_factory() as session:
        overview = get_operations_overview(session=session, now=now)

    weather = _freshness(overview, "weather_features")
    bench = _freshness(overview, "bench_dispatch_research")
    policy = _freshness(overview, "policy_documents")

    assert weather.status == "critical"
    assert weather.age_hours is not None
    assert weather.age_hours >= 40
    assert bench.status == "healthy"
    assert bench.research_only is True
    assert bench.details["usage_scope"] == "research_only"
    assert bench.details["available_regions"] == list(BENCH_REGIONS)
    assert bench.details["recommendation_chain_isolated"] is True
    assert policy.status == "healthy"
    assert policy.details["document_count"] == 1
    assert policy.details["manual_only"] is True


def test_operations_overview_reports_source_health_counts(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        _add_market_endpoint(
            session,
            endpoint_id="southern_regulator_downloads",
            collection_enabled=False,
        )
        _add_market_endpoint(
            session,
            endpoint_id="institute_home",
            collection_enabled=False,
            access_mode="manual_submission_only",
            lifecycle_status="blocked_anti_automation",
        )
    with db_session_factory() as session:
        overview = get_operations_overview(
            session=session,
            now=datetime(2026, 6, 3, 9, 0, tzinfo=SHANGHAI),
        )

    registry = next(item for item in overview.health if item.key == "source_registry")
    assert registry.status == "healthy"
    assert registry.details["source_count"] == 2
    assert registry.details["endpoint_count"] == 2
    assert registry.details["disabled_count"] == 2
    assert registry.details["blocked_count"] == 1
    assert registry.details["manual_only_count"] == 1
    assert registry.details["policy_allowlist_collection_enabled_count"] == 0


def _json_item(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(item for item in items if item["key"] == key)


def _table_counts(session: Session) -> dict[str, int]:
    return {
        "workflow_runs": int(session.scalar(select(func.count()).select_from(WorkflowRun)) or 0),
        "briefs": int(session.scalar(select(func.count()).select_from(IntelligenceBrief)) or 0),
        "recommendations": int(
            session.scalar(select(func.count()).select_from(RecommendationRun)) or 0
        ),
        "decisions": int(
            session.scalar(select(func.count()).select_from(RecommendationDecision)) or 0
        ),
    }


def _data_review_counts(session: Session) -> dict[str, int]:
    return {
        "weather_features": int(
            session.scalar(select(func.count()).select_from(WeatherFeatureSnapshot)) or 0
        ),
        "market_artifacts": int(
            session.scalar(select(func.count()).select_from(MarketRawArtifact)) or 0
        ),
        "policy_documents": int(
            session.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
        ),
    }


def _freshness(
    overview: OperationsOverviewResponse,
    key: str,
) -> OperationsFreshnessItem:
    return next(item for item in overview.freshness if item.key == key)


def _add_weather_snapshot(session: Session, *, generated_at: datetime) -> None:
    session.add(
        WeatherFeatureSnapshot(
            feature_snapshot_id="weather_features_test",
            ingestion_run_id="weather_run_test",
            raw_payload_id="weather_raw_test",
            provider="open_meteo",
            location_id="demo_hydro_a_reference",
            generated_at=generated_at,
            forecast_start=generated_at,
            feature_version="test",
            quality_status="valid",
            human_review_status="pending_review",
            features_json={},
            evidence_json=[],
            missing_data_warnings_json=[],
            content_hash="w" * 64,
            data_mode="public_derived",
        )
    )


def _add_today_brief(session: Session, *, now: datetime) -> None:
    session.add(
        IntelligenceBrief(
            brief_id="brief_today",
            target_date=now.date(),
            generated_at=now - timedelta(hours=1),
            status="generated",
            human_review_status="pending_review",
            risk_level="medium",
            confidence_score=0.7,
            deterministic_facts_json={},
            narrative_json={"summary": "deterministic"},
            citations_json=[],
            missing_information_json=[],
            llm_used=False,
            llm_model=None,
            no_auto_trading=True,
        )
    )


def _add_bench_research_datasets(session: Session, *, imported_at: datetime) -> None:
    for index, region in enumerate(BENCH_REGIONS):
        session.add(
            ForecastResearchDataset(
                dataset_id=f"bench_{region.lower()}",
                name=f"BENCH Dispatch {region}",
                source_name="BENCH",
                source_url="https://operator.benchmark.example.invalid/",
                region_code=f"BENCH_NEM_{region}",
                region_name=region,
                market_scope="bench_nem_dispatch_benchmark",
                market_stage="dispatch",
                price_scope="regional_rrp",
                interval_minutes=15,
                timezone="Australia/Sydney",
                currency="AUD",
                price_unit="AUD/MWh",
                data_mode="public_observed",
                usage_scope="research_only",
                content_sha256=f"{index:064x}",
                raw_payload_json={},
                imported_at=imported_at,
                quality_status="valid",
                quality_issue_count=0,
                normalized_point_count=96,
                trade_date_count=1,
                notes="research_only benchmark.",
            )
        )


def _add_policy_document(session: Session, *, captured_at: datetime) -> None:
    session.add(
        KnowledgeDocument(
            document_id="policy_doc_test",
            title="Policy note",
            document_layer="official_policy",
            trust_tier="official",
            source_name="Manual import",
            source_url="https://example.test/policy",
            media_type="text/plain",
            published_at=None,
            effective_at=None,
            captured_at=captured_at,
            external_processing_allowed=False,
            human_review_status="pending_review",
            data_mode="public_observed",
        )
    )


def _add_market_artifact(session: Session, *, captured_at: datetime) -> None:
    _add_market_endpoint(
        session,
        endpoint_id="market_artifact_review_endpoint",
        collection_enabled=True,
        lifecycle_status="verified",
    )
    session.add(
        MarketRawArtifact(
            artifact_id="market_artifact_review_test",
            source_id="source_market_artifact_review_endpoint",
            endpoint_id="market_artifact_review_endpoint",
            source_url="https://example.test/artifact",
            title="Reviewable artifact",
            media_type="text/html",
            storage_backend="inline",
            inline_text="<html><body>reviewable artifact</body></html>",
            object_key=None,
            content_sha256="a" * 64,
            byte_length=45,
            published_at=None,
            captured_at=captured_at,
            ingestion_method="manual",
            transport_security_status="https_verified",
            human_review_status="pending_review",
            data_mode="public_observed",
        )
    )


def _add_market_endpoint(
    session: Session,
    *,
    endpoint_id: str,
    collection_enabled: bool,
    access_mode: str = "anonymous_https",
    lifecycle_status: str = "candidate_unverified",
) -> None:
    source_id = f"source_{endpoint_id}"
    session.add(
        MarketDataSource(
            source_id=source_id,
            name=source_id,
            operator_name=source_id,
            official_url="https://example.test/",
            market_scope="policy_research",
            notes="Test source.",
            data_mode="public_derived",
            trust_tier="candidate",
            attribution_text="Test source.",
            collection_permission_note="Manual test.",
        )
    )
    session.add(
        MarketSourceEndpoint(
            endpoint_id=endpoint_id,
            source_id=source_id,
            name=endpoint_id,
            canonical_url="https://example.test/",
            endpoint_kind="policy_research",
            allowed_domains_json=["example.test"],
            visibility_scope="internet_public",
            access_mode=access_mode,
            lifecycle_status=lifecycle_status,
            content_formats_json=["text/html"],
            data_granularity="documents",
            adapter_key=None,
            parser_key=None,
            parser_version=None,
            health_check_enabled=False,
            manual_submission_enabled=access_mode == "manual_submission_only",
            collection_enabled=collection_enabled,
            health_probe_not_before=None,
            cadence=None,
            notes="Test endpoint.",
        )
    )
