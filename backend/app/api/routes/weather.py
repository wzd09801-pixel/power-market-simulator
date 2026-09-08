from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.adapters.open_meteo import OpenMeteoClient
from backend.app.db.session import get_db_session
from backend.app.schemas.weather import (
    OpenMeteoForecastIngestRequest,
    WeatherFeatureReviewPackageResponse,
    WeatherFeatureReviewRequest,
    WeatherFeatureReviewResponse,
    WeatherFeatureSnapshotResponse,
    WeatherIngestionResponse,
    WeatherQualityIssueListResponse,
    WeatherRecordListResponse,
)
from backend.app.services.weather import (
    get_latest_weather_features,
    get_open_meteo_client,
    get_weather_feature_review_package,
    get_weather_quality_issues,
    get_weather_records,
    ingest_open_meteo_forecast,
    review_weather_feature_snapshot,
)

router = APIRouter(prefix="/v1/weather", tags=["weather"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
OpenMeteoClientDependency = Annotated[OpenMeteoClient, Depends(get_open_meteo_client)]


@router.post("/open-meteo/forecast", response_model=WeatherIngestionResponse)
def ingest_forecast(
    request: OpenMeteoForecastIngestRequest,
    session: SessionDependency,
    client: OpenMeteoClientDependency,
) -> WeatherIngestionResponse:
    return ingest_open_meteo_forecast(request, session=session, client=client)


@router.get("/records", response_model=WeatherRecordListResponse)
def list_records(
    session: SessionDependency,
    location_id: Annotated[str, Query(min_length=1, max_length=80)],
    variable: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> WeatherRecordListResponse:
    return get_weather_records(
        location_id=location_id,
        variable=variable,
        limit=limit,
        session=session,
    )


@router.get("/features/latest", response_model=WeatherFeatureSnapshotResponse)
def get_latest_features(
    session: SessionDependency,
    location_id: Annotated[str, Query(min_length=1, max_length=80)],
) -> WeatherFeatureSnapshotResponse:
    return get_latest_weather_features(location_id=location_id, session=session)


@router.get(
    "/features/{feature_snapshot_id}/review-package",
    response_model=WeatherFeatureReviewPackageResponse,
)
def get_feature_review_package(
    feature_snapshot_id: str,
    session: SessionDependency,
) -> WeatherFeatureReviewPackageResponse:
    return get_weather_feature_review_package(feature_snapshot_id, session=session)


@router.get("/quality/issues", response_model=WeatherQualityIssueListResponse)
def list_quality_issues(
    session: SessionDependency,
    location_id: Annotated[str, Query(min_length=1, max_length=80)],
    issue_code: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> WeatherQualityIssueListResponse:
    return get_weather_quality_issues(
        location_id=location_id,
        issue_code=issue_code,
        limit=limit,
        session=session,
    )


@router.post(
    "/features/{feature_snapshot_id}/reviews",
    response_model=WeatherFeatureReviewResponse,
)
def create_feature_review(
    feature_snapshot_id: str,
    request: WeatherFeatureReviewRequest,
    session: SessionDependency,
) -> WeatherFeatureReviewResponse:
    return review_weather_feature_snapshot(feature_snapshot_id, request, session=session)
