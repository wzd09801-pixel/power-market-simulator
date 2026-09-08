from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor: Mapped[str] = mapped_column(String(120), default="system")
    data_mode: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"

    rec_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    input_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("feature_snapshots.snapshot_id"), index=True
    )
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    asset_id: Mapped[str] = mapped_column(String(80))
    data_mode: Mapped[str] = mapped_column(String(40))
    scenario_id: Mapped[str] = mapped_column(String(120), index=True)
    risk_level: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    strategy_json: Mapped[dict[str, object]] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(40), default="pending_review")


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    asset_id: Mapped[str] = mapped_column(String(80))
    scenario_id: Mapped[str] = mapped_column(String(120), index=True)
    data_mode: Mapped[str] = mapped_column(String(40))
    inputs_json: Mapped[dict[str, object]] = mapped_column(JSON)
    evidence_json: Mapped[list[dict[str, object]]] = mapped_column(JSON)


class RecommendationReview(Base):
    __tablename__ = "recommendation_reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_runs.rec_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(120), default="local_operator")
    review_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)


class RecommendationDecision(Base):
    __tablename__ = "recommendation_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_runs.rec_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(120), default="local_operator")
    decision_status: Mapped[str] = mapped_column(String(40))
    selected_windows_json: Mapped[list[str]] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text)
    safety_boundary_acknowledged: Mapped[bool] = mapped_column(Boolean)
    no_auto_trading: Mapped[bool] = mapped_column(Boolean)
    audit_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)


class RecommendationDecisionFeedback(Base):
    __tablename__ = "recommendation_decision_feedback"

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_decisions.decision_id"), index=True
    )
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_runs.rec_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(120), default="local_operator")
    outcome_status: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text)
    data_mode: Mapped[str] = mapped_column(String(40), default="user_uploaded")
