from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class IntelligenceBrief(Base):
    __tablename__ = "intelligence_briefs"

    brief_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(40))
    human_review_status: Mapped[str] = mapped_column(String(40), default="pending_review")
    risk_level: Mapped[str] = mapped_column(String(40))
    confidence_score: Mapped[float] = mapped_column(Float)
    deterministic_facts_json: Mapped[dict[str, object]] = mapped_column(JSON)
    narrative_json: Mapped[dict[str, object]] = mapped_column(JSON)
    citations_json: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    missing_information_json: Mapped[list[str]] = mapped_column(JSON)
    llm_used: Mapped[bool] = mapped_column(Boolean)
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    no_auto_trading: Mapped[bool] = mapped_column(Boolean, default=True)


class IntelligenceBriefReview(Base):
    __tablename__ = "intelligence_brief_reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    brief_id: Mapped[str] = mapped_column(ForeignKey("intelligence_briefs.brief_id"), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="local_operator")
    review_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntelligenceQuestionRun(Base):
    __tablename__ = "intelligence_question_runs"

    question_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    analysis_mode: Mapped[str] = mapped_column(String(40))
    answer: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    missing_information_json: Mapped[list[str]] = mapped_column(JSON)
    retrieved_chunk_ids_json: Mapped[list[str]] = mapped_column(JSON)
    excluded_restricted_chunks: Mapped[int] = mapped_column(Integer)
    confidence_score: Mapped[float] = mapped_column(Float)
    human_review_required: Mapped[bool] = mapped_column(Boolean)
    llm_used: Mapped[bool] = mapped_column(Boolean)
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
