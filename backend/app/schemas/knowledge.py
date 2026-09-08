from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentLayer = Literal[
    "official_policy", "official_market_notice", "public_research", "user_uploaded"
]
KnowledgeCorpusStatus = Literal["healthy", "warning", "critical"]
KnowledgeDocumentReviewAction = Literal["approved", "rejected", "needs_revision"]


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    title: str
    document_layer: DocumentLayer
    trust_tier: str
    source_name: str
    source_url: str | None
    media_type: str
    captured_at: datetime
    external_processing_allowed: bool
    human_review_status: str
    data_mode: str


class KnowledgeDocumentListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[KnowledgeDocumentResponse]


class KnowledgeCorpusLayerSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_layer: DocumentLayer
    document_count: int
    chunk_count: int
    embedded_chunk_count: int
    embedding_coverage: float
    external_processing_allowed_count: int
    latest_captured_at: datetime | None


class KnowledgeCorpusOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    status: KnowledgeCorpusStatus
    message: str
    document_count: int
    version_count: int
    chunk_count: int
    embedded_chunk_count: int
    embedding_coverage: float
    external_processing_allowed_count: int
    external_processing_blocked_count: int
    artifact_provenance_count: int
    layers: list[KnowledgeCorpusLayerSummary]
    recent_documents: list[KnowledgeDocumentResponse]
    network_probe_performed: bool
    fetch_performed: bool
    no_auto_trading: bool


class KnowledgeDocumentVersionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    version_id: str
    version_number: int
    content_sha256: str
    parser_key: str
    raw_object_id: str
    parsed_character_count: int
    created_at: datetime


class KnowledgeRawObjectSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_object_id: str
    content_sha256: str
    storage_backend: str
    bucket_name: str
    object_key: str
    media_type: str
    byte_length: int
    source_url: str | None
    captured_at: datetime
    data_mode: str


class KnowledgeArtifactProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    artifact_content_sha256: str | None = None
    artifact_captured_at: datetime | None = None
    source_id: str | None = None
    source_name: str | None = None
    source_trust_tier: str | None = None
    source_market_scope: str | None = None
    endpoint_id: str | None = None
    endpoint_name: str | None = None
    endpoint_kind: str | None = None
    endpoint_data_granularity: str | None = None
    source_url: str | None = None


class KnowledgeDocumentDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    title: str
    document_layer: DocumentLayer
    trust_tier: str
    source_name: str
    source_url: str | None
    media_type: str
    published_at: datetime | None
    effective_at: datetime | None
    captured_at: datetime
    external_processing_allowed: bool
    external_processing_allowed_default: bool
    human_review_status: str
    data_mode: str
    latest_version: KnowledgeDocumentVersionSummary | None
    raw_object: KnowledgeRawObjectSummary | None
    chunk_count: int
    embedded_chunk_count: int
    embedding_coverage: float
    artifact_provenance: list[KnowledgeArtifactProvenance]
    raw_download_available: bool


class KnowledgeChunkResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    ordinal: int
    content: str
    character_count: int
    embedding_model: str | None


class KnowledgeChunkListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[KnowledgeChunkResponse]


class ExternalProcessingAuthorizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_processing_allowed: bool
    note: str = Field(min_length=1, max_length=500)


class ExternalProcessingAuthorizationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization_audit_id: str
    document_id: str
    external_processing_allowed: bool
    actor: str
    note: str
    created_at: datetime


class KnowledgeDocumentReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_status: KnowledgeDocumentReviewAction
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("Knowledge document review note must not be blank.")
        return note


class KnowledgeDocumentReviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    document_id: str
    created_at: datetime
    actor: str
    review_status: KnowledgeDocumentReviewAction
    note: str


class KnowledgeDocumentReviewPackageChunkSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_count: int
    embedded_count: int
    embedding_coverage: float
    displayed_chunk_count: int


class KnowledgeDocumentReviewPackageChunkResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    ordinal: int
    content_sha256: str
    character_count: int
    embedding_model: str | None
    content_excerpt: str


class KnowledgeDocumentReviewPackageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_version: str
    generated_at: datetime
    document: KnowledgeDocumentDetailResponse
    chunk_summary: KnowledgeDocumentReviewPackageChunkSummary
    displayed_chunks: list[KnowledgeDocumentReviewPackageChunkResponse]
    reviews: list[KnowledgeDocumentReviewResponse]
    review_count: int
    external_processing_allowed: bool
    external_processing_allowed_default: bool
    raw_payload_included: bool
    server_artifact_written: bool
    no_auto_trading: bool
    recommendation_chain_isolated: bool
    network_probe_performed: bool
    fetch_performed: bool
    external_model_call_performed: bool
