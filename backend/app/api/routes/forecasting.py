from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.adapters.bench_dispatch import BenchDispatchClient
from backend.app.db.session import get_db_session
from backend.app.schemas.forecasting import (
    BenchDispatchBenchmarkImportRequest,
    ForecastResearchBacktestRequest,
    ForecastResearchDatasetImportRunListResponse,
    ForecastResearchDatasetListResponse,
    ForecastResearchModelRunListResponse,
    ForecastResearchModelRunResponse,
    ForecastResearchOverviewResponse,
    ForecastResearchPredictionListResponse,
    ForecastResearchPricePointListResponse,
    ForecastResearchQualityIssueListResponse,
    ForecastResearchReviewPackageResponse,
    ManualForecastResearchDatasetRequest,
    ManualForecastResearchDatasetResponse,
)
from backend.app.services.forecasting import (
    get_bench_dispatch_client,
    get_forecast_research_datasets,
    get_forecast_research_import_runs,
    get_forecast_research_model_runs,
    get_forecast_research_overview,
    get_forecast_research_predictions,
    get_forecast_research_price_points,
    get_forecast_research_quality_issues,
    get_forecast_research_review_package,
    import_bench_dispatch_benchmark,
    import_manual_forecast_research_dataset,
    run_forecast_research_backtest,
)

router = APIRouter(prefix="/v1/forecasting/research", tags=["forecasting-research"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
BenchDispatchClientDependency = Annotated[BenchDispatchClient, Depends(get_bench_dispatch_client)]


@router.get("/overview", response_model=ForecastResearchOverviewResponse)
def overview(session: SessionDependency) -> ForecastResearchOverviewResponse:
    return get_forecast_research_overview(session=session)


@router.post("/datasets/manual", response_model=ManualForecastResearchDatasetResponse)
def create_manual_dataset(
    request: ManualForecastResearchDatasetRequest,
    session: SessionDependency,
) -> ManualForecastResearchDatasetResponse:
    return import_manual_forecast_research_dataset(request, session=session)


@router.post(
    "/benchmarks/bench-dispatch/archive",
    response_model=ManualForecastResearchDatasetResponse,
)
def create_bench_dispatch_benchmark(
    request: BenchDispatchBenchmarkImportRequest,
    session: SessionDependency,
    client: BenchDispatchClientDependency,
) -> ManualForecastResearchDatasetResponse:
    return import_bench_dispatch_benchmark(request, session=session, client=client)


@router.get("/datasets", response_model=ForecastResearchDatasetListResponse)
def list_datasets(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ForecastResearchDatasetListResponse:
    return get_forecast_research_datasets(limit=limit, session=session)


@router.get("/import-runs", response_model=ForecastResearchDatasetImportRunListResponse)
def list_import_runs(
    session: SessionDependency,
    dataset_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ForecastResearchDatasetImportRunListResponse:
    return get_forecast_research_import_runs(dataset_id=dataset_id, limit=limit, session=session)


@router.get(
    "/datasets/{dataset_id}/points",
    response_model=ForecastResearchPricePointListResponse,
)
def list_price_points(
    dataset_id: str,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
) -> ForecastResearchPricePointListResponse:
    return get_forecast_research_price_points(dataset_id, limit=limit, session=session)


@router.get("/quality/issues", response_model=ForecastResearchQualityIssueListResponse)
def list_quality_issues(
    session: SessionDependency,
    dataset_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    issue_code: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ForecastResearchQualityIssueListResponse:
    return get_forecast_research_quality_issues(
        dataset_id=dataset_id,
        issue_code=issue_code,
        limit=limit,
        session=session,
    )


@router.get(
    "/datasets/{dataset_id}/review-package",
    response_model=ForecastResearchReviewPackageResponse,
)
def review_package(
    dataset_id: str,
    session: SessionDependency,
) -> ForecastResearchReviewPackageResponse:
    return get_forecast_research_review_package(dataset_id, session=session)


@router.post(
    "/datasets/{dataset_id}/backtests",
    response_model=ForecastResearchModelRunResponse,
)
def create_backtest(
    dataset_id: str,
    request: ForecastResearchBacktestRequest,
    session: SessionDependency,
) -> ForecastResearchModelRunResponse:
    return run_forecast_research_backtest(dataset_id, request, session=session)


@router.get("/model-runs", response_model=ForecastResearchModelRunListResponse)
def list_model_runs(
    session: SessionDependency,
    dataset_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ForecastResearchModelRunListResponse:
    return get_forecast_research_model_runs(dataset_id=dataset_id, limit=limit, session=session)


@router.get(
    "/model-runs/{model_run_id}/predictions",
    response_model=ForecastResearchPredictionListResponse,
)
def list_predictions(
    model_run_id: str,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
) -> ForecastResearchPredictionListResponse:
    return get_forecast_research_predictions(model_run_id, limit=limit, session=session)
