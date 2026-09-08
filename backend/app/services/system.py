from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.models.forecasting import ForecastResearchDataset, ForecastResearchModelRun
from backend.app.models.intelligence import IntelligenceBrief
from backend.app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from backend.app.models.market import MarketRawArtifact
from backend.app.models.recommendation import (
    RecommendationDecision,
    RecommendationDecisionFeedback,
    RecommendationRun,
)
from backend.app.models.weather import WeatherFeatureSnapshot
from backend.app.schemas.system import (
    DemoSeedSummary,
    SystemReadinessCheck,
    SystemReadinessResponse,
    SystemReadinessStatus,
)
from backend.app.services.demo_seed import DEMO_IDS, DEMO_SEED_KEY, demo_seed_presence
from backend.app.services.operations import get_operation_action_center

TIMEZONE = ZoneInfo("Asia/Shanghai")
RECOMMENDATION_FORBIDDEN_EVIDENCE_MARKERS = ("bench", "research_only", "policy_watch")


def get_system_readiness(*, session: Session) -> SystemReadinessResponse:
    generated_at = datetime.now(tz=TIMEZONE)
    table_counts = _table_counts(session)
    demo_presence = demo_seed_presence(session)
    missing_demo_items = [key for key, present in demo_presence.items() if not present]
    checks = [
        _migration_check(session),
        _demo_seed_check(demo_presence),
        _weather_check(table_counts),
        _policy_corpus_check(table_counts),
        _brief_check(session, table_counts),
        _recommendation_check(table_counts),
        _forecast_check(session, table_counts),
        _recommendation_isolation_check(session),
        _action_center_check(session),
    ]
    status = _worst_status([check.status for check in checks])
    return SystemReadinessResponse(
        generated_at=generated_at,
        status=status,
        checks=checks,
        demo_seed=_demo_seed_summary(demo_presence),
        table_counts=table_counts,
        missing_demo_items=missing_demo_items,
        recommended_actions=_recommended_actions(checks, missing_demo_items),
        no_auto_trading=True,
    )


def _table_counts(session: Session) -> dict[str, int]:
    models = {
        "weather_feature_snapshots": WeatherFeatureSnapshot,
        "market_raw_artifacts": MarketRawArtifact,
        "knowledge_documents": KnowledgeDocument,
        "knowledge_chunks": KnowledgeChunk,
        "intelligence_briefs": IntelligenceBrief,
        "recommendation_runs": RecommendationRun,
        "recommendation_decisions": RecommendationDecision,
        "recommendation_decision_feedback": RecommendationDecisionFeedback,
        "forecast_research_datasets": ForecastResearchDataset,
        "forecast_research_model_runs": ForecastResearchModelRun,
    }
    counts: dict[str, int] = {}
    for key, model in models.items():
        counts[key] = int(session.scalar(select(func.count()).select_from(model)) or 0)
    return counts


def _migration_check(session: Session) -> SystemReadinessCheck:
    try:
        version = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    except SQLAlchemyError:
        return SystemReadinessCheck(
            key="migration",
            label="Database Migration Marker",
            status="warning",
            message="Alembic revision marker is unavailable; tests may be using create_all.",
            details={"revision": None},
        )
    status: SystemReadinessStatus = "healthy" if version else "warning"
    return SystemReadinessCheck(
        key="migration",
        label="Database Migration Marker",
        status=status,
        message=(
            f"Database reports Alembic revision {version}."
            if version
            else "Database has no Alembic revision marker."
        ),
        details={"revision": version},
    )


def _demo_seed_check(presence: dict[str, bool]) -> SystemReadinessCheck:
    missing = [key for key, present in presence.items() if not present]
    return SystemReadinessCheck(
        key="demo_seed",
        label="Demo Seed Coverage",
        status="healthy" if not missing else "warning",
        message=(
            "Demo seed objects are present."
            if not missing
            else "Demo seed is incomplete; run the fixed demo seed job."
        ),
        details={"seed_key": DEMO_SEED_KEY, "missing": missing, "presence": presence},
    )


def _weather_check(counts: dict[str, int]) -> SystemReadinessCheck:
    count = counts["weather_feature_snapshots"]
    return SystemReadinessCheck(
        key="weather_features",
        label="Weather Feature Snapshots",
        status="healthy" if count > 0 else "warning",
        message=(
            "Weather feature snapshots are available."
            if count > 0
            else "No weather feature snapshot is available."
        ),
        details={"count": count},
    )


def _policy_corpus_check(counts: dict[str, int]) -> SystemReadinessCheck:
    documents = counts["knowledge_documents"]
    chunks = counts["knowledge_chunks"]
    status: SystemReadinessStatus = "healthy" if documents > 0 and chunks > 0 else "warning"
    return SystemReadinessCheck(
        key="policy_corpus",
        label="Policy Corpus",
        status=status,
        message=(
            "Policy corpus has documents and chunks."
            if status == "healthy"
            else "Policy corpus is missing documents or chunks."
        ),
        details={"document_count": documents, "chunk_count": chunks},
    )


def _brief_check(session: Session, counts: dict[str, int]) -> SystemReadinessCheck:
    brief_count = counts["intelligence_briefs"]
    pending_count = int(
        session.scalar(
            select(func.count())
            .select_from(IntelligenceBrief)
            .where(IntelligenceBrief.human_review_status.in_(("pending_review", "needs_revision")))
        )
        or 0
    )
    status: SystemReadinessStatus = (
        "warning" if brief_count == 0 or pending_count > 0 else "healthy"
    )
    return SystemReadinessCheck(
        key="brief_review",
        label="Brief Review Loop",
        status=status,
        message=(
            "Briefs exist and no brief is pending review."
            if status == "healthy"
            else "Brief review loop needs operator attention or seed data."
        ),
        details={"brief_count": brief_count, "pending_review_count": pending_count},
    )


def _recommendation_check(counts: dict[str, int]) -> SystemReadinessCheck:
    recommendation_count = counts["recommendation_runs"]
    decision_count = counts["recommendation_decisions"]
    feedback_count = counts["recommendation_decision_feedback"]
    status: SystemReadinessStatus = (
        "healthy"
        if recommendation_count > 0 and decision_count > 0 and feedback_count > 0
        else "warning"
    )
    return SystemReadinessCheck(
        key="recommendation_feedback",
        label="Recommendation Feedback Loop",
        status=status,
        message=(
            "Recommendation, decision, and feedback records are available."
            if status == "healthy"
            else "Recommendation feedback loop is incomplete."
        ),
        details={
            "recommendation_count": recommendation_count,
            "decision_count": decision_count,
            "feedback_count": feedback_count,
        },
    )


def _forecast_check(session: Session, counts: dict[str, int]) -> SystemReadinessCheck:
    dataset_count = counts["forecast_research_datasets"]
    candidate_count = int(
        session.scalar(
            select(func.count())
            .select_from(ForecastResearchModelRun)
            .where(
                ForecastResearchModelRun.registry_status == "candidate",
                ForecastResearchModelRun.usage_scope == "research_only",
            )
        )
        or 0
    )
    non_research_dataset_count = int(
        session.scalar(
            select(func.count())
            .select_from(ForecastResearchDataset)
            .where(ForecastResearchDataset.usage_scope != "research_only")
        )
        or 0
    )
    status: SystemReadinessStatus = (
        "critical"
        if non_research_dataset_count > 0
        else ("healthy" if dataset_count > 0 and candidate_count > 0 else "warning")
    )
    return SystemReadinessCheck(
        key="forecast_research",
        label="Forecast Research",
        status=status,
        message=(
            "Forecast research dataset and candidate model run are available."
            if status == "healthy"
            else "Forecast research is incomplete or has non-research scoped datasets."
        ),
        details={
            "dataset_count": dataset_count,
            "candidate_model_run_count": candidate_count,
            "non_research_dataset_count": non_research_dataset_count,
            "usage_scope": "research_only",
        },
    )


def _recommendation_isolation_check(session: Session) -> SystemReadinessCheck:
    violating_ids: list[str] = []
    for run in session.scalars(select(RecommendationRun)):
        if _contains_forbidden_recommendation_marker(run.strategy_json):
            violating_ids.append(run.rec_id)
    return SystemReadinessCheck(
        key="recommendation_isolation",
        label="Recommendation Evidence Isolation",
        status="critical" if violating_ids else "healthy",
        message=(
            "Recommendation evidence is isolated from BENCH, research_only, and policy_watch."
            if not violating_ids
            else "Recommendation evidence contains forbidden research markers."
        ),
        details={"violating_recommendation_ids": violating_ids},
    )


def _action_center_check(session: Session) -> SystemReadinessCheck:
    action_center = get_operation_action_center(session=session, limit=20)
    status: SystemReadinessStatus = "warning" if action_center.counts.total else "healthy"
    return SystemReadinessCheck(
        key="action_center",
        label="Action Center",
        status=status,
        message=(
            "Action Center has no urgent todo items."
            if action_center.counts.total == 0
            else "Action Center has operator todo items."
        ),
        details={
            "todo_count": action_center.counts.total,
            "critical": action_center.counts.critical,
            "warning": action_center.counts.warning,
            "by_category": action_center.counts.by_category,
        },
    )


def _demo_seed_summary(presence: dict[str, bool]) -> DemoSeedSummary:
    return DemoSeedSummary(
        seed_key=DEMO_SEED_KEY,
        created={key: False for key in presence},
        object_ids={
            "weather_feature_snapshot_id": DEMO_IDS["weather_feature_snapshot"],
            "market_artifact_id": DEMO_IDS["market_artifact"],
            "policy_document_id": DEMO_IDS["knowledge_document"],
            "brief_id": DEMO_IDS["brief"],
            "recommendation_id": DEMO_IDS["recommendation"],
            "recommendation_decision_id": DEMO_IDS["recommendation_decision"],
            "forecast_dataset_id": DEMO_IDS["forecast_dataset"],
            "forecast_model_run_id": DEMO_IDS["forecast_model_run"],
        },
        data_modes={
            "weather": "public_derived",
            "market_artifact": "user_uploaded",
            "policy_document": "user_uploaded",
            "recommendation": "scenario_simulated",
            "decision_feedback": "user_uploaded",
            "forecast": "scenario_simulated/public_derived",
        },
        research_only=True,
        no_auto_trading=True,
    )


def _recommended_actions(
    checks: list[SystemReadinessCheck],
    missing_demo_items: list[str],
) -> list[str]:
    actions: list[str] = []
    if missing_demo_items:
        actions.append("Run fixed job demo_research_workspace_seed to populate local RC fixtures.")
    for check in checks:
        if check.status == "critical":
            actions.append(f"Resolve critical readiness check: {check.label}.")
    if not actions:
        actions.append("Review Action Center items and complete normal human review steps.")
    return actions


def _worst_status(statuses: list[SystemReadinessStatus]) -> SystemReadinessStatus:
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    return "healthy"


def _contains_forbidden_recommendation_marker(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_forbidden_recommendation_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_recommendation_marker(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in RECOMMENDATION_FORBIDDEN_EVIDENCE_MARKERS)
    return False
