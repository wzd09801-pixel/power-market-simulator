from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.intelligence import (
    IntelligenceBrief,
    IntelligenceBriefReview,
    IntelligenceQuestionRun,
)
from backend.app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
from backend.app.models.market import MarketQualityIssue
from backend.app.models.operations import WorkflowRun
from backend.app.models.weather import WeatherFeatureSnapshot


def add_brief(session: Session, brief: IntelligenceBrief) -> IntelligenceBrief:
    session.add(brief)
    return brief


def get_latest_brief(session: Session) -> IntelligenceBrief | None:
    return session.scalar(select(IntelligenceBrief).order_by(IntelligenceBrief.generated_at.desc()))


def list_briefs(session: Session, *, limit: int) -> list[IntelligenceBrief]:
    statement = (
        select(IntelligenceBrief).order_by(IntelligenceBrief.generated_at.desc()).limit(limit)
    )
    return list(session.scalars(statement))


def get_brief(session: Session, brief_id: str) -> IntelligenceBrief | None:
    return session.get(IntelligenceBrief, brief_id)


def add_brief_review(session: Session, review: IntelligenceBriefReview) -> IntelligenceBriefReview:
    session.add(review)
    return review


def list_brief_reviews(session: Session, brief_id: str) -> list[IntelligenceBriefReview]:
    statement = (
        select(IntelligenceBriefReview)
        .where(IntelligenceBriefReview.brief_id == brief_id)
        .order_by(IntelligenceBriefReview.created_at.asc())
    )
    return list(session.scalars(statement))


def add_question_run(session: Session, run: IntelligenceQuestionRun) -> IntelligenceQuestionRun:
    session.add(run)
    return run


def list_search_chunks(
    session: Session, *, limit: int
) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
    statement = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(
            KnowledgeDocumentVersion,
            KnowledgeChunk.version_id == KnowledgeDocumentVersion.version_id,
        )
        .join(
            KnowledgeDocument, KnowledgeDocumentVersion.document_id == KnowledgeDocument.document_id
        )
        .order_by(KnowledgeDocument.captured_at.desc(), KnowledgeChunk.ordinal)
        .limit(limit)
    )
    return list(session.execute(statement).tuples())


def count_recent_workflow_failures(session: Session) -> int:
    statement = select(WorkflowRun).where(WorkflowRun.status == "failed")
    return len(list(session.scalars(statement)))


def count_market_quality_issues(session: Session) -> int:
    return len(list(session.scalars(select(MarketQualityIssue))))


def count_weather_snapshots(session: Session) -> int:
    return len(list(session.scalars(select(WeatherFeatureSnapshot))))


def count_documents(session: Session) -> int:
    return len(list(session.scalars(select(KnowledgeDocument))))


def count_briefs_for_date(session: Session, target_date: date) -> int:
    return len(
        list(
            session.scalars(
                select(IntelligenceBrief).where(IntelligenceBrief.target_date == target_date)
            )
        )
    )
