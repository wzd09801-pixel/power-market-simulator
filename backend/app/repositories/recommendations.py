from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.recommendation import (
    AuditEvent,
    FeatureSnapshot,
    RecommendationDecision,
    RecommendationDecisionFeedback,
    RecommendationReview,
    RecommendationRun,
)


def add_feature_snapshot(
    session: Session,
    *,
    snapshot_id: str,
    created_at: datetime,
    trade_date: date,
    asset_id: str,
    scenario_id: str,
    data_mode: str,
    inputs_json: dict[str, Any],
    evidence_json: list[dict[str, Any]],
) -> FeatureSnapshot:
    snapshot = FeatureSnapshot(
        snapshot_id=snapshot_id,
        created_at=created_at,
        trade_date=trade_date,
        asset_id=asset_id,
        scenario_id=scenario_id,
        data_mode=data_mode,
        inputs_json=inputs_json,
        evidence_json=evidence_json,
    )
    session.add(snapshot)
    return snapshot


def add_recommendation_run(
    session: Session,
    *,
    recommendation_id: str,
    created_at: datetime,
    input_snapshot_id: str,
    trade_date: date,
    asset_id: str,
    data_mode: str,
    scenario_id: str,
    risk_level: str,
    confidence: float,
    strategy_json: dict[str, Any],
) -> RecommendationRun:
    run = RecommendationRun(
        rec_id=recommendation_id,
        created_at=created_at,
        input_snapshot_id=input_snapshot_id,
        trade_date=trade_date,
        asset_id=asset_id,
        data_mode=data_mode,
        scenario_id=scenario_id,
        risk_level=risk_level,
        confidence=confidence,
        strategy_json=strategy_json,
        review_status="pending_review",
    )
    session.add(run)
    return run


def add_audit_event(
    session: Session,
    *,
    event_id: str,
    created_at: datetime,
    event_type: str,
    data_mode: str,
    payload_json: dict[str, Any],
    actor: str = "system",
) -> AuditEvent:
    event = AuditEvent(
        event_id=event_id,
        created_at=created_at,
        event_type=event_type,
        actor=actor,
        data_mode=data_mode,
        payload_json=payload_json,
    )
    session.add(event)
    return event


def get_recommendation_run(session: Session, recommendation_id: str) -> RecommendationRun | None:
    return session.get(RecommendationRun, recommendation_id)


def list_recent_recommendation_runs(session: Session, *, limit: int) -> list[RecommendationRun]:
    statement = select(RecommendationRun).order_by(RecommendationRun.created_at.desc()).limit(limit)
    return list(session.scalars(statement))


def list_all_recommendation_runs(session: Session) -> list[RecommendationRun]:
    statement = select(RecommendationRun).order_by(RecommendationRun.created_at.desc())
    return list(session.scalars(statement))


def add_recommendation_review(
    session: Session,
    *,
    review_id: str,
    recommendation_id: str,
    created_at: datetime,
    review_status: str,
    note: str,
    actor: str,
) -> RecommendationReview:
    review = RecommendationReview(
        review_id=review_id,
        recommendation_id=recommendation_id,
        created_at=created_at,
        actor=actor,
        review_status=review_status,
        note=note,
    )
    session.add(review)
    return review


def list_recommendation_reviews(
    session: Session, recommendation_id: str
) -> list[RecommendationReview]:
    statement = (
        select(RecommendationReview)
        .where(RecommendationReview.recommendation_id == recommendation_id)
        .order_by(RecommendationReview.created_at.asc())
    )
    return list(session.scalars(statement))


def add_recommendation_decision(
    session: Session,
    *,
    decision_id: str,
    recommendation_id: str,
    created_at: datetime,
    decision_status: str,
    selected_windows_json: list[str],
    note: str,
    safety_boundary_acknowledged: bool,
    no_auto_trading: bool,
    audit_snapshot_json: dict[str, Any],
    actor: str,
) -> RecommendationDecision:
    decision = RecommendationDecision(
        decision_id=decision_id,
        recommendation_id=recommendation_id,
        created_at=created_at,
        actor=actor,
        decision_status=decision_status,
        selected_windows_json=selected_windows_json,
        note=note,
        safety_boundary_acknowledged=safety_boundary_acknowledged,
        no_auto_trading=no_auto_trading,
        audit_snapshot_json=audit_snapshot_json,
    )
    session.add(decision)
    return decision


def get_recommendation_decision(
    session: Session, decision_id: str
) -> RecommendationDecision | None:
    return session.get(RecommendationDecision, decision_id)


def list_recommendation_decisions(
    session: Session, recommendation_id: str
) -> list[RecommendationDecision]:
    statement = (
        select(RecommendationDecision)
        .where(RecommendationDecision.recommendation_id == recommendation_id)
        .order_by(RecommendationDecision.created_at.asc())
    )
    return list(session.scalars(statement))


def list_all_recommendation_decisions(session: Session) -> list[RecommendationDecision]:
    statement = select(RecommendationDecision).order_by(RecommendationDecision.created_at.desc())
    return list(session.scalars(statement))


def add_recommendation_decision_feedback(
    session: Session,
    *,
    feedback_id: str,
    decision_id: str,
    recommendation_id: str,
    created_at: datetime,
    outcome_status: str,
    observed_at: date | None,
    note: str,
    actor: str,
    data_mode: str,
) -> RecommendationDecisionFeedback:
    feedback = RecommendationDecisionFeedback(
        feedback_id=feedback_id,
        decision_id=decision_id,
        recommendation_id=recommendation_id,
        created_at=created_at,
        actor=actor,
        outcome_status=outcome_status,
        observed_at=observed_at,
        note=note,
        data_mode=data_mode,
    )
    session.add(feedback)
    return feedback


def list_recommendation_decision_feedback(
    session: Session, decision_id: str
) -> list[RecommendationDecisionFeedback]:
    statement = (
        select(RecommendationDecisionFeedback)
        .where(RecommendationDecisionFeedback.decision_id == decision_id)
        .order_by(RecommendationDecisionFeedback.created_at.asc())
    )
    return list(session.scalars(statement))


def list_all_recommendation_decision_feedback(
    session: Session,
) -> list[RecommendationDecisionFeedback]:
    statement = select(RecommendationDecisionFeedback).order_by(
        RecommendationDecisionFeedback.created_at.desc()
    )
    return list(session.scalars(statement))
