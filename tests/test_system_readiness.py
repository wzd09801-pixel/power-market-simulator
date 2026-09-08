from __future__ import annotations

from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.forecasting import (
    ForecastResearchDataset,
    ForecastResearchModelRun,
    ForecastResearchPrediction,
    ForecastResearchPricePoint,
)
from backend.app.models.intelligence import IntelligenceBrief
from backend.app.models.knowledge import KnowledgeDocument
from backend.app.models.market import MarketRawArtifact
from backend.app.models.recommendation import (
    RecommendationDecision,
    RecommendationDecisionFeedback,
    RecommendationRun,
)
from backend.app.models.weather import WeatherFeatureSnapshot
from backend.app.schemas.system import SystemReadinessResponse
from backend.app.services.demo_seed import DEMO_IDS, DEMO_SEED_KEY
from backend.app.services.system import get_system_readiness
from backend.app.services.workstation_jobs import execute_fixed_workstation_job


def test_system_readiness_empty_database_returns_warning(client: TestClient) -> None:
    response = client.get("/v1/system/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["no_auto_trading"] is True
    assert payload["demo_seed"]["seed_key"] == DEMO_SEED_KEY
    assert set(payload["missing_demo_items"]) == {
        "weather_snapshot",
        "market_artifact",
        "policy_document",
        "brief",
        "recommendation",
        "decision_feedback",
        "forecast_dataset",
        "forecast_model_run",
    }
    assert any(
        "demo_research_workspace_seed" in action for action in payload["recommended_actions"]
    )


def test_demo_seed_fixed_job_is_idempotent_and_keeps_data_boundaries(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        first = execute_fixed_workstation_job("demo_research_workspace_seed", session=session)
        second = execute_fixed_workstation_job("demo_research_workspace_seed", session=session)

    with db_session_factory() as session:
        counts = {
            "weather": _count(session, WeatherFeatureSnapshot),
            "market_artifact": _count(session, MarketRawArtifact),
            "policy_document": _count(session, KnowledgeDocument),
            "brief": _count(session, IntelligenceBrief),
            "recommendation": _count(session, RecommendationRun),
            "decision": _count(session, RecommendationDecision),
            "feedback": _count(session, RecommendationDecisionFeedback),
            "forecast_dataset": _count(session, ForecastResearchDataset),
            "forecast_points": _count(session, ForecastResearchPricePoint),
            "forecast_model_run": _count(session, ForecastResearchModelRun),
            "forecast_predictions": _count(session, ForecastResearchPrediction),
        }
        readiness = get_system_readiness(session=session)
        recommendation = session.get(RecommendationRun, DEMO_IDS["recommendation"])
        dataset = session.get(ForecastResearchDataset, DEMO_IDS["forecast_dataset"])
        model_run = session.get(ForecastResearchModelRun, DEMO_IDS["forecast_model_run"])
        document = session.get(KnowledgeDocument, DEMO_IDS["knowledge_document"])
        artifact = session.get(MarketRawArtifact, DEMO_IDS["market_artifact"])
        brief = session.get(IntelligenceBrief, DEMO_IDS["brief"])

    first_created = cast(dict[str, bool], first.summary["created"])
    second_created = cast(dict[str, bool], second.summary["created"])

    assert first.status == "succeeded"
    assert first.summary["seed_key"] == DEMO_SEED_KEY
    assert first_created["weather_snapshot"] is True
    assert first.summary["no_auto_trading"] is True
    assert second.status == "succeeded"
    assert all(created is False for created in second_created.values())
    assert counts == {
        "weather": 1,
        "market_artifact": 1,
        "policy_document": 1,
        "brief": 1,
        "recommendation": 1,
        "decision": 1,
        "feedback": 1,
        "forecast_dataset": 1,
        "forecast_points": 15 * 96,
        "forecast_model_run": 1,
        "forecast_predictions": 3 * 96,
    }
    assert readiness.missing_demo_items == []
    assert readiness.status == "warning"
    assert _check_status(readiness, "demo_seed") == "healthy"
    assert _check_status(readiness, "recommendation_isolation") == "healthy"
    assert recommendation is not None
    assert recommendation.data_mode == "scenario_simulated"
    assert recommendation.review_status == "pending_review"
    assert recommendation.strategy_json["no_auto_trading"] is True
    assert recommendation.strategy_json["human_check_required"] is True
    assert "bench" not in str(recommendation.strategy_json).lower()
    assert "research_only" not in str(recommendation.strategy_json).lower()
    assert "policy_watch" not in str(recommendation.strategy_json).lower()
    assert dataset is not None
    assert dataset.data_mode == "scenario_simulated"
    assert dataset.usage_scope == "research_only"
    assert model_run is not None
    assert model_run.registry_status == "candidate"
    assert model_run.usage_scope == "research_only"
    assert document is not None
    assert document.data_mode == "user_uploaded"
    assert document.external_processing_allowed is False
    assert artifact is not None
    assert artifact.data_mode == "user_uploaded"
    assert brief is not None
    assert brief.no_auto_trading is True


def test_system_readiness_marks_forbidden_recommendation_research_evidence_critical(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        execute_fixed_workstation_job("demo_research_workspace_seed", session=session)
    with db_session_factory.begin() as session:
        recommendation = session.get(RecommendationRun, DEMO_IDS["recommendation"])
        assert recommendation is not None
        mutated = dict(recommendation.strategy_json)
        mutated["evidence"] = [
            {
                "source": "BENCH",
                "usage_scope": "research_only",
                "field": "policy_watch",
            }
        ]
        recommendation.strategy_json = mutated
    with db_session_factory() as session:
        readiness = get_system_readiness(session=session)

    assert readiness.status == "critical"
    isolation = next(check for check in readiness.checks if check.key == "recommendation_isolation")
    assert isolation.status == "critical"
    assert isolation.details["violating_recommendation_ids"] == [DEMO_IDS["recommendation"]]


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _check_status(response: SystemReadinessResponse, key: str) -> str:
    return next(check.status for check in response.checks if check.key == key)
