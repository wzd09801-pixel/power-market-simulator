from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import cast
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session

from backend.app.core.errors import (
    AppError,
    MarketArtifactNotUsableError,
    MarketRawArtifactNotFoundError,
)
from backend.app.models.knowledge import (
    KnowledgeAuthorizationAudit,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentReview,
    KnowledgeDocumentVersion,
)
from backend.app.models.market import MarketDataSource, MarketRawArtifact, MarketSourceEndpoint
from backend.app.models.operations import RawObject
from backend.app.repositories.knowledge import (
    add_authorization_audit,
    add_chunk,
    add_document,
    add_document_review,
    add_document_version,
    get_document,
    get_document_by_source_content_hash,
    get_latest_document_version,
    list_all_document_versions,
    list_all_documents,
    list_chunks_for_document,
    list_chunks_for_version,
    list_chunks_with_documents,
    list_document_reviews,
    list_documents,
)
from backend.app.repositories.market import (
    get_market_endpoint,
    get_market_raw_artifact,
    get_market_source,
)
from backend.app.repositories.operations import get_raw_object
from backend.app.schemas.knowledge import (
    DocumentLayer,
    ExternalProcessingAuthorizationRequest,
    ExternalProcessingAuthorizationResponse,
    KnowledgeArtifactProvenance,
    KnowledgeChunkListResponse,
    KnowledgeChunkResponse,
    KnowledgeCorpusLayerSummary,
    KnowledgeCorpusOverviewResponse,
    KnowledgeCorpusStatus,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentReviewAction,
    KnowledgeDocumentReviewPackageChunkResponse,
    KnowledgeDocumentReviewPackageChunkSummary,
    KnowledgeDocumentReviewPackageResponse,
    KnowledgeDocumentReviewRequest,
    KnowledgeDocumentReviewResponse,
    KnowledgeDocumentVersionSummary,
    KnowledgeRawObjectSummary,
)
from backend.app.services.document_parsing import DocumentParsingError, chunk_text, parse_document
from backend.app.services.embeddings import EmbeddingClient
from backend.app.services.operations import preserve_raw_object
from backend.app.storage.blob_store import BlobStore, BlobStoreError

ARTIFACT_KNOWLEDGE_MEDIA_EXTENSIONS = {
    "text/html": ".html",
    "text/plain": ".txt",
}


def _now() -> datetime:
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))


def ingest_knowledge_document(
    *,
    filename: str,
    title: str,
    document_layer: DocumentLayer,
    source_name: str,
    source_url: str | None,
    media_type: str,
    content: bytes,
    store: BlobStore,
    embedding_client: EmbeddingClient,
    session: Session,
    published_at: datetime | None = None,
    effective_at: datetime | None = None,
    captured_at: datetime | None = None,
    metadata: dict[str, object] | None = None,
    merge_raw_object_metadata_on_duplicate: bool = False,
) -> KnowledgeDocumentResponse:
    try:
        parsed_text, parser_key = parse_document(
            filename=filename, media_type=media_type, content=content
        )
        parsed_chunks = chunk_text(parsed_text)
    except DocumentParsingError as exc:
        raise AppError(
            status_code=422,
            code="knowledge_document_parse_error",
            message=str(exc),
        ) from exc
    raw_metadata: dict[str, object] = {"filename": filename, "parser_key": parser_key}
    if metadata:
        raw_metadata.update(metadata)
    raw_object, _duplicate = preserve_raw_object(
        content=content,
        media_type=media_type,
        data_mode="user_uploaded" if document_layer == "user_uploaded" else "public_observed",
        source_url=source_url,
        metadata=raw_metadata,
        store=store,
        session=session,
        captured_at=captured_at,
        merge_metadata_on_duplicate=merge_raw_object_metadata_on_duplicate,
    )
    try:
        embeddings: list[list[float] | None] = [
            embedding
            for embedding in embedding_client.embed([chunk.content for chunk in parsed_chunks])
        ]
    except requests.RequestException:
        embeddings = [None] * len(parsed_chunks)
    document_id = f"knowledge_{uuid4().hex}"
    document_captured_at = captured_at or _now()
    with session.begin():
        document = add_document(
            session,
            KnowledgeDocument(
                document_id=document_id,
                title=title,
                document_layer=document_layer,
                trust_tier=_trust_tier(document_layer),
                source_name=source_name,
                source_url=source_url,
                media_type=media_type,
                published_at=published_at,
                effective_at=effective_at,
                captured_at=document_captured_at,
                external_processing_allowed=False,
                human_review_status="pending_review",
                data_mode="user_uploaded"
                if document_layer == "user_uploaded"
                else "public_observed",
            ),
        )
        version = add_document_version(
            session,
            KnowledgeDocumentVersion(
                version_id=f"knowledge_version_{uuid4().hex}",
                document_id=document_id,
                raw_object_id=raw_object.raw_object_id,
                version_number=1,
                content_sha256=raw_object.content_sha256,
                parser_key=parser_key,
                parsed_text=parsed_text,
            ),
        )
        for parsed_chunk, embedding in zip(parsed_chunks, embeddings, strict=True):
            add_chunk(
                session,
                KnowledgeChunk(
                    chunk_id=f"knowledge_chunk_{uuid4().hex}",
                    version_id=version.version_id,
                    ordinal=parsed_chunk.ordinal,
                    section_heading=None,
                    content=parsed_chunk.content,
                    character_count=len(parsed_chunk.content),
                    content_sha256=parsed_chunk.content_sha256,
                    embedding=embedding,
                    embedding_model=embedding_client.model if embedding is not None else None,
                ),
            )
    return _to_document_response(document)


def ingest_market_artifact_as_knowledge_document(
    artifact_id: str,
    *,
    store: BlobStore,
    embedding_client: EmbeddingClient,
    session: Session,
) -> KnowledgeDocumentResponse:
    with session.begin():
        artifact = get_market_raw_artifact(session, artifact_id)
        if artifact is None:
            raise MarketRawArtifactNotFoundError(artifact_id)
        endpoint = get_market_endpoint(session, artifact.endpoint_id)
        source = get_market_source(session, artifact.source_id)

    if endpoint is None or source is None or endpoint.source_id != artifact.source_id:
        raise MarketArtifactNotUsableError(
            artifact_id,
            "registered source or endpoint metadata is missing",
        )
    _ensure_artifact_can_enter_policy_knowledge(artifact, source, endpoint)
    content = _artifact_content(artifact, store)
    _ensure_artifact_content_hash_matches(artifact, content)
    document_layer = _document_layer_for_artifact(source, endpoint)
    source_name = f"{source.name} / {endpoint.name}"
    with session.begin():
        existing_document = get_document_by_source_content_hash(
            session,
            content_sha256=artifact.content_sha256,
            source_name=source_name,
            source_url=artifact.source_url,
            document_layer=document_layer,
        )
    if existing_document is not None:
        return _to_document_response(existing_document)
    return ingest_knowledge_document(
        filename=_artifact_filename(artifact),
        title=artifact.title or endpoint.name,
        document_layer=document_layer,
        source_name=source_name,
        source_url=artifact.source_url,
        media_type=artifact.media_type,
        content=content,
        store=store,
        embedding_client=embedding_client,
        session=session,
        published_at=artifact.published_at,
        captured_at=artifact.captured_at,
        metadata=_market_artifact_metadata(artifact, source, endpoint),
        merge_raw_object_metadata_on_duplicate=True,
    )


def get_knowledge_documents(*, limit: int, session: Session) -> KnowledgeDocumentListResponse:
    return KnowledgeDocumentListResponse(
        items=[_to_document_response(document) for document in list_documents(session, limit=limit)]
    )


def get_knowledge_corpus_overview(*, session: Session) -> KnowledgeCorpusOverviewResponse:
    documents = list_all_documents(session)
    versions = list_all_document_versions(session)
    chunk_rows = list_chunks_with_documents(session)
    chunk_count = len(chunk_rows)
    embedded_chunk_count = sum(1 for chunk, _document in chunk_rows if chunk.embedding is not None)
    layer_summaries = _corpus_layer_summaries(documents, chunk_rows)
    artifact_ids = _artifact_provenance_ids_for_versions(versions, session=session)
    external_allowed = sum(1 for document in documents if document.external_processing_allowed)
    status, message = _corpus_status(
        document_count=len(documents),
        chunk_count=chunk_count,
        embedded_chunk_count=embedded_chunk_count,
    )
    return KnowledgeCorpusOverviewResponse(
        generated_at=_now(),
        status=status,
        message=message,
        document_count=len(documents),
        version_count=len(versions),
        chunk_count=chunk_count,
        embedded_chunk_count=embedded_chunk_count,
        embedding_coverage=_coverage(embedded_chunk_count, chunk_count),
        external_processing_allowed_count=external_allowed,
        external_processing_blocked_count=len(documents) - external_allowed,
        artifact_provenance_count=len(artifact_ids),
        layers=layer_summaries,
        recent_documents=[_to_document_response(document) for document in documents[:5]],
        network_probe_performed=False,
        fetch_performed=False,
        no_auto_trading=True,
    )


def get_knowledge_document_detail(
    document_id: str, *, session: Session
) -> KnowledgeDocumentDetailResponse:
    document = _required_document(session, document_id)
    version = get_latest_document_version(session, document_id)
    raw_object = get_raw_object(session, version.raw_object_id) if version is not None else None
    chunks = list_chunks_for_version(session, version.version_id) if version is not None else []
    embedded_chunk_count = sum(1 for chunk in chunks if chunk.embedding is not None)
    metadata = raw_object.metadata_json if raw_object is not None else {}
    return KnowledgeDocumentDetailResponse(
        document_id=document.document_id,
        title=document.title,
        document_layer=cast(DocumentLayer, document.document_layer),
        trust_tier=document.trust_tier,
        source_name=document.source_name,
        source_url=document.source_url,
        media_type=document.media_type,
        published_at=document.published_at,
        effective_at=document.effective_at,
        captured_at=document.captured_at,
        external_processing_allowed=document.external_processing_allowed,
        external_processing_allowed_default=bool(
            metadata.get("external_processing_allowed_default", False)
        ),
        human_review_status=document.human_review_status,
        data_mode=document.data_mode,
        latest_version=_to_version_summary(version),
        raw_object=_to_raw_object_summary(raw_object),
        chunk_count=len(chunks),
        embedded_chunk_count=embedded_chunk_count,
        embedding_coverage=_coverage(embedded_chunk_count, len(chunks)),
        artifact_provenance=_artifact_provenance_for_document(document, metadata),
        raw_download_available=False,
    )


def get_knowledge_chunks(document_id: str, *, session: Session) -> KnowledgeChunkListResponse:
    _required_document(session, document_id)
    return KnowledgeChunkListResponse(
        items=[
            KnowledgeChunkResponse(
                chunk_id=chunk.chunk_id,
                ordinal=chunk.ordinal,
                content=chunk.content,
                character_count=chunk.character_count,
                embedding_model=chunk.embedding_model,
            )
            for chunk in list_chunks_for_document(session, document_id)
        ]
    )


def get_knowledge_document_review_package(
    document_id: str,
    *,
    session: Session,
    chunk_limit: int = 5,
) -> KnowledgeDocumentReviewPackageResponse:
    detail = get_knowledge_document_detail(document_id, session=session)
    version = get_latest_document_version(session, document_id)
    chunks = list_chunks_for_version(session, version.version_id) if version is not None else []
    displayed_chunks = chunks[:chunk_limit]
    embedded_chunk_count = sum(1 for chunk in chunks if chunk.embedding is not None)
    reviews = list_document_reviews(session, document_id)
    return KnowledgeDocumentReviewPackageResponse(
        package_version="policy_document_review_package_v1",
        generated_at=_now(),
        document=detail,
        chunk_summary=KnowledgeDocumentReviewPackageChunkSummary(
            total_count=len(chunks),
            embedded_count=embedded_chunk_count,
            embedding_coverage=_coverage(embedded_chunk_count, len(chunks)),
            displayed_chunk_count=len(displayed_chunks),
        ),
        displayed_chunks=[
            KnowledgeDocumentReviewPackageChunkResponse(
                chunk_id=chunk.chunk_id,
                ordinal=chunk.ordinal,
                content_sha256=chunk.content_sha256,
                character_count=chunk.character_count,
                embedding_model=chunk.embedding_model,
                content_excerpt=_content_excerpt(chunk.content),
            )
            for chunk in displayed_chunks
        ],
        reviews=[_to_document_review_response(review) for review in reviews],
        review_count=len(reviews),
        external_processing_allowed=detail.external_processing_allowed,
        external_processing_allowed_default=detail.external_processing_allowed_default,
        raw_payload_included=False,
        server_artifact_written=False,
        no_auto_trading=True,
        recommendation_chain_isolated=True,
        network_probe_performed=False,
        fetch_performed=False,
        external_model_call_performed=False,
    )


def set_external_processing_authorization(
    document_id: str,
    request: ExternalProcessingAuthorizationRequest,
    *,
    session: Session,
) -> ExternalProcessingAuthorizationResponse:
    created_at = _now()
    with session.begin():
        document = _required_document(session, document_id)
        document.external_processing_allowed = request.external_processing_allowed
        audit = add_authorization_audit(
            session,
            KnowledgeAuthorizationAudit(
                authorization_audit_id=f"knowledge_auth_{uuid4().hex}",
                document_id=document_id,
                actor="local_operator",
                external_processing_allowed=request.external_processing_allowed,
                note=request.note,
                created_at=created_at,
            ),
        )
    return ExternalProcessingAuthorizationResponse(
        authorization_audit_id=audit.authorization_audit_id,
        document_id=document_id,
        external_processing_allowed=audit.external_processing_allowed,
        actor=audit.actor,
        note=audit.note,
        created_at=audit.created_at,
    )


def review_knowledge_document(
    document_id: str,
    request: KnowledgeDocumentReviewRequest,
    *,
    session: Session,
) -> KnowledgeDocumentReviewResponse:
    created_at = _now()
    with session.begin():
        document = _required_document(session, document_id)
        review = add_document_review(
            session,
            KnowledgeDocumentReview(
                review_id=f"knowledge_review_{uuid4().hex}",
                document_id=document_id,
                created_at=created_at,
                actor="local_operator",
                review_status=request.review_status,
                note=request.note,
            ),
        )
        document.human_review_status = request.review_status
    return KnowledgeDocumentReviewResponse(
        review_id=review.review_id,
        document_id=review.document_id,
        created_at=review.created_at,
        actor=review.actor,
        review_status=cast(KnowledgeDocumentReviewAction, review.review_status),
        note=review.note,
    )


def _required_document(session: Session, document_id: str) -> KnowledgeDocument:
    document = get_document(session, document_id)
    if document is None:
        raise AppError(
            status_code=404,
            code="knowledge_document_not_found",
            message=f"Knowledge document '{document_id}' was not found.",
        )
    return document


def _trust_tier(document_layer: DocumentLayer) -> str:
    if document_layer in {"official_policy", "official_market_notice"}:
        return "official"
    if document_layer == "public_research":
        return "public_research"
    return "user_uploaded"


def _ensure_artifact_can_enter_policy_knowledge(
    artifact: MarketRawArtifact,
    source: MarketDataSource,
    endpoint: MarketSourceEndpoint,
) -> None:
    if artifact.data_mode != "public_observed":
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            "artifact data_mode must be public_observed",
        )
    if artifact.media_type not in ARTIFACT_KNOWLEDGE_MEDIA_EXTENSIONS:
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            f"unsupported media type {artifact.media_type}",
        )
    research_markers = (
        source.source_id,
        source.market_scope,
        source.notes,
        endpoint.endpoint_id,
        endpoint.notes,
        endpoint.data_granularity,
    )
    normalized_markers = " ".join(marker.lower() for marker in research_markers)
    if (
        "bench" in normalized_markers
        or "bench_nem_dispatch_benchmark" in normalized_markers
        or "research_only" in normalized_markers
    ):
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            "research_only or BENCH artifacts cannot enter demo policy knowledge",
        )


def _artifact_content(artifact: MarketRawArtifact, store: BlobStore) -> bytes:
    if artifact.inline_text is not None and artifact.inline_text.strip():
        return artifact.inline_text.encode("utf-8")
    if artifact.object_key is not None:
        try:
            content = store.get(object_key=artifact.object_key)
        except BlobStoreError as exc:
            raise AppError(
                status_code=502,
                code="knowledge_artifact_storage_error",
                message=f"Stored market artifact '{artifact.artifact_id}' could not be read.",
            ) from exc
        if content:
            return content
    raise MarketArtifactNotUsableError(
        artifact.artifact_id,
        "artifact contains no importable text content",
    )


def _ensure_artifact_content_hash_matches(artifact: MarketRawArtifact, content: bytes) -> None:
    actual_sha256 = sha256(content).hexdigest()
    if actual_sha256 != artifact.content_sha256:
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            "artifact content hash does not match preserved metadata",
        )


def _market_artifact_metadata(
    artifact: MarketRawArtifact,
    source: MarketDataSource,
    endpoint: MarketSourceEndpoint,
) -> dict[str, object]:
    provenance = {
        "artifact_id": artifact.artifact_id,
        "artifact_content_sha256": artifact.content_sha256,
        "artifact_captured_at": artifact.captured_at.isoformat(),
        "source_id": source.source_id,
        "source_name": source.name,
        "source_trust_tier": source.trust_tier,
        "source_market_scope": source.market_scope,
        "endpoint_id": endpoint.endpoint_id,
        "endpoint_name": endpoint.name,
        "endpoint_kind": endpoint.endpoint_kind,
        "endpoint_data_granularity": endpoint.data_granularity,
        "source_url": artifact.source_url,
    }
    return {
        "ingestion_bridge": "market_raw_artifact",
        **provenance,
        "market_artifact_imports": [provenance],
        "external_processing_allowed_default": False,
    }


def _artifact_filename(artifact: MarketRawArtifact) -> str:
    source_path = urlparse(artifact.source_url).path
    source_suffix = ""
    if "." in source_path.rsplit("/", 1)[-1]:
        source_suffix = f".{source_path.rsplit('.', 1)[-1].lower()}"
    extension = ARTIFACT_KNOWLEDGE_MEDIA_EXTENSIONS[artifact.media_type]
    suffix = (
        source_suffix
        if source_suffix in set(ARTIFACT_KNOWLEDGE_MEDIA_EXTENSIONS.values())
        else extension
    )
    return f"{artifact.artifact_id}{suffix}"


def _document_layer_for_artifact(
    source: MarketDataSource, endpoint: MarketSourceEndpoint
) -> DocumentLayer:
    endpoint_text = " ".join(
        [
            endpoint.endpoint_kind,
            endpoint.data_granularity,
            endpoint.name,
            source.market_scope,
        ]
    ).lower()
    if source.trust_tier == "official" and "notice" in endpoint_text:
        return "official_market_notice"
    if source.trust_tier == "official" and (
        "policy" in endpoint_text or "regulator" in endpoint_text
    ):
        return "official_policy"
    if source.trust_tier == "official" and "market" in endpoint_text:
        return "official_market_notice"
    return "public_research"


def _coverage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _corpus_status(
    *, document_count: int, chunk_count: int, embedded_chunk_count: int
) -> tuple[KnowledgeCorpusStatus, str]:
    if document_count == 0:
        return "warning", "No policy or research documents are available in the local corpus."
    if chunk_count == 0:
        return "warning", "Documents exist but no searchable chunks are available."
    if embedded_chunk_count < chunk_count:
        return (
            "warning",
            "Some chunks do not have embeddings; local search will rely more on lexical matching.",
        )
    return "healthy", "Policy corpus is indexed with local chunks and embeddings."


def _corpus_layer_summaries(
    documents: list[KnowledgeDocument],
    chunk_rows: list[tuple[KnowledgeChunk, KnowledgeDocument]],
) -> list[KnowledgeCorpusLayerSummary]:
    layers = sorted({document.document_layer for document in documents})
    summaries: list[KnowledgeCorpusLayerSummary] = []
    for layer in layers:
        layer_documents = [document for document in documents if document.document_layer == layer]
        layer_chunks = [chunk for chunk, document in chunk_rows if document.document_layer == layer]
        embedded_chunk_count = sum(1 for chunk in layer_chunks if chunk.embedding is not None)
        latest_captured_at = max(
            (document.captured_at for document in layer_documents),
            default=None,
        )
        summaries.append(
            KnowledgeCorpusLayerSummary(
                document_layer=cast(DocumentLayer, layer),
                document_count=len(layer_documents),
                chunk_count=len(layer_chunks),
                embedded_chunk_count=embedded_chunk_count,
                embedding_coverage=_coverage(embedded_chunk_count, len(layer_chunks)),
                external_processing_allowed_count=sum(
                    1 for document in layer_documents if document.external_processing_allowed
                ),
                latest_captured_at=latest_captured_at,
            )
        )
    return summaries


def _artifact_provenance_ids_for_versions(
    versions: list[KnowledgeDocumentVersion], *, session: Session
) -> set[str]:
    artifact_ids: set[str] = set()
    raw_object_ids = {version.raw_object_id for version in versions}
    for raw_object_id in raw_object_ids:
        raw_object = get_raw_object(session, raw_object_id)
        if raw_object is None:
            continue
        for provenance in _artifact_provenance_from_metadata(raw_object.metadata_json):
            artifact_ids.add(provenance.artifact_id)
    return artifact_ids


def _to_version_summary(
    version: KnowledgeDocumentVersion | None,
) -> KnowledgeDocumentVersionSummary | None:
    if version is None:
        return None
    return KnowledgeDocumentVersionSummary(
        version_id=version.version_id,
        version_number=version.version_number,
        content_sha256=version.content_sha256,
        parser_key=version.parser_key,
        raw_object_id=version.raw_object_id,
        parsed_character_count=len(version.parsed_text),
        created_at=version.created_at,
    )


def _to_raw_object_summary(raw_object: RawObject | None) -> KnowledgeRawObjectSummary | None:
    if raw_object is None:
        return None
    return KnowledgeRawObjectSummary.model_validate(raw_object, from_attributes=True)


def _artifact_provenance_from_metadata(
    metadata: dict[str, object] | None,
) -> list[KnowledgeArtifactProvenance]:
    if not metadata:
        return []
    raw_entries = metadata.get("market_artifact_imports")
    entries: list[dict[str, object]] = []
    if isinstance(raw_entries, list):
        entries = [entry for entry in raw_entries if isinstance(entry, dict)]
    elif isinstance(metadata.get("artifact_id"), str):
        entries = [metadata]
    provenances: list[KnowledgeArtifactProvenance] = []
    seen_artifact_ids: set[str] = set()
    for entry in entries:
        artifact_id = _optional_str(entry.get("artifact_id"))
        if artifact_id is None or artifact_id in seen_artifact_ids:
            continue
        seen_artifact_ids.add(artifact_id)
        provenances.append(
            KnowledgeArtifactProvenance(
                artifact_id=artifact_id,
                artifact_content_sha256=_optional_str(entry.get("artifact_content_sha256")),
                artifact_captured_at=_optional_datetime(entry.get("artifact_captured_at")),
                source_id=_optional_str(entry.get("source_id")),
                source_name=_optional_str(entry.get("source_name")),
                source_trust_tier=_optional_str(entry.get("source_trust_tier")),
                source_market_scope=_optional_str(entry.get("source_market_scope")),
                endpoint_id=_optional_str(entry.get("endpoint_id")),
                endpoint_name=_optional_str(entry.get("endpoint_name")),
                endpoint_kind=_optional_str(entry.get("endpoint_kind")),
                endpoint_data_granularity=_optional_str(entry.get("endpoint_data_granularity")),
                source_url=_optional_str(entry.get("source_url")),
            )
        )
    return provenances


def _artifact_provenance_for_document(
    document: KnowledgeDocument, metadata: dict[str, object] | None
) -> list[KnowledgeArtifactProvenance]:
    if document.document_layer == "user_uploaded":
        return []
    provenances = _artifact_provenance_from_metadata(metadata)
    return [
        provenance
        for provenance in provenances
        if _document_matches_artifact_provenance(document, provenance)
    ]


def _document_matches_artifact_provenance(
    document: KnowledgeDocument, provenance: KnowledgeArtifactProvenance
) -> bool:
    if provenance.source_url is not None and provenance.source_url != document.source_url:
        return False
    if provenance.source_name is not None and provenance.source_name not in document.source_name:
        return False
    if (
        provenance.endpoint_name is not None
        and provenance.endpoint_name not in document.source_name
    ):
        return False
    return True


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _content_excerpt(content: str, *, max_length: int = 240) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


def _to_document_review_response(
    review: KnowledgeDocumentReview,
) -> KnowledgeDocumentReviewResponse:
    return KnowledgeDocumentReviewResponse(
        review_id=review.review_id,
        document_id=review.document_id,
        created_at=review.created_at,
        actor=review.actor,
        review_status=cast(KnowledgeDocumentReviewAction, review.review_status),
        note=review.note,
    )


def _to_document_response(document: KnowledgeDocument) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse.model_validate(document, from_attributes=True)
