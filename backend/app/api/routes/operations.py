from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.schemas.operations import (
    OperationActionCenterResponse,
    OperationJobListResponse,
    OperationsOverviewResponse,
    OperationsReviewPackageResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
)
from backend.app.services.operations import (
    get_operation_action_center,
    get_operation_jobs,
    get_operations_overview,
    get_operations_review_package,
    get_workflow_run_by_id,
    get_workflow_runs,
    queue_operation_job,
)

router = APIRouter(prefix="/v1/operations", tags=["operations"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("/jobs", response_model=OperationJobListResponse)
def list_jobs() -> OperationJobListResponse:
    return get_operation_jobs()


@router.get("/overview", response_model=OperationsOverviewResponse)
def overview(session: SessionDependency) -> OperationsOverviewResponse:
    return get_operations_overview(session=session)


@router.get("/review-package", response_model=OperationsReviewPackageResponse)
def review_package(session: SessionDependency) -> OperationsReviewPackageResponse:
    return get_operations_review_package(session=session)


@router.get("/action-center", response_model=OperationActionCenterResponse)
def action_center(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OperationActionCenterResponse:
    return get_operation_action_center(session=session, limit=limit)


@router.get("/runs", response_model=WorkflowRunListResponse)
def list_runs(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> WorkflowRunListResponse:
    return get_workflow_runs(limit=limit, session=session)


@router.get("/runs/{workflow_run_id}", response_model=WorkflowRunResponse)
def get_run(workflow_run_id: str, session: SessionDependency) -> WorkflowRunResponse:
    return get_workflow_run_by_id(workflow_run_id, session=session)


@router.post("/jobs/{job_key}/run", response_model=WorkflowRunResponse)
def run_job(job_key: str, session: SessionDependency) -> WorkflowRunResponse:
    return queue_operation_job(job_key, session=session)
