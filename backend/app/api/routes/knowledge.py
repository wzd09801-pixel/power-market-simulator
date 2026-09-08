from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_db_session
from backend.app.schemas.knowledge import (
    DocumentLayer,
    ExternalProcessingAuthorizationRequest,
    ExternalProcessingAuthorizationResponse,
    KnowledgeChunkListResponse,
    KnowledgeCorpusOverviewResponse,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentReviewPackageResponse,
    KnowledgeDocumentReviewRequest,
    KnowledgeDocumentReviewResponse,
)
from backend.app.services.embeddings import EmbeddingClient, get_embedding_client
from backend.app.services.knowledge import (
    get_knowledge_chunks,
    get_knowledge_corpus_overview,
    get_knowledge_document_detail,
    get_knowledge_document_review_package,
    get_knowledge_documents,
    ingest_knowledge_document,
    ingest_market_artifact_as_knowledge_document,
    review_knowledge_document,
    set_external_processing_authorization,
)
from backend.app.storage.blob_store import BlobStore, MinioBlobStore

router = APIRouter(prefix="/v1/policy", tags=["policy-knowledge"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


def get_blob_store() -> BlobStore:
    return MinioBlobStore(get_settings())


BlobStoreDependency = Annotated[BlobStore, Depends(get_blob_store)]
EmbeddingClientDependency = Annotated[EmbeddingClient, Depends(get_embedding_client)]


@router.post("/documents/upload", response_model=KnowledgeDocumentResponse)
async def upload_document(
    session: SessionDependency,
    store: BlobStoreDependency,
    embedding_client: EmbeddingClientDependency,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=300)],
    document_layer: Annotated[DocumentLayer, Form()],
    source_name: Annotated[str, Form(min_length=1, max_length=160)] = "Local operator upload",
    source_url: Annotated[str | None, Form(max_length=2000)] = None,
) -> KnowledgeDocumentResponse:
    content = await file.read()
    return ingest_knowledge_document(
        filename=file.filename or "uploaded-document",
        title=title,
        document_layer=document_layer,
        source_name=source_name,
        source_url=source_url,
        media_type=file.content_type or "application/octet-stream",
        content=content,
        store=store,
        embedding_client=embedding_client,
        session=session,
    )


@router.post(
    "/documents/from-market-artifact/{artifact_id}",
    response_model=KnowledgeDocumentResponse,
)
def import_market_artifact_document(
    artifact_id: str,
    session: SessionDependency,
    store: BlobStoreDependency,
    embedding_client: EmbeddingClientDependency,
) -> KnowledgeDocumentResponse:
    return ingest_market_artifact_as_knowledge_document(
        artifact_id,
        store=store,
        embedding_client=embedding_client,
        session=session,
    )


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def list_documents(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> KnowledgeDocumentListResponse:
    return get_knowledge_documents(limit=limit, session=session)


@router.get("/corpus/overview", response_model=KnowledgeCorpusOverviewResponse)
def corpus_overview(session: SessionDependency) -> KnowledgeCorpusOverviewResponse:
    return get_knowledge_corpus_overview(session=session)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDetailResponse)
def document_detail(
    document_id: str, session: SessionDependency
) -> KnowledgeDocumentDetailResponse:
    return get_knowledge_document_detail(document_id, session=session)


@router.get(
    "/documents/{document_id}/review-package",
    response_model=KnowledgeDocumentReviewPackageResponse,
)
def document_review_package(
    document_id: str,
    session: SessionDependency,
    chunk_limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> KnowledgeDocumentReviewPackageResponse:
    return get_knowledge_document_review_package(
        document_id,
        session=session,
        chunk_limit=chunk_limit,
    )


@router.get("/documents/{document_id}/chunks", response_model=KnowledgeChunkListResponse)
def list_document_chunks(
    document_id: str, session: SessionDependency
) -> KnowledgeChunkListResponse:
    return get_knowledge_chunks(document_id, session=session)


@router.post(
    "/documents/{document_id}/external-processing-authorization",
    response_model=ExternalProcessingAuthorizationResponse,
)
def authorize_external_processing(
    document_id: str,
    request: ExternalProcessingAuthorizationRequest,
    session: SessionDependency,
) -> ExternalProcessingAuthorizationResponse:
    return set_external_processing_authorization(document_id, request, session=session)


@router.post(
    "/documents/{document_id}/reviews",
    response_model=KnowledgeDocumentReviewResponse,
)
def review_document(
    document_id: str,
    request: KnowledgeDocumentReviewRequest,
    session: SessionDependency,
) -> KnowledgeDocumentReviewResponse:
    return review_knowledge_document(document_id, request, session=session)
