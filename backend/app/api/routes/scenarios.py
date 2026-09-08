from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.schemas.scenario import (
    HydroOptimizationRunListResponse,
    HydroOptimizationRunRequest,
    HydroOptimizationRunResponse,
    HydroScenario,
)
from backend.app.services.scenarios import (
    create_demo_hydro_optimization_run,
    get_default_demo_hydro_scenario,
    get_demo_hydro_optimization_run,
    get_recent_demo_hydro_optimization_runs,
)

router = APIRouter(prefix="/v1/scenarios", tags=["scenarios"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("/demo_hydro/default", response_model=HydroScenario)
def get_demo_hydro_default() -> HydroScenario:
    return get_default_demo_hydro_scenario()


@router.post(
    "/demo_hydro/optimization-runs",
    response_model=HydroOptimizationRunResponse,
)
def create_demo_hydro_optimization(
    request: HydroOptimizationRunRequest,
    session: SessionDependency,
) -> HydroOptimizationRunResponse:
    return create_demo_hydro_optimization_run(request, session=session)


@router.get(
    "/demo_hydro/optimization-runs/recent",
    response_model=HydroOptimizationRunListResponse,
)
def recent_demo_hydro_optimization_runs(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> HydroOptimizationRunListResponse:
    return get_recent_demo_hydro_optimization_runs(limit=limit, session=session)


@router.get(
    "/demo_hydro/optimization-runs/{optimization_run_id}",
    response_model=HydroOptimizationRunResponse,
)
def get_demo_hydro_optimization(
    optimization_run_id: str,
    session: SessionDependency,
) -> HydroOptimizationRunResponse:
    return get_demo_hydro_optimization_run(optimization_run_id, session=session)
