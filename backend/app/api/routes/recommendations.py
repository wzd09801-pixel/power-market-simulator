from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.schemas.recommendation import (
    RecommendationAuditResponse,
    RecommendationDecisionFeedbackRequest,
    RecommendationDecisionFeedbackResponse,
    RecommendationDecisionListResponse,
    RecommendationDecisionRequest,
    RecommendationDecisionResponse,
    RecommendationDetailResponse,
    RecommendationEvidenceExportResponse,
    RecommendationFeedbackAnalyticsResponse,
    RecommendationRecentResponse,
    RecommendationReviewRequest,
    RecommendationReviewResponse,
    RecommendationRunRequest,
    RecommendationRunResponse,
)
from backend.app.services.recommendations import (
    create_recommendation_decision,
    create_recommendation_decision_feedback,
    generate_recommendation,
    get_recent_recommendations,
    get_recommendation_audit,
    get_recommendation_detail,
    get_recommendation_evidence_export,
    get_recommendation_feedback_analytics,
    list_recommendation_decision_log,
    review_recommendation,
)

router = APIRouter(prefix="/v1/recommendations", tags=["recommendations"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.post("/run", response_model=RecommendationRunResponse)
def run_recommendation(
    request: RecommendationRunRequest, session: SessionDependency
) -> RecommendationRunResponse:
    return generate_recommendation(request, session)


@router.get("/recent", response_model=RecommendationRecentResponse)
def list_recent_recommendations(
    session: SessionDependency, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> RecommendationRecentResponse:
    return get_recent_recommendations(limit=limit, session=session)


@router.get("/feedback/overview", response_model=RecommendationFeedbackAnalyticsResponse)
def get_recommendation_feedback_overview(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> RecommendationFeedbackAnalyticsResponse:
    return get_recommendation_feedback_analytics(limit=limit, session=session)


@router.get("/{recommendation_id}", response_model=RecommendationDetailResponse)
def get_recommendation(
    recommendation_id: str, session: SessionDependency
) -> RecommendationDetailResponse:
    return get_recommendation_detail(recommendation_id, session)


@router.get("/{recommendation_id}/audit", response_model=RecommendationAuditResponse)
def get_recommendation_audit_view(
    recommendation_id: str, session: SessionDependency
) -> RecommendationAuditResponse:
    return get_recommendation_audit(recommendation_id, session)


@router.get(
    "/{recommendation_id}/evidence-export",
    response_model=RecommendationEvidenceExportResponse,
)
def get_recommendation_evidence_export_view(
    recommendation_id: str, session: SessionDependency
) -> RecommendationEvidenceExportResponse:
    return get_recommendation_evidence_export(recommendation_id, session)


@router.get("/{recommendation_id}/decisions", response_model=RecommendationDecisionListResponse)
def list_recommendation_decisions_view(
    recommendation_id: str, session: SessionDependency
) -> RecommendationDecisionListResponse:
    return list_recommendation_decision_log(recommendation_id, session)


@router.post("/{recommendation_id}/decisions", response_model=RecommendationDecisionResponse)
def create_recommendation_decision_view(
    recommendation_id: str,
    request: RecommendationDecisionRequest,
    session: SessionDependency,
) -> RecommendationDecisionResponse:
    return create_recommendation_decision(recommendation_id, request, session)


@router.post(
    "/decisions/{decision_id}/feedback",
    response_model=RecommendationDecisionFeedbackResponse,
)
def create_recommendation_decision_feedback_view(
    decision_id: str,
    request: RecommendationDecisionFeedbackRequest,
    session: SessionDependency,
) -> RecommendationDecisionFeedbackResponse:
    return create_recommendation_decision_feedback(decision_id, request, session)


@router.post("/{recommendation_id}/reviews", response_model=RecommendationReviewResponse)
def create_recommendation_review(
    recommendation_id: str,
    request: RecommendationReviewRequest,
    session: SessionDependency,
) -> RecommendationReviewResponse:
    return review_recommendation(recommendation_id, request, session)
