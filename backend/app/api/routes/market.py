from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from backend.app.adapters.market_endpoint_health import MarketEndpointHealthClient
from backend.app.db.session import get_db_session
from backend.app.schemas.market import (
    ManualMarketArtifactRequest,
    ManualMarketArtifactResponse,
    MarketArtifactReviewPackageResponse,
    MarketArtifactReviewRequest,
    MarketArtifactReviewResponse,
    MarketDataSourceListResponse,
    MarketEndpointHealthCheckListResponse,
    MarketEndpointHealthCheckResponse,
    MarketIngestionRunListResponse,
    MarketObservationListResponse,
    MarketParsingRunListResponse,
    MarketParsingRunResponse,
    MarketQualityIssueListResponse,
    MarketRawArtifactListResponse,
    MarketSourceEndpointListResponse,
)
from backend.app.services.market import (
    get_market_artifact_review_package,
    get_market_artifacts,
    get_market_endpoints,
    get_market_ingestion_runs,
    get_market_quality_issues,
    get_market_sources,
    preserve_manual_market_artifact,
)
from backend.app.services.market_health import (
    get_market_endpoint_health_checks,
    get_market_endpoint_health_client,
    probe_market_endpoint,
)
from backend.app.services.market_reports import (
    get_market_observations,
    get_market_parsing_runs,
    parse_reviewed_reports_weekly_artifact,
    review_market_artifact,
)

router = APIRouter(prefix="/v1/market", tags=["market"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
MarketEndpointHealthClientDependency = Annotated[
    MarketEndpointHealthClient,
    Depends(get_market_endpoint_health_client),
]


@router.get("/sources", response_model=MarketDataSourceListResponse)
def list_sources(session: SessionDependency) -> MarketDataSourceListResponse:
    return get_market_sources(session=session)


@router.get("/endpoints", response_model=MarketSourceEndpointListResponse)
def list_endpoints(
    session: SessionDependency,
    source_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
) -> MarketSourceEndpointListResponse:
    return get_market_endpoints(source_id=source_id, session=session)


@router.post(
    "/endpoints/{endpoint_id}/health-checks",
    response_model=MarketEndpointHealthCheckResponse,
)
def create_endpoint_health_check(
    endpoint_id: str,
    session: SessionDependency,
    client: MarketEndpointHealthClientDependency,
    _empty_body: Annotated[None, Body()] = None,
) -> MarketEndpointHealthCheckResponse:
    return probe_market_endpoint(endpoint_id, session=session, client=client)


@router.get("/health/checks", response_model=MarketEndpointHealthCheckListResponse)
def list_endpoint_health_checks(
    session: SessionDependency,
    endpoint_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> MarketEndpointHealthCheckListResponse:
    return get_market_endpoint_health_checks(endpoint_id=endpoint_id, limit=limit, session=session)


@router.post("/artifacts/manual", response_model=ManualMarketArtifactResponse)
def create_manual_artifact(
    request: ManualMarketArtifactRequest,
    session: SessionDependency,
) -> ManualMarketArtifactResponse:
    return preserve_manual_market_artifact(request, session=session)


@router.get("/artifacts", response_model=MarketRawArtifactListResponse)
def list_artifacts(
    session: SessionDependency,
    source_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    endpoint_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> MarketRawArtifactListResponse:
    return get_market_artifacts(
        source_id=source_id,
        endpoint_id=endpoint_id,
        limit=limit,
        session=session,
    )


@router.get(
    "/artifacts/{artifact_id}/review-package",
    response_model=MarketArtifactReviewPackageResponse,
)
def get_artifact_review_package(
    artifact_id: str,
    session: SessionDependency,
) -> MarketArtifactReviewPackageResponse:
    return get_market_artifact_review_package(artifact_id, session=session)


@router.get("/ingestion/runs", response_model=MarketIngestionRunListResponse)
def list_ingestion_runs(
    session: SessionDependency,
    source_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    endpoint_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    status: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> MarketIngestionRunListResponse:
    return get_market_ingestion_runs(
        source_id=source_id,
        endpoint_id=endpoint_id,
        status=status,
        limit=limit,
        session=session,
    )


@router.get("/quality/issues", response_model=MarketQualityIssueListResponse)
def list_quality_issues(
    session: SessionDependency,
    source_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    endpoint_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    issue_code: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> MarketQualityIssueListResponse:
    return get_market_quality_issues(
        source_id=source_id,
        endpoint_id=endpoint_id,
        issue_code=issue_code,
        limit=limit,
        session=session,
    )


@router.post(
    "/artifacts/{artifact_id}/reviews",
    response_model=MarketArtifactReviewResponse,
)
def create_artifact_review(
    artifact_id: str,
    request: MarketArtifactReviewRequest,
    session: SessionDependency,
) -> MarketArtifactReviewResponse:
    return review_market_artifact(artifact_id, request, session=session)


@router.post(
    "/artifacts/{artifact_id}/parse/reports-weekly-report",
    response_model=MarketParsingRunResponse,
)
def parse_reports_weekly_report(
    artifact_id: str,
    session: SessionDependency,
) -> MarketParsingRunResponse:
    return parse_reviewed_reports_weekly_artifact(artifact_id, session=session)


@router.get("/parsing/runs", response_model=MarketParsingRunListResponse)
def list_parsing_runs(
    session: SessionDependency,
    artifact_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> MarketParsingRunListResponse:
    return get_market_parsing_runs(artifact_id=artifact_id, limit=limit, session=session)


@router.get("/observations", response_model=MarketObservationListResponse)
def list_observations(
    session: SessionDependency,
    artifact_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    area_code: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    market_stage: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    metric: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> MarketObservationListResponse:
    return get_market_observations(
        artifact_id=artifact_id,
        area_code=area_code,
        market_stage=market_stage,
        metric=metric,
        limit=limit,
        session=session,
    )
