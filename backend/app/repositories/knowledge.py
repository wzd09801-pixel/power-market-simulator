from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.knowledge import (
    KnowledgeAuthorizationAudit,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentReview,
    KnowledgeDocumentVersion,
)


def add_document(session: Session, document: KnowledgeDocument) -> KnowledgeDocument:
    session.add(document)
    return document


def get_document(session: Session, document_id: str) -> KnowledgeDocument | None:
    return session.get(KnowledgeDocument, document_id)


def get_document_by_source_content_hash(
    session: Session,
    *,
    content_sha256: str,
    source_name: str,
    source_url: str | None,
    document_layer: str,
) -> KnowledgeDocument | None:
    statement = (
        select(KnowledgeDocument)
        .join(KnowledgeDocumentVersion)
        .where(
            KnowledgeDocumentVersion.content_sha256 == content_sha256,
            KnowledgeDocument.source_name == source_name,
            KnowledgeDocument.source_url == source_url,
            KnowledgeDocument.document_layer == document_layer,
        )
        .order_by(KnowledgeDocument.captured_at.desc())
        .limit(1)
    )
    return session.scalar(statement)


def list_documents(session: Session, *, limit: int) -> list[KnowledgeDocument]:
    statement = (
        select(KnowledgeDocument).order_by(KnowledgeDocument.captured_at.desc()).limit(limit)
    )
    return list(session.scalars(statement))


def list_all_documents(session: Session) -> list[KnowledgeDocument]:
    statement = select(KnowledgeDocument).order_by(KnowledgeDocument.captured_at.desc())
    return list(session.scalars(statement))


def add_document_version(
    session: Session, version: KnowledgeDocumentVersion
) -> KnowledgeDocumentVersion:
    session.add(version)
    return version


def count_document_versions(session: Session, document_id: str) -> int:
    statement = (
        select(func.count())
        .select_from(KnowledgeDocumentVersion)
        .where(KnowledgeDocumentVersion.document_id == document_id)
    )
    return int(session.scalar(statement) or 0)


def get_latest_document_version(
    session: Session, document_id: str
) -> KnowledgeDocumentVersion | None:
    statement = (
        select(KnowledgeDocumentVersion)
        .where(KnowledgeDocumentVersion.document_id == document_id)
        .order_by(
            KnowledgeDocumentVersion.version_number.desc(),
            KnowledgeDocumentVersion.created_at.desc(),
        )
        .limit(1)
    )
    return session.scalar(statement)


def list_all_document_versions(session: Session) -> list[KnowledgeDocumentVersion]:
    statement = select(KnowledgeDocumentVersion)
    return list(session.scalars(statement))


def add_chunk(session: Session, chunk: KnowledgeChunk) -> KnowledgeChunk:
    session.add(chunk)
    return chunk


def list_chunks_for_document(session: Session, document_id: str) -> list[KnowledgeChunk]:
    statement = (
        select(KnowledgeChunk)
        .join(KnowledgeDocumentVersion)
        .where(KnowledgeDocumentVersion.document_id == document_id)
        .order_by(KnowledgeDocumentVersion.version_number.desc(), KnowledgeChunk.ordinal)
    )
    return list(session.scalars(statement))


def list_chunks_for_version(session: Session, version_id: str) -> list[KnowledgeChunk]:
    statement = (
        select(KnowledgeChunk)
        .where(KnowledgeChunk.version_id == version_id)
        .order_by(KnowledgeChunk.ordinal)
    )
    return list(session.scalars(statement))


def list_chunks_with_documents(
    session: Session,
) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
    statement = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(
            KnowledgeDocumentVersion,
            KnowledgeChunk.version_id == KnowledgeDocumentVersion.version_id,
        )
        .join(
            KnowledgeDocument,
            KnowledgeDocumentVersion.document_id == KnowledgeDocument.document_id,
        )
    )
    return list(session.execute(statement).tuples())


def list_latest_chunks(session: Session, *, limit: int) -> list[KnowledgeChunk]:
    statement = select(KnowledgeChunk).order_by(KnowledgeChunk.chunk_id).limit(limit)
    return list(session.scalars(statement))


def add_authorization_audit(
    session: Session, audit: KnowledgeAuthorizationAudit
) -> KnowledgeAuthorizationAudit:
    session.add(audit)
    return audit


def add_document_review(
    session: Session, review: KnowledgeDocumentReview
) -> KnowledgeDocumentReview:
    session.add(review)
    return review


def list_document_reviews(session: Session, document_id: str) -> list[KnowledgeDocumentReview]:
    statement = (
        select(KnowledgeDocumentReview)
        .where(KnowledgeDocumentReview.document_id == document_id)
        .order_by(KnowledgeDocumentReview.created_at.desc())
    )
    return list(session.scalars(statement))
