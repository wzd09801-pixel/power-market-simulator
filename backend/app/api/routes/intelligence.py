from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.schemas.intelligence import (
    IntelligenceBriefDetailResponse,
    IntelligenceBriefGenerateRequest,
    IntelligenceBriefListResponse,
    IntelligenceBriefResponse,
    IntelligenceBriefReviewRequest,
    IntelligenceBriefReviewResponse,
    IntelligenceQuestionRequest,
    IntelligenceQuestionResponse,
    IntelligenceSearchRequest,
    IntelligenceSearchResponse,
    PolicyWatchResponse,
)
from backend.app.services.deepseek import DeepSeekClient, get_deepseek_client
from backend.app.services.embeddings import EmbeddingClient, get_embedding_client
from backend.app.services.intelligence import (
    answer_intelligence_question,
    generate_intelligence_brief,
    get_intelligence_brief_detail,
    get_latest_intelligence_brief,
    get_policy_watch,
    list_intelligence_briefs,
    review_intelligence_brief,
    search_intelligence,
)

router = APIRouter(prefix="/v1/intelligence", tags=["intelligence"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
EmbeddingClientDependency = Annotated[EmbeddingClient, Depends(get_embedding_client)]
DeepSeekClientDependency = Annotated[DeepSeekClient, Depends(get_deepseek_client)]


@router.post("/search", response_model=IntelligenceSearchResponse)
def search(
    request: IntelligenceSearchRequest,
    session: SessionDependency,
    embedding_client: EmbeddingClientDependency,
) -> IntelligenceSearchResponse:
    return search_intelligence(request, session=session, embedding_client=embedding_client)


@router.get("/policy-watch", response_model=PolicyWatchResponse)
def policy_watch(
    session: SessionDependency,
    embedding_client: EmbeddingClientDependency,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> PolicyWatchResponse:
    return get_policy_watch(limit=limit, session=session, embedding_client=embedding_client)


@router.post("/questions", response_model=IntelligenceQuestionResponse)
def answer_question(
    request: IntelligenceQuestionRequest,
    session: SessionDependency,
    embedding_client: EmbeddingClientDependency,
    deepseek_client: DeepSeekClientDependency,
) -> IntelligenceQuestionResponse:
    return answer_intelligence_question(
        request,
        session=session,
        embedding_client=embedding_client,
        deepseek_client=deepseek_client,
    )


@router.post("/briefs/generate", response_model=IntelligenceBriefResponse)
def generate_brief(
    request: IntelligenceBriefGenerateRequest,
    session: SessionDependency,
    embedding_client: EmbeddingClientDependency,
    deepseek_client: DeepSeekClientDependency,
) -> IntelligenceBriefResponse:
    return generate_intelligence_brief(
        request,
        session=session,
        embedding_client=embedding_client,
        deepseek_client=deepseek_client,
    )


@router.get("/briefs", response_model=IntelligenceBriefListResponse)
def briefs(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> IntelligenceBriefListResponse:
    return list_intelligence_briefs(limit=limit, session=session)


@router.get("/briefs/latest", response_model=IntelligenceBriefResponse)
def latest_brief(session: SessionDependency) -> IntelligenceBriefResponse:
    return get_latest_intelligence_brief(session=session)


@router.get("/briefs/{brief_id}", response_model=IntelligenceBriefDetailResponse)
def brief_detail(brief_id: str, session: SessionDependency) -> IntelligenceBriefDetailResponse:
    return get_intelligence_brief_detail(brief_id, session=session)


@router.post("/briefs/{brief_id}/reviews", response_model=IntelligenceBriefReviewResponse)
def review_brief(
    brief_id: str,
    request: IntelligenceBriefReviewRequest,
    session: SessionDependency,
) -> IntelligenceBriefReviewResponse:
    return review_intelligence_brief(brief_id, request, session=session)
