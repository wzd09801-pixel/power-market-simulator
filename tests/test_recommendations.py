from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.recommendation import (
    AuditEvent,
    FeatureSnapshot,
    RecommendationDecision,
    RecommendationDecisionFeedback,
    RecommendationReview,
    RecommendationRun,
)
from backend.app.models.weather import (
    WeatherFeatureSnapshot,
    WeatherIngestionRun,
    WeatherLocation,
    WeatherRawPayload,
)

WEATHER_FEATURES = {
    "precipitation_sum_24h": 24.0,
    "precipitation_sum_72h": 72.0,
    "rain_sum_24h": 12.0,
    "rain_sum_72h": 36.0,
    "temperature_mean_24h": 22.0,
    "temperature_min_24h": 20.0,
    "temperature_max_24h": 24.0,
}


def add_weather_feature_snapshot(
    db_session_factory: sessionmaker[Session],
    *,
    snapshot_id: str,
    review_status: str,
    quality_status: str = "valid",
    forecast_date: str = "2026-06-01",
) -> None:
    timestamp = datetime.fromisoformat(f"{forecast_date}T00:00:00+08:00")
    with db_session_factory() as session:
        session.add(
            WeatherLocation(
                location_id=f"location_{snapshot_id}",
                name="Public weather reference point",
                latitude=30.0,
                longitude=110.0,
                timezone="Asia/Shanghai",
                data_mode="public_derived",
            )
        )
        session.add(
            WeatherRawPayload(
                raw_payload_id=f"raw_{snapshot_id}",
                provider="open_meteo",
                location_id=f"location_{snapshot_id}",
                fetched_at=timestamp,
                request_url="https://api.open-meteo.com/v1/forecast",
                request_params_json={},
                payload_json={},
                raw_content="{}",
                content_hash=f"raw_hash_{snapshot_id}",
                data_mode="public_observed",
                quality_flag="valid",
            )
        )
        session.add(
            WeatherIngestionRun(
                ingestion_run_id=f"ingest_{snapshot_id}",
                provider="open_meteo",
                location_id=f"location_{snapshot_id}",
                started_at=timestamp,
                completed_at=timestamp,
                status="succeeded",
                request_url="https://api.open-meteo.com/v1/forecast",
                raw_payload_id=f"raw_{snapshot_id}",
                records_received=432,
                records_inserted=432,
                duplicate_records=0,
                quality_status=quality_status,
                quality_issue_count=0,
            )
        )
        session.add(
            WeatherFeatureSnapshot(
                feature_snapshot_id=snapshot_id,
                ingestion_run_id=f"ingest_{snapshot_id}",
                raw_payload_id=f"raw_{snapshot_id}",
                provider="open_meteo",
                location_id=f"location_{snapshot_id}",
                generated_at=timestamp,
                forecast_start=timestamp,
                feature_version="hydro_weather_v1",
                quality_status=quality_status,
                human_review_status=review_status,
                features_json=WEATHER_FEATURES,
                evidence_json=[
                    {
                        "field": "precipitation_sum_72h",
                        "value": 72.0,
                        "unit": "mm",
                        "formula": "sum",
                    }
                ],
                missing_data_warnings_json=[],
                content_hash=f"feature_hash_{snapshot_id}",
                data_mode="public_derived",
            )
        )
        session.commit()


def test_recommendation_is_persisted_with_snapshot_and_audit_event(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    response = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_id"].startswith("rec_")
    assert payload["input_snapshot_id"].startswith("snapshot_")
    assert payload["review_status"] == "pending_review"
    assert payload["horizon"] == "day_ahead_scenario"
    assert payload["data_mode"] == "scenario_simulated"
    assert payload["human_check_required"] is True
    assert payload["no_auto_trading"] is True
    assert payload["evidence"]
    assert payload["missing_data_warnings"]

    with db_session_factory() as session:
        snapshot_count = session.scalar(select(func.count()).select_from(FeatureSnapshot))
        recommendation_count = session.scalar(select(func.count()).select_from(RecommendationRun))
        audit_count = session.scalar(select(func.count()).select_from(AuditEvent))

    assert snapshot_count == 1
    assert recommendation_count == 1
    assert audit_count == 1


def test_recommendation_missing_trade_date_returns_stable_error(client: TestClient) -> None:
    response = client.post("/v1/recommendations/run", json={})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Invalid request payload."


def test_recommendation_reviews_preserve_history_and_latest_status(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]

    actions = [
        ("approved", "场景假设清楚，可以继续人工决策。"),
        ("rejected", "缺少价格序列，暂不采纳。"),
        ("needs_revision", "请补充天气数据后重新生成。"),
    ]
    for review_status, note in actions:
        response = client.post(
            f"/v1/recommendations/{recommendation_id}/reviews",
            json={"review_status": review_status, "note": note},
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == review_status

    detail = client.get(f"/v1/recommendations/{recommendation_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["review_status"] == "needs_revision"
    assert [review["review_status"] for review in payload["reviews"]] == [
        "approved",
        "rejected",
        "needs_revision",
    ]

    with db_session_factory() as session:
        review_count = session.scalar(select(func.count()).select_from(RecommendationReview))
        audit_count = session.scalar(select(func.count()).select_from(AuditEvent))

    assert review_count == 3
    assert audit_count == 4


def test_recent_recommendations_returns_saved_drafts(client: TestClient) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    response = client.get("/v1/recommendations/recent?limit=10")
    assert response.status_code == 200
    assert response.json()["items"][0]["recommendation_id"] == generated["recommendation_id"]


def test_missing_recommendation_returns_stable_error(client: TestClient) -> None:
    response = client.get("/v1/recommendations/rec_missing")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "recommendation_not_found",
            "message": "Recommendation 'rec_missing' was not found.",
        }
    }


def test_recommendation_audit_flags_scenario_missing_data_warnings(
    client: TestClient,
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()

    response = client.get(f"/v1/recommendations/{generated['recommendation_id']}/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "warning"
    assert payload["review_status"] == "pending_review"
    assert payload["no_auto_trading"] is True
    assert payload["human_check_required"] is True
    assert payload["evidence_summary"]["evidence_count"] >= 1
    assert payload["evidence_summary"]["missing_data_count"] >= 4
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["no_auto_trading"]["status"] == "healthy"
    assert checks["human_review_required"]["status"] == "healthy"
    assert checks["recommendation_chain_isolation"]["status"] == "healthy"
    assert checks["weather_context"]["status"] == "warning"
    assert checks["missing_data"]["status"] == "warning"
    assert any("Complete human review" in action for action in payload["recommended_actions"])


def test_recommendation_audit_recognizes_approved_weather_evidence(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    add_weather_feature_snapshot(
        db_session_factory,
        snapshot_id="weather_audit_approved",
        review_status="approved",
    )
    generated = client.post(
        "/v1/recommendations/run",
        json={
            "trade_date": "2026-06-01",
            "weather_feature_snapshot_id": "weather_audit_approved",
        },
    ).json()

    response = client.get(f"/v1/recommendations/{generated['recommendation_id']}/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "warning"
    assert payload["evidence_summary"]["weather_evidence_present"] is True
    assert payload["evidence_summary"]["source_types"]["weather_feature"] == 1
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["weather_context"]["status"] == "healthy"
    assert checks["missing_data"]["status"] == "warning"


def test_recommendation_audit_reflects_latest_review_status(client: TestClient) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]
    review = client.post(
        f"/v1/recommendations/{recommendation_id}/reviews",
        json={"review_status": "approved", "note": "Reviewed scenario warnings."},
    )

    response = client.get(f"/v1/recommendations/{recommendation_id}/audit")

    assert review.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "approved"
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["review_status"]["status"] == "healthy"


def test_recommendation_audit_rejects_research_only_and_disabled_safety_flags(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]
    with db_session_factory.begin() as session:
        run = session.get(RecommendationRun, recommendation_id)
        assert run is not None
        strategy = dict(run.strategy_json)
        strategy["no_auto_trading"] = False
        strategy["human_check_required"] = False
        strategy["evidence"] = [
            *cast(list[dict[str, object]], strategy["evidence"]),
            {
                "source": "BENCH Dispatch benchmark",
                "source_type": "policy_watch_research_only",
                "data_mode": "public_derived",
                "timestamp": "2026-06-01T00:00:00+08:00",
                "field": "dispatchis_rrp",
                "value": 1.0,
                "unit": "AUD/MWh",
                "confidence": 0.1,
                "url": "https://bench.example/dispatchis",
                "note": "research_only policy_watch marker must not enter recommendations.",
            },
        ]
        run.strategy_json = strategy

    response = client.get(f"/v1/recommendations/{recommendation_id}/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "critical"
    assert payload["evidence_summary"]["research_only_evidence_count"] == 1
    assert payload["evidence_summary"]["bench_evidence_count"] == 1
    assert payload["evidence_summary"]["policy_watch_evidence_count"] == 1
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["no_auto_trading"]["status"] == "critical"
    assert checks["human_review_required"]["status"] == "critical"
    assert checks["recommendation_chain_isolation"]["status"] == "critical"


def test_recommendation_evidence_export_is_read_only_package(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]
    with db_session_factory() as session:
        before_audit_count = session.scalar(select(func.count()).select_from(AuditEvent))

    response = client.get(f"/v1/recommendations/{recommendation_id}/evidence-export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_id"] == recommendation_id
    assert payload["input_snapshot_id"] == generated["input_snapshot_id"]
    assert payload["trade_date"] == "2026-06-01"
    assert payload["asset_id"] == "demo_hydro_a"
    assert payload["scenario_id"] == "demo_hydro_a_normal_storage_normal_inflow_v1"
    assert payload["generated_at"]
    assert payload["exported_at"]
    assert payload["review_status"] == "pending_review"
    assert payload["audit_status"] == "warning"
    assert payload["data_mode"] == "scenario_simulated"
    assert payload["risk_level"] == generated["risk_level"]
    assert payload["confidence"] == generated["confidence"]
    assert payload["human_check_required"] is True
    assert payload["no_auto_trading"] is True
    assert payload["missing_data_warnings"] == generated["missing_data_warnings"]
    assert payload["evidence"] == generated["evidence"]
    assert payload["evidence_summary"]["evidence_count"] == len(generated["evidence"])
    assert {check["key"] for check in payload["checks"]} >= {
        "no_auto_trading",
        "human_review_required",
        "recommendation_chain_isolation",
    }
    assert any("Complete human review" in action for action in payload["recommended_actions"])
    with db_session_factory() as session:
        after_audit_count = session.scalar(select(func.count()).select_from(AuditEvent))
    assert after_audit_count == before_audit_count


def test_recommendation_evidence_export_missing_recommendation_returns_stable_error(
    client: TestClient,
) -> None:
    response = client.get("/v1/recommendations/rec_missing/evidence-export")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "recommendation_not_found"


def test_recommendation_audit_missing_recommendation_returns_stable_error(
    client: TestClient,
) -> None:
    response = client.get("/v1/recommendations/rec_missing/audit")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "recommendation_not_found"


def test_recommendation_decision_records_warning_audit_snapshot(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]

    response = client.post(
        f"/v1/recommendations/{recommendation_id}/decisions",
        json={
            "decision_status": "partially_adopted",
            "selected_windows": ["18:00-21:00"],
            "note": "Use as a local discussion input only.",
            "safety_boundary_acknowledged": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_status"] == "partially_adopted"
    assert payload["selected_windows"] == ["18:00-21:00"]
    assert payload["no_auto_trading"] is True
    assert payload["audit_snapshot"]["overall_status"] == "warning"
    assert payload["feedback"] == []
    with db_session_factory() as session:
        decision_count = session.scalar(select(func.count()).select_from(RecommendationDecision))
        event = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "recommendation_decision_recorded")
        ).one()

    assert decision_count == 1
    assert event.data_mode == "user_uploaded"
    assert event.payload_json["decision_status"] == "partially_adopted"


def test_recommendation_decision_requires_safety_boundary_ack(
    client: TestClient,
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()

    response = client.post(
        f"/v1/recommendations/{generated['recommendation_id']}/decisions",
        json={
            "decision_status": "deferred",
            "selected_windows": [],
            "note": "Need more data.",
            "safety_boundary_acknowledged": False,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_recommendation_decision_blocks_adoption_for_critical_audit(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]
    with db_session_factory.begin() as session:
        run = session.get(RecommendationRun, recommendation_id)
        assert run is not None
        strategy = dict(run.strategy_json)
        strategy["no_auto_trading"] = False
        run.strategy_json = strategy

    response = client.post(
        f"/v1/recommendations/{recommendation_id}/decisions",
        json={
            "decision_status": "adopted",
            "selected_windows": ["18:00-21:00"],
            "note": "Should be blocked.",
            "safety_boundary_acknowledged": True,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "recommendation_audit_not_adoptable"


def test_recommendation_decision_allows_non_adoption_for_critical_audit(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]
    with db_session_factory.begin() as session:
        run = session.get(RecommendationRun, recommendation_id)
        assert run is not None
        strategy = dict(run.strategy_json)
        strategy["human_check_required"] = False
        run.strategy_json = strategy

    response = client.post(
        f"/v1/recommendations/{recommendation_id}/decisions",
        json={
            "decision_status": "not_adopted",
            "selected_windows": [],
            "note": "Critical audit means this draft is not adopted.",
            "safety_boundary_acknowledged": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["audit_snapshot"]["overall_status"] == "critical"
    assert response.json()["decision_status"] == "not_adopted"


def test_recommendation_decision_feedback_is_append_only(
    client: TestClient,
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]
    decision = client.post(
        f"/v1/recommendations/{recommendation_id}/decisions",
        json={
            "decision_status": "deferred",
            "selected_windows": [],
            "note": "Wait for more observations.",
            "safety_boundary_acknowledged": True,
        },
    ).json()

    first = client.post(
        f"/v1/recommendations/decisions/{decision['decision_id']}/feedback",
        json={
            "outcome_status": "pending_observation",
            "observed_at": "2026-06-02",
            "note": "Observation window has started.",
        },
    )
    second = client.post(
        f"/v1/recommendations/decisions/{decision['decision_id']}/feedback",
        json={
            "outcome_status": "uncertain",
            "observed_at": "2026-06-03",
            "note": "Still not enough market data.",
        },
    )
    listing = client.get(f"/v1/recommendations/{recommendation_id}/decisions")

    assert first.status_code == 200
    assert second.status_code == 200
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert [item["outcome_status"] for item in items[0]["feedback"]] == [
        "pending_observation",
        "uncertain",
    ]
    assert all(item["data_mode"] == "user_uploaded" for item in items[0]["feedback"])


def test_recommendation_decision_missing_records_return_stable_errors(
    client: TestClient,
) -> None:
    missing_recommendation = client.get("/v1/recommendations/rec_missing/decisions")
    missing_feedback = client.post(
        "/v1/recommendations/decisions/decision_missing/feedback",
        json={
            "outcome_status": "neutral",
            "observed_at": None,
            "note": "Missing decision.",
        },
    )

    assert missing_recommendation.status_code == 404
    assert missing_recommendation.json()["error"]["code"] == "recommendation_not_found"
    assert missing_feedback.status_code == 404
    assert missing_feedback.json()["error"]["code"] == "recommendation_decision_not_found"


def test_recommendation_feedback_overview_empty_database_returns_warning(
    client: TestClient,
) -> None:
    response = client.get("/v1/recommendations/feedback/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["summary"]["recommendation_count"] == 0
    assert payload["summary"]["decision_count"] == 0
    assert payload["summary"]["feedback_count"] == 0
    assert payload["summary"]["audit_status_counts"] == {}
    assert payload["summary"]["review_status_counts"] == {}
    assert payload["recent_decisions"] == []
    assert payload["recent_feedback"] == []
    assert payload["no_auto_trading"] is True
    assert "Record operator decisions" in payload["recommended_actions"][0]


def test_recommendation_feedback_overview_aggregates_decisions_and_feedback(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    first = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    first_decision = client.post(
        f"/v1/recommendations/{first['recommendation_id']}/decisions",
        json={
            "decision_status": "partially_adopted",
            "selected_windows": ["18:00-21:00"],
            "note": "Use for local operator discussion.",
            "safety_boundary_acknowledged": True,
        },
    ).json()
    client.post(
        f"/v1/recommendations/decisions/{first_decision['decision_id']}/feedback",
        json={
            "outcome_status": "useful",
            "observed_at": "2026-06-02",
            "note": "The discussion helped frame follow-up checks.",
        },
    )

    second = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-02"}).json()
    with db_session_factory.begin() as session:
        run = session.get(RecommendationRun, second["recommendation_id"])
        assert run is not None
        strategy = dict(run.strategy_json)
        strategy["human_check_required"] = False
        run.strategy_json = strategy
    second_decision = client.post(
        f"/v1/recommendations/{second['recommendation_id']}/decisions",
        json={
            "decision_status": "not_adopted",
            "selected_windows": [],
            "note": "Critical audit; do not adopt.",
            "safety_boundary_acknowledged": True,
        },
    )

    response = client.get("/v1/recommendations/feedback/overview?limit=5")

    assert second_decision.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert payload["status"] == "warning"
    assert summary["recommendation_count"] == 2
    assert summary["decision_count"] == 2
    assert summary["feedback_count"] == 1
    assert summary["pending_observation_count"] == 1
    assert summary["critical_audit_not_adopted_count"] == 1
    assert summary["no_auto_trading_false_count"] == 0
    assert summary["safety_boundary_unacknowledged_count"] == 0
    assert summary["audit_status_counts"]["warning"] == 1
    assert summary["audit_status_counts"]["critical"] == 1
    assert summary["review_status_counts"]["pending_review"] == 2
    assert summary["decision_status_counts"]["partially_adopted"] == 1
    assert summary["decision_status_counts"]["not_adopted"] == 1
    assert summary["outcome_status_counts"]["useful"] == 1
    assert summary["feedback_data_modes"]["user_uploaded"] == 1
    assert payload["pending_observation_decisions"][0]["decision_status"] == "not_adopted"
    assert payload["critical_audit_not_adopted"][0]["audit_status"] == "critical"
    assert payload["recent_feedback"][0]["outcome_status"] == "useful"
    assert "Add follow-up feedback" in " ".join(payload["recommended_actions"])


def test_recommendation_decision_does_not_mutate_recommendation(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]
    with db_session_factory() as session:
        before = session.get(RecommendationRun, recommendation_id)
        assert before is not None
        before_status = before.review_status
        before_confidence = before.confidence
        before_strategy = dict(before.strategy_json)

    client.post(
        f"/v1/recommendations/{recommendation_id}/decisions",
        json={
            "decision_status": "deferred",
            "selected_windows": [],
            "note": "Decision log only.",
            "safety_boundary_acknowledged": True,
        },
    )

    with db_session_factory() as session:
        after = session.get(RecommendationRun, recommendation_id)
        assert after is not None
        feedback_count = session.scalar(
            select(func.count()).select_from(RecommendationDecisionFeedback)
        )

    assert after.review_status == before_status
    assert after.confidence == before_confidence
    assert after.strategy_json == before_strategy
    assert feedback_count == 0


def test_review_requires_valid_action_and_non_blank_note(client: TestClient) -> None:
    generated = client.post("/v1/recommendations/run", json={"trade_date": "2026-06-01"}).json()
    recommendation_id = generated["recommendation_id"]

    invalid_action = client.post(
        f"/v1/recommendations/{recommendation_id}/reviews",
        json={"review_status": "maybe", "note": "test"},
    )
    assert invalid_action.status_code == 422
    assert invalid_action.json()["error"]["code"] == "validation_error"

    blank_note = client.post(
        f"/v1/recommendations/{recommendation_id}/reviews",
        json={"review_status": "needs_revision", "note": "   "},
    )
    assert blank_note.status_code == 422
    assert blank_note.json()["error"]["code"] == "validation_error"


def test_recommendation_links_explicit_approved_weather_snapshot_as_evidence(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    add_weather_feature_snapshot(
        db_session_factory,
        snapshot_id="weather_approved",
        review_status="approved",
    )

    response = client.post(
        "/v1/recommendations/run",
        json={
            "trade_date": "2026-06-01",
            "weather_feature_snapshot_id": "weather_approved",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["weather_feature_snapshot_id"] == "weather_approved"
    assert any(item["source_type"] == "weather_feature" for item in payload["evidence"])
    assert any("public-derived" in warning for warning in payload["missing_data_warnings"])

    with db_session_factory() as session:
        snapshot = session.scalar(select(FeatureSnapshot))
        audit_event = session.scalar(select(AuditEvent))

    assert snapshot is not None
    weather_inputs = cast(dict[str, object], snapshot.inputs_json["weather_feature_snapshot"])
    assert weather_inputs["feature_snapshot_id"] == "weather_approved"
    assert audit_event is not None
    assert audit_event.payload_json["weather_feature_snapshot_id"] == "weather_approved"


def test_recommendation_rejects_unapproved_weather_snapshot(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    add_weather_feature_snapshot(
        db_session_factory,
        snapshot_id="weather_pending",
        review_status="pending_review",
    )

    response = client.post(
        "/v1/recommendations/run",
        json={
            "trade_date": "2026-06-01",
            "weather_feature_snapshot_id": "weather_pending",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "weather_feature_snapshot_not_usable"


def test_recommendation_rejects_weather_snapshot_for_different_trade_date(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    add_weather_feature_snapshot(
        db_session_factory,
        snapshot_id="weather_wrong_day",
        review_status="approved",
        forecast_date="2026-06-02",
    )

    response = client.post(
        "/v1/recommendations/run",
        json={
            "trade_date": "2026-06-01",
            "weather_feature_snapshot_id": "weather_wrong_day",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "weather_feature_snapshot_not_usable"


def test_recommendation_returns_stable_error_for_missing_weather_snapshot(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/recommendations/run",
        json={
            "trade_date": "2026-06-01",
            "weather_feature_snapshot_id": "weather_missing",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "weather_feature_snapshot_not_found",
            "message": "Weather feature snapshot 'weather_missing' was not found.",
        }
    }
