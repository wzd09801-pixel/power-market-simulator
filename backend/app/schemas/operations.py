from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.system import SystemReadinessResponse

OperationsStatus = Literal["healthy", "warning", "critical"]
OperationTodoCategory = Literal[
    "workflow",
    "brief_review",
    "recommendation_review",
    "decision_feedback",
    "data_freshness",
    "weather_feature_review",
    "market_artifact_review",
    "policy_document_review",
]


class OperationJobResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_key: str
    description: str
    schedule: str
    timezone: str
    research_only: bool
    manual_trigger_enabled: bool


class OperationJobListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[OperationJobResponse]


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow_run_id: str
    workflow_key: str
    trigger_mode: str
    prefect_flow_run_id: str | None
    scheduled_for: datetime | None
    status: str
    started_at: datetime
    available_at: datetime
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    worker_id: str | None
    attempt_count: int
    completed_at: datetime | None
    summary: dict[str, object]
    error_code: str | None
    error_message: str | None


class WorkflowRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[WorkflowRunResponse]


class OperationsHealthItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    status: OperationsStatus
    message: str
    observed_at: datetime | None = None
    details: dict[str, object]


class OperationsFreshnessItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    status: OperationsStatus
    message: str
    latest_at: datetime | None = None
    age_hours: float | None = None
    data_mode: str | None = None
    research_only: bool = False
    details: dict[str, object]


class OperationsActionItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_key: str
    label: str
    description: str
    schedule: str
    timezone: str
    manual_trigger_enabled: bool
    research_only: bool
    recommended: bool
    reason: str


class OperationsOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    overall_status: OperationsStatus
    workflow_overview: dict[str, object]
    freshness: list[OperationsFreshnessItem]
    health: list[OperationsHealthItem]
    actions: list[OperationsActionItem]
    recent_runs: list[WorkflowRunResponse]
    recent_incidents: list[WorkflowRunResponse]
    no_auto_trading: bool


class OperationTodoItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    category: OperationTodoCategory
    severity: OperationsStatus
    title: str
    message: str
    target_type: str
    target_id: str
    navigation_target_type: str | None = None
    navigation_target_id: str | None = None
    created_at: datetime | None = None
    latest_at: datetime | None = None
    recommended_action: str
    job_key: str | None = None
    review_target_type: str | None = None
    allowed_review_statuses: list[str] = Field(default_factory=list)
    default_review_note: str | None = None


class OperationTodoCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    critical: int
    warning: int
    by_category: dict[str, int]


class OperationActionCenterResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    status: OperationsStatus
    counts: OperationTodoCounts
    items: list[OperationTodoItem]
    no_auto_trading: bool


class OperationsReviewPackageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_version: str
    generated_at: datetime
    overview: OperationsOverviewResponse
    action_center: OperationActionCenterResponse
    system_readiness: SystemReadinessResponse
    recent_runs: list[WorkflowRunResponse]
    fixed_job_keys: list[str]
    no_auto_trading: bool
    manual_job_keys_only: bool
    network_probe_performed: bool
    fetch_performed: bool
