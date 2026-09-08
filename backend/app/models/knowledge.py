from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    document_layer: Mapped[str] = mapped_column(String(40), index=True)
    trust_tier: Mapped[str] = mapped_column(String(40))
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str] = mapped_column(String(160))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    external_processing_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    human_review_status: Mapped[str] = mapped_column(String(40), default="pending_review")
    data_mode: Mapped[str] = mapped_column(String(40))


class KnowledgeDocumentVersion(Base):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_knowledge_version_number"),
        UniqueConstraint("document_id", "content_sha256", name="uq_knowledge_document_hash"),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.document_id"), index=True
    )
    raw_object_id: Mapped[str] = mapped_column(ForeignKey("raw_objects.raw_object_id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    parser_key: Mapped[str] = mapped_column(String(80))
    parsed_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("version_id", "ordinal", name="uq_knowledge_chunk_ordinal"),)

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_document_versions.version_id"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    section_heading: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    character_count: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)


class KnowledgeAuthorizationAudit(Base):
    __tablename__ = "knowledge_authorization_audits"

    authorization_audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.document_id"), index=True
    )
    actor: Mapped[str] = mapped_column(String(120))
    external_processing_allowed: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeDocumentReview(Base):
    __tablename__ = "knowledge_document_reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.document_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(120))
    review_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
