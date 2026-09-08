from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.errors import (
    OperationJobManualTriggerDisabledError,
    OperationJobNotFoundError,
    WorkflowRunNotFoundError,
)
from backend.app.models.forecasting import ForecastResearchDataset
from backend.app.models.intelligence import IntelligenceBrief
from backend.app.models.knowledge import KnowledgeDocument
from backend.app.models.market import (
    MarketDataSource,
    MarketEndpointHealthCheck,
    MarketRawArtifact,
    MarketSourceEndpoint,
)
from backend.app.models.operations import RawObject, WorkflowRun
from backend.app.models.recommendation import (
    RecommendationDecision,
    RecommendationDecisionFeedback,
    RecommendationRun,
)
from backend.app.models.weather import WeatherFeatureSnapshot
from backend.app.repositories.operations import (
    add_raw_object,
    add_workflow_run,
    claim_next_workflow_run,
    fail_exhausted_workflow_leases,
    get_raw_object_by_hash,
    get_workday_override,
    get_workflow_run,
    get_workflow_run_by_schedule_identity,
    list_workflow_runs,
)
from backend.app.schemas.operations import (
    OperationActionCenterResponse,
    OperationJobListResponse,
    OperationJobResponse,
    OperationsActionItem,
    OperationsFreshnessItem,
    OperationsHealthItem,
    OperationsOverviewResponse,
    OperationsReviewPackageResponse,
    OperationsStatus,
    OperationTodoCounts,
    OperationTodoItem,
    WorkflowRunListResponse,
    WorkflowRunResponse,
)
from backend.app.storage.blob_store import BlobStore

OFFICIAL_2026_CALENDAR_URL = (
    "https://calendar.example.invalid/zhengce/content/202511/content_7047098.htm"
)
DEFAULT_WORKFLOW_LEASE_SECONDS = 300
DEFAULT_WORKFLOW_RETRY_DELAY_SECONDS = 60
MAX_WORKFLOW_ATTEMPTS = 2
TIMEZONE = ZoneInfo("Asia/Shanghai")
BENCH_RESEARCH_REGION_CODES = (
    "BENCH_NEM_NSW1",
    "BENCH_NEM_QLD1",
    "BENCH_NEM_SA1",
    "BENCH_NEM_TAS1",
    "BENCH_NEM_VIC1",
)
POLICY_RESEARCH_ENDPOINT_IDS = (
    "southern_regulator_downloads",
    "council_home",
    "association_home",
    "institute_home",
)
TERMINAL_WORKFLOW_STATUSES = ("succeeded", "skipped", "failed")
FRESHNESS_JOB_KEYS = {
    "weather_features": "weather_refresh",
    "daily_brief": "daily_intelligence_brief",
    "bench_dispatch_research": "bench_dispatch_research",
    "policy_documents": "policy_research_refresh",
}
REVIEW_TODO_STATUSES = ("pending_review", "needs_revision")
ACTION_CENTER_REVIEW_STATUSES = ("approved", "needs_revision", "rejected")
ACTION_CENTER_DEFAULT_REVIEW_NOTE = "Reviewed from Action Center quick action."
OPERATIONS_REVIEW_PACKAGE_VERSION = "operations_review_package_v1"


@dataclass(frozen=True)
class OperationJob:
    job_key: str
    description: str
    schedule: str
    timezone: str = "Asia/Shanghai"
    research_only: bool = False
    manual_trigger_enabled: bool = True


@dataclass(frozen=True)
class ClaimedWorkflowRun:
    run: WorkflowRunResponse
    lease_token: str


class WorkflowLeaseLostError(RuntimeError):
    pass


OPERATION_JOBS = (
    OperationJob(
        "weather_refresh",
        "Refresh approved public weather reference points.",
        "0 7,16 * * *",
    ),
    OperationJob(
        "policy_research_refresh",
        "Refresh enabled allowlisted policy sources.",
        "0 1,7,13,19 * * *",
    ),
    OperationJob(
        "bench_dispatch_research",
        "Archive the fixed official BENCH Dispatch benchmark.",
        "30 9 * * *",
        research_only=True,
    ),
    OperationJob(
        "daily_intelligence_brief",
        "Generate the human-reviewed daily intelligence brief.",
        "30 8 * * 1-5",
    ),
    OperationJob(
        "demo_research_workspace_seed",
        "Seed local deterministic demo data for the v0.1 RC checklist.",
        "manual",
    ),
)


def _now() -> datetime:
    return datetime.now(tz=TIMEZONE)


def _as_local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=TIMEZONE)
    return value.astimezone(TIMEZONE)


def _age_hours(now: datetime, value: datetime | None) -> float | None:
    local_value = _as_local_datetime(value)
    if local_value is None:
        return None
    return max((now - local_value).total_seconds() / 3600, 0.0)


def _datetime_isoformat(value: datetime | None) -> str | None:
    local_value = _as_local_datetime(value)
    return local_value.isoformat() if local_value is not None else None


def _status_from_age(
    age_hours: float | None,
    *,
    warning_hours: float,
    critical_hours: float | None = None,
) -> OperationsStatus:
    if age_hours is None:
        return "warning"
    if critical_hours is not None and age_hours > critical_hours:
        return "critical"
    if age_hours > warning_hours:
        return "warning"
    return "healthy"


def _worst_status(items: list[OperationsStatus]) -> OperationsStatus:
    if "critical" in items:
        return "critical"
    if "warning" in items:
        return "warning"
    return "healthy"


def preserve_raw_object(
    *,
    content: bytes,
    media_type: str,
    data_mode: str,
    source_url: str | None,
    metadata: dict[str, object],
    store: BlobStore,
    session: Session,
    captured_at: datetime | None = None,
    merge_metadata_on_duplicate: bool = False,
) -> tuple[RawObject, bool]:
    digest = sha256(content).hexdigest()
    with session.begin():
        existing = get_raw_object_by_hash(session, digest)
        if existing is not None:
            if merge_metadata_on_duplicate:
                _merge_duplicate_raw_object_metadata(existing, metadata)
            return existing, True
        object_key = f"raw/{digest[:2]}/{digest}"
        store.put(object_key=object_key, content=content, media_type=media_type)
        raw_object = RawObject(
            raw_object_id=f"raw_{uuid4().hex}",
            content_sha256=digest,
            storage_backend="minio",
            bucket_name=store.bucket_name,
            object_key=object_key,
            media_type=media_type,
            byte_length=len(content),
            source_url=source_url,
            captured_at=captured_at or _now(),
            metadata_json=metadata,
            data_mode=data_mode,
        )
        try:
            with session.begin_nested():
                add_raw_object(session, raw_object)
                session.flush()
        except IntegrityError:
            existing = get_raw_object_by_hash(session, digest)
            if existing is None:
                raise
            if merge_metadata_on_duplicate:
                _merge_duplicate_raw_object_metadata(existing, metadata)
            return existing, True
    return raw_object, False


def _merge_duplicate_raw_object_metadata(
    raw_object: RawObject, incoming_metadata: dict[str, object]
) -> None:
    import_entry = _market_artifact_import_entry(incoming_metadata)
    if import_entry is None:
        return
    merged_metadata = dict(raw_object.metadata_json or {})
    existing_imports = merged_metadata.get("market_artifact_imports")
    imports = list(existing_imports) if isinstance(existing_imports, list) else []
    artifact_id = import_entry.get("artifact_id")
    if any(isinstance(item, dict) and item.get("artifact_id") == artifact_id for item in imports):
        return
    imports.append(import_entry)
    merged_metadata["market_artifact_imports"] = imports
    raw_object.metadata_json = merged_metadata


def _market_artifact_import_entry(metadata: dict[str, object]) -> dict[str, object] | None:
    artifact_id = metadata.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        return None
    return {
        key: value
        for key, value in metadata.items()
        if key
        in {
            "artifact_id",
            "artifact_content_sha256",
            "artifact_captured_at",
            "source_id",
            "source_name",
            "source_trust_tier",
            "source_market_scope",
            "endpoint_id",
            "endpoint_name",
            "endpoint_kind",
            "endpoint_data_granularity",
            "source_url",
        }
    }


def is_mainland_workday(calendar_date: date, *, session: Session) -> bool:
    override = get_workday_override(session, calendar_date)
    return override.is_workday if override is not None else calendar_date.weekday() < 5


def get_operation_jobs() -> OperationJobListResponse:
    return OperationJobListResponse(
        items=[OperationJobResponse.model_validate(job.__dict__) for job in OPERATION_JOBS]
    )


def get_workflow_runs(*, limit: int, session: Session) -> WorkflowRunListResponse:
    return WorkflowRunListResponse(
        items=[_to_workflow_run_response(run) for run in list_workflow_runs(session, limit=limit)]
    )


def get_operations_overview(
    *,
    session: Session,
    now: datetime | None = None,
) -> OperationsOverviewResponse:
    generated_at = _as_local_datetime(now or _now())
    if generated_at is None:
        generated_at = _now()
    workflow_count_rows = session.execute(
        select(WorkflowRun.status, func.count(WorkflowRun.workflow_run_id)).group_by(
            WorkflowRun.status
        )
    ).all()
    workflow_counts = {str(status): int(count or 0) for status, count in workflow_count_rows}
    for status in ("queued", "running", "retry_wait", *TERMINAL_WORKFLOW_STATUSES):
        workflow_counts.setdefault(status, 0)
    stale_lease_count = int(
        session.scalar(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.status == "running",
                WorkflowRun.lease_expires_at.is_not(None),
                WorkflowRun.lease_expires_at <= generated_at,
            )
        )
        or 0
    )
    failed_last_24h = int(
        session.scalar(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.status == "failed",
                WorkflowRun.completed_at.is_not(None),
                WorkflowRun.completed_at >= generated_at - timedelta(hours=24),
            )
        )
        or 0
    )
    recent_run_models = list_workflow_runs(session, limit=8)
    recent_incident_models = list(
        session.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.status.in_(("failed", "retry_wait")))
            .order_by(WorkflowRun.available_at.desc(), WorkflowRun.started_at.desc())
            .limit(8)
        )
    )
    workflow_status: OperationsStatus = "healthy"
    if stale_lease_count > 0 or workflow_counts["failed"] > 0:
        workflow_status = "critical"
    elif workflow_counts["retry_wait"] > 0:
        workflow_status = "warning"

    freshness = [
        _weather_freshness(session, generated_at),
        _daily_brief_freshness(session, generated_at),
        _bench_dispatch_freshness(session, generated_at),
        _policy_document_freshness(session),
    ]
    health = [
        _source_registry_health(session),
        _endpoint_health_summary(session),
    ]
    actions = _operation_action_items(
        freshness,
        recent_incident_models,
    )
    overall_status = _worst_status(
        [workflow_status, *[item.status for item in freshness], *[item.status for item in health]]
    )
    return OperationsOverviewResponse(
        generated_at=generated_at,
        overall_status=overall_status,
        workflow_overview={
            "counts": workflow_counts,
            "queued": workflow_counts["queued"],
            "running": workflow_counts["running"],
            "retry_wait": workflow_counts["retry_wait"],
            "failed": workflow_counts["failed"],
            "stale_lease_count": stale_lease_count,
            "failed_last_24h": failed_last_24h,
            "status": workflow_status,
        },
        freshness=freshness,
        health=health,
        actions=actions,
        recent_runs=[_to_workflow_run_response(run) for run in recent_run_models],
        recent_incidents=[_to_workflow_run_response(run) for run in recent_incident_models],
        no_auto_trading=True,
    )


def get_operation_action_center(
    *,
    session: Session,
    now: datetime | None = None,
    limit: int = 20,
) -> OperationActionCenterResponse:
    generated_at = _as_local_datetime(now or _now()) or _now()
    overview = get_operations_overview(session=session, now=generated_at)
    items: list[OperationTodoItem] = []
    items.extend(_workflow_todo_items(session, overview, generated_at))
    items.extend(_freshness_todo_items(overview.freshness))
    items.extend(_brief_review_todo_items(session, generated_at))
    items.extend(_recommendation_review_todo_items(session))
    items.extend(_decision_feedback_todo_items(session))
    items.extend(_weather_feature_review_todo_items(session))
    items.extend(_market_artifact_review_todo_items(session))
    items.extend(_policy_document_review_todo_items(session))
    severity_counts = Counter(item.severity for item in items)
    category_counts = Counter(item.category for item in items)
    status = _worst_status([item.severity for item in items]) if items else "healthy"
    visible_items = sorted(items, key=_todo_sort_key)[:limit]
    return OperationActionCenterResponse(
        generated_at=generated_at,
        status=status,
        counts=OperationTodoCounts(
            total=len(items),
            critical=severity_counts["critical"],
            warning=severity_counts["warning"],
            by_category={str(category): count for category, count in category_counts.items()},
        ),
        items=visible_items,
        no_auto_trading=True,
    )


def get_operations_review_package(
    *,
    session: Session,
    now: datetime | None = None,
    action_limit: int = 20,
    run_limit: int = 8,
) -> OperationsReviewPackageResponse:
    from backend.app.services.system import get_system_readiness

    generated_at = _as_local_datetime(now or _now()) or _now()
    overview = get_operations_overview(session=session, now=generated_at)
    action_center = get_operation_action_center(
        session=session,
        now=generated_at,
        limit=action_limit,
    )
    recent_runs = get_workflow_runs(limit=run_limit, session=session).items
    readiness = get_system_readiness(session=session)
    return OperationsReviewPackageResponse(
        package_version=OPERATIONS_REVIEW_PACKAGE_VERSION,
        generated_at=generated_at,
        overview=overview,
        action_center=action_center,
        system_readiness=readiness,
        recent_runs=recent_runs,
        fixed_job_keys=[job.job_key for job in OPERATION_JOBS],
        no_auto_trading=True,
        manual_job_keys_only=True,
        network_probe_performed=False,
        fetch_performed=False,
    )


def _workflow_todo_items(
    session: Session,
    overview: OperationsOverviewResponse,
    generated_at: datetime,
) -> list[OperationTodoItem]:
    items: list[OperationTodoItem] = []
    incident_ids: set[str] = set()
    for run in overview.recent_incidents:
        incident_ids.add(run.workflow_run_id)
        severity: OperationsStatus = "critical" if run.status == "failed" else "warning"
        items.append(
            OperationTodoItem(
                item_id=f"workflow:{run.workflow_run_id}",
                category="workflow",
                severity=severity,
                title=f"Workflow {run.status}: {run.workflow_key}",
                message=run.error_message or run.error_code or "Workflow requires operator review.",
                target_type="workflow_run",
                target_id=run.workflow_run_id,
                created_at=run.started_at,
                latest_at=run.completed_at or run.available_at,
                recommended_action=(
                    "Review the run error, then rerun the fixed registered job if appropriate."
                ),
                job_key=_registered_manual_job_key(run.workflow_key),
            )
        )
    stale_runs = list(
        session.scalars(
            select(WorkflowRun)
            .where(
                WorkflowRun.status == "running",
                WorkflowRun.lease_expires_at.is_not(None),
                WorkflowRun.lease_expires_at <= generated_at,
            )
            .order_by(WorkflowRun.lease_expires_at.asc())
            .limit(8)
        )
    )
    for stale_run in stale_runs:
        if stale_run.workflow_run_id in incident_ids:
            continue
        items.append(
            OperationTodoItem(
                item_id=f"workflow:{stale_run.workflow_run_id}",
                category="workflow",
                severity="critical",
                title=f"Stale workflow lease: {stale_run.workflow_key}",
                message="A running workflow lease has expired and may need worker recovery.",
                target_type="workflow_run",
                target_id=stale_run.workflow_run_id,
                created_at=stale_run.started_at,
                latest_at=stale_run.lease_expires_at,
                recommended_action=(
                    "Check the operation worker and allow the fixed queue consumer to "
                    "recover the lease."
                ),
                job_key=_registered_manual_job_key(stale_run.workflow_key),
            )
        )
    return items


def _freshness_todo_items(
    freshness_items: list[OperationsFreshnessItem],
) -> list[OperationTodoItem]:
    items: list[OperationTodoItem] = []
    for item in freshness_items:
        if item.status == "healthy":
            continue
        job_key = FRESHNESS_JOB_KEYS.get(item.key)
        items.append(
            OperationTodoItem(
                item_id=f"freshness:{item.key}",
                category="data_freshness",
                severity=item.status,
                title=f"{item.label} freshness is {item.status}",
                message=item.message,
                target_type="freshness",
                target_id=item.key,
                created_at=None,
                latest_at=item.latest_at,
                recommended_action=_freshness_recommended_action(item.key),
                job_key=_registered_manual_job_key(job_key) if job_key is not None else None,
            )
        )
    return items


def _brief_review_todo_items(
    session: Session,
    generated_at: datetime,
) -> list[OperationTodoItem]:
    target_date = generated_at.date()
    brief = session.scalar(
        select(IntelligenceBrief)
        .where(IntelligenceBrief.target_date == target_date)
        .order_by(IntelligenceBrief.generated_at.desc())
        .limit(1)
    )
    if brief is None:
        brief = session.scalar(
            select(IntelligenceBrief).order_by(IntelligenceBrief.generated_at.desc()).limit(1)
        )
    if brief is None or brief.human_review_status not in {"pending_review", "needs_revision"}:
        return []
    return [
        OperationTodoItem(
            item_id=f"brief:{brief.brief_id}",
            category="brief_review",
            severity="warning",
            title=f"Brief review: {brief.human_review_status}",
            message=(
                f"Brief {brief.brief_id} for {brief.target_date.isoformat()} needs operator review."
            ),
            target_type="intelligence_brief",
            target_id=brief.brief_id,
            navigation_target_type="intelligence_brief",
            navigation_target_id=brief.brief_id,
            created_at=brief.generated_at,
            latest_at=brief.generated_at,
            recommended_action=(
                "Open the daily brief, review policy watch and missing information, then "
                "approve or request revision."
            ),
            job_key=None,
        )
    ]


def _recommendation_review_todo_items(session: Session) -> list[OperationTodoItem]:
    runs = list(
        session.scalars(
            select(RecommendationRun)
            .where(RecommendationRun.review_status.in_(("pending_review", "needs_revision")))
            .order_by(RecommendationRun.created_at.desc())
            .limit(8)
        )
    )
    return [
        OperationTodoItem(
            item_id=f"recommendation:{run.rec_id}",
            category="recommendation_review",
            severity="warning",
            title=f"Recommendation review: {run.review_status}",
            message=(
                f"Recommendation {run.rec_id} for {run.trade_date.isoformat()} "
                "needs human review before use as decision support."
            ),
            target_type="recommendation",
            target_id=run.rec_id,
            navigation_target_type="recommendation",
            navigation_target_id=run.rec_id,
            created_at=run.created_at,
            latest_at=run.created_at,
            recommended_action=(
                "Open the recommendation, inspect evidence audit, and record human review."
            ),
            job_key=None,
        )
        for run in runs
    ]


def _decision_feedback_todo_items(session: Session) -> list[OperationTodoItem]:
    decisions = list(
        session.scalars(
            select(RecommendationDecision)
            .order_by(RecommendationDecision.created_at.desc())
            .limit(50)
        )
    )
    if not decisions:
        return []
    decision_ids = [decision.decision_id for decision in decisions]
    feedback_items = list(
        session.scalars(
            select(RecommendationDecisionFeedback)
            .where(RecommendationDecisionFeedback.decision_id.in_(decision_ids))
            .order_by(RecommendationDecisionFeedback.created_at.desc())
        )
    )
    latest_feedback_by_decision: dict[str, RecommendationDecisionFeedback] = {}
    for feedback in feedback_items:
        latest_feedback_by_decision.setdefault(feedback.decision_id, feedback)
    items: list[OperationTodoItem] = []
    for decision in decisions:
        latest_feedback = latest_feedback_by_decision.get(decision.decision_id)
        if latest_feedback is not None and latest_feedback.outcome_status != "pending_observation":
            continue
        latest_at = (
            latest_feedback.created_at if latest_feedback is not None else decision.created_at
        )
        if latest_feedback is None:
            message = "Decision has no follow-up feedback yet."
        else:
            message = "Latest decision feedback is still pending observation."
        items.append(
            OperationTodoItem(
                item_id=f"decision:{decision.decision_id}",
                category="decision_feedback",
                severity="warning",
                title="Decision feedback pending",
                message=f"{message} recommendation_id={decision.recommendation_id}",
                target_type="recommendation_decision",
                target_id=decision.decision_id,
                navigation_target_type="recommendation",
                navigation_target_id=decision.recommendation_id,
                created_at=decision.created_at,
                latest_at=latest_at,
                recommended_action=(
                    "Add subjective follow-up feedback when observation is available."
                ),
                job_key=None,
            )
        )
    return items[:8]


def _weather_feature_review_todo_items(session: Session) -> list[OperationTodoItem]:
    snapshots = list(
        session.scalars(
            select(WeatherFeatureSnapshot)
            .where(WeatherFeatureSnapshot.human_review_status.in_(REVIEW_TODO_STATUSES))
            .order_by(WeatherFeatureSnapshot.generated_at.desc())
            .limit(8)
        )
    )
    return [
        OperationTodoItem(
            item_id=f"weather_feature:{snapshot.feature_snapshot_id}",
            category="weather_feature_review",
            severity="warning",
            title=f"Weather feature review: {snapshot.human_review_status}",
            message=(
                f"Weather feature snapshot {snapshot.feature_snapshot_id} for "
                f"{snapshot.location_id} needs operator review."
            ),
            target_type="weather_feature_snapshot",
            target_id=snapshot.feature_snapshot_id,
            created_at=snapshot.generated_at,
            latest_at=snapshot.generated_at,
            recommended_action=(
                "Review public-derived weather quality and approve or request revision."
            ),
            review_target_type="weather_feature",
            allowed_review_statuses=list(ACTION_CENTER_REVIEW_STATUSES),
            default_review_note=ACTION_CENTER_DEFAULT_REVIEW_NOTE,
        )
        for snapshot in snapshots
    ]


def _market_artifact_review_todo_items(session: Session) -> list[OperationTodoItem]:
    artifacts = list(
        session.scalars(
            select(MarketRawArtifact)
            .where(MarketRawArtifact.human_review_status.in_(REVIEW_TODO_STATUSES))
            .order_by(MarketRawArtifact.captured_at.desc())
            .limit(8)
        )
    )
    return [
        OperationTodoItem(
            item_id=f"market_artifact:{artifact.artifact_id}",
            category="market_artifact_review",
            severity="warning",
            title=f"Market artifact review: {artifact.human_review_status}",
            message=(
                f"Preserved artifact {artifact.artifact_id} from {artifact.endpoint_id} "
                "needs local review."
            ),
            target_type="market_raw_artifact",
            target_id=artifact.artifact_id,
            created_at=artifact.captured_at,
            latest_at=artifact.captured_at,
            recommended_action=(
                "Review the preserved source metadata and approve, reject, or request revision."
            ),
            review_target_type="market_artifact",
            allowed_review_statuses=list(ACTION_CENTER_REVIEW_STATUSES),
            default_review_note=ACTION_CENTER_DEFAULT_REVIEW_NOTE,
        )
        for artifact in artifacts
    ]


def _policy_document_review_todo_items(session: Session) -> list[OperationTodoItem]:
    documents = list(
        session.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.human_review_status.in_(REVIEW_TODO_STATUSES))
            .order_by(KnowledgeDocument.captured_at.desc())
            .limit(8)
        )
    )
    return [
        OperationTodoItem(
            item_id=f"policy_document:{document.document_id}",
            category="policy_document_review",
            severity="warning",
            title=f"Policy document review: {document.human_review_status}",
            message=(
                f"Knowledge document {document.document_id} from {document.source_name} "
                "needs operator review."
            ),
            target_type="knowledge_document",
            target_id=document.document_id,
            created_at=document.captured_at,
            latest_at=document.captured_at,
            recommended_action=(
                "Review document provenance and local chunks before updating review status."
            ),
            review_target_type="policy_document",
            allowed_review_statuses=list(ACTION_CENTER_REVIEW_STATUSES),
            default_review_note=ACTION_CENTER_DEFAULT_REVIEW_NOTE,
        )
        for document in documents
    ]


def _freshness_recommended_action(key: str) -> str:
    actions = {
        "weather_features": "Run the fixed weather_refresh job or review weather quality inputs.",
        "daily_brief": "Run the fixed daily_intelligence_brief job or generate a brief manually.",
        "bench_dispatch_research": (
            "Run the fixed BENCH research benchmark job; keep it research_only."
        ),
        "policy_documents": (
            "Review local policy library imports; automatic Chinese policy collection "
            "remains disabled unless verified."
        ),
    }
    return actions.get(key, "Review the freshness warning before relying on this data.")


def _registered_manual_job_key(job_key: str | None) -> str | None:
    if job_key is None:
        return None
    for job in OPERATION_JOBS:
        if job.job_key == job_key and job.manual_trigger_enabled:
            return job.job_key
    return None


def _todo_sort_key(item: OperationTodoItem) -> tuple[int, float]:
    severity_weight = {"critical": 0, "warning": 1, "healthy": 2}[item.severity]
    timestamp = item.latest_at or item.created_at or datetime.min.replace(tzinfo=TIMEZONE)
    local_timestamp = _as_local_datetime(timestamp) or datetime.min.replace(tzinfo=TIMEZONE)
    sort_timestamp = local_timestamp.timestamp() if local_timestamp.year >= 1970 else 0.0
    return (severity_weight, -sort_timestamp)


def get_workflow_run_by_id(workflow_run_id: str, *, session: Session) -> WorkflowRunResponse:
    run = get_workflow_run(session, workflow_run_id)
    if run is None:
        raise WorkflowRunNotFoundError(workflow_run_id)
    return _to_workflow_run_response(run)


def _weather_freshness(session: Session, now: datetime) -> OperationsFreshnessItem:
    snapshot = session.scalar(
        select(WeatherFeatureSnapshot).order_by(WeatherFeatureSnapshot.generated_at.desc()).limit(1)
    )
    latest_at = _as_local_datetime(snapshot.generated_at) if snapshot is not None else None
    age = _age_hours(now, latest_at)
    status = _status_from_age(age, warning_hours=18, critical_hours=36)
    if snapshot is None:
        message = "No weather feature snapshot has been generated."
    elif status == "critical":
        message = "Weather feature snapshot is older than 36 hours."
    elif status == "warning":
        message = "Weather feature snapshot is older than 18 hours."
    else:
        message = "Weather feature snapshot is current."
    return OperationsFreshnessItem(
        key="weather_features",
        label="Weather Features",
        status=status,
        message=message,
        latest_at=latest_at,
        age_hours=round(age, 2) if age is not None else None,
        data_mode=snapshot.data_mode if snapshot is not None else None,
        research_only=False,
        details={
            "location_id": snapshot.location_id if snapshot is not None else None,
            "provider": snapshot.provider if snapshot is not None else None,
            "quality_status": snapshot.quality_status if snapshot is not None else None,
            "human_review_status": (snapshot.human_review_status if snapshot is not None else None),
        },
    )


def _daily_brief_freshness(session: Session, now: datetime) -> OperationsFreshnessItem:
    target_date = now.date()
    brief_today = session.scalar(
        select(IntelligenceBrief)
        .where(IntelligenceBrief.target_date == target_date)
        .order_by(IntelligenceBrief.generated_at.desc())
        .limit(1)
    )
    latest_brief = session.scalar(
        select(IntelligenceBrief).order_by(IntelligenceBrief.generated_at.desc()).limit(1)
    )
    is_workday = is_mainland_workday(target_date, session=session)
    selected_brief = brief_today or latest_brief
    latest_at = (
        _as_local_datetime(selected_brief.generated_at) if selected_brief is not None else None
    )
    age = _age_hours(now, latest_at)
    if not is_workday:
        status: OperationsStatus = "healthy"
        message = "Daily brief is not required on a mainland non-workday."
    elif brief_today is None:
        status = "warning"
        message = "No daily intelligence brief has been generated for today's workday."
    else:
        status = "healthy"
        message = "Daily intelligence brief exists for today's workday."
    return OperationsFreshnessItem(
        key="daily_brief",
        label="Daily Intelligence Brief",
        status=status,
        message=message,
        latest_at=latest_at,
        age_hours=round(age, 2) if age is not None else None,
        data_mode=None,
        research_only=False,
        details={
            "target_date": target_date.isoformat(),
            "is_mainland_workday": is_workday,
            "brief_id": selected_brief.brief_id if selected_brief is not None else None,
            "today_brief_id": brief_today.brief_id if brief_today is not None else None,
            "human_review_status": (
                selected_brief.human_review_status if selected_brief is not None else None
            ),
            "no_auto_trading": (
                selected_brief.no_auto_trading if selected_brief is not None else True
            ),
        },
    )


def _bench_dispatch_freshness(session: Session, now: datetime) -> OperationsFreshnessItem:
    datasets = list(
        session.scalars(
            select(ForecastResearchDataset)
            .where(
                ForecastResearchDataset.market_scope == "bench_nem_dispatch_benchmark",
                ForecastResearchDataset.usage_scope == "research_only",
            )
            .order_by(ForecastResearchDataset.imported_at.desc())
        )
    )
    latest_by_region: dict[str, ForecastResearchDataset] = {}
    for dataset in datasets:
        if dataset.region_code not in BENCH_RESEARCH_REGION_CODES:
            continue
        current = latest_by_region.get(dataset.region_code)
        if current is None or dataset.imported_at > current.imported_at:
            latest_by_region[dataset.region_code] = dataset
    missing_regions = [
        region_code
        for region_code in BENCH_RESEARCH_REGION_CODES
        if region_code not in latest_by_region
    ]
    latest_times: list[datetime] = []
    for dataset in latest_by_region.values():
        local_imported_at = _as_local_datetime(dataset.imported_at)
        if local_imported_at is not None:
            latest_times.append(local_imported_at)
    complete = len(missing_regions) == 0
    freshness_anchor = (
        min(latest_times) if complete and latest_times else max(latest_times, default=None)
    )
    age = _age_hours(now, freshness_anchor)
    if not complete:
        status: OperationsStatus = "warning"
        message = "BENCH research benchmark is missing one or more regions."
    elif age is not None and age > 48:
        status = "warning"
        message = "BENCH research benchmark is older than 48 hours."
    else:
        status = "healthy"
        message = "BENCH research benchmark has all five regions within 48 hours."
    data_modes = sorted({dataset.data_mode for dataset in latest_by_region.values()})
    return OperationsFreshnessItem(
        key="bench_dispatch_research",
        label="BENCH Dispatch Research Benchmark",
        status=status,
        message=message,
        latest_at=freshness_anchor,
        age_hours=round(age, 2) if age is not None else None,
        data_mode=data_modes[0] if len(data_modes) == 1 else None,
        research_only=True,
        details={
            "usage_scope": "research_only",
            "expected_regions": [
                _short_bench_region(region) for region in BENCH_RESEARCH_REGION_CODES
            ],
            "available_regions": [
                _short_bench_region(region) for region in sorted(latest_by_region)
            ],
            "missing_regions": [_short_bench_region(region) for region in missing_regions],
            "dataset_ids": {
                _short_bench_region(region): dataset.dataset_id
                for region, dataset in sorted(latest_by_region.items())
            },
            "recommendation_chain_isolated": True,
        },
    )


def _policy_document_freshness(session: Session) -> OperationsFreshnessItem:
    document_count = int(session.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0)
    latest_document = session.scalar(
        select(KnowledgeDocument).order_by(KnowledgeDocument.captured_at.desc()).limit(1)
    )
    latest_at = (
        _as_local_datetime(latest_document.captured_at) if latest_document is not None else None
    )
    message = (
        "Policy library is local/manual-only; disabled automatic collection is not a failure."
        if document_count == 0
        else "Policy library has local preserved documents."
    )
    return OperationsFreshnessItem(
        key="policy_documents",
        label="Policy Knowledge Library",
        status="healthy",
        message=message,
        latest_at=latest_at,
        age_hours=None,
        data_mode=latest_document.data_mode if latest_document is not None else None,
        research_only=False,
        details={
            "document_count": document_count,
            "manual_only": True,
            "automatic_collection_failure": False,
        },
    )


def _source_registry_health(session: Session) -> OperationsHealthItem:
    source_count = int(session.scalar(select(func.count()).select_from(MarketDataSource)) or 0)
    endpoint_count = int(
        session.scalar(select(func.count()).select_from(MarketSourceEndpoint)) or 0
    )
    disabled_count = int(
        session.scalar(
            select(func.count())
            .select_from(MarketSourceEndpoint)
            .where(MarketSourceEndpoint.collection_enabled.is_(False))
        )
        or 0
    )
    collection_enabled_count = int(
        session.scalar(
            select(func.count())
            .select_from(MarketSourceEndpoint)
            .where(MarketSourceEndpoint.collection_enabled.is_(True))
        )
        or 0
    )
    blocked_count = int(
        session.scalar(
            select(func.count())
            .select_from(MarketSourceEndpoint)
            .where(MarketSourceEndpoint.lifecycle_status.like("blocked_%"))
        )
        or 0
    )
    manual_only_count = int(
        session.scalar(
            select(func.count())
            .select_from(MarketSourceEndpoint)
            .where(MarketSourceEndpoint.access_mode == "manual_submission_only")
        )
        or 0
    )
    enabled_policy_count = int(
        session.scalar(
            select(func.count())
            .select_from(MarketSourceEndpoint)
            .where(
                MarketSourceEndpoint.endpoint_id.in_(POLICY_RESEARCH_ENDPOINT_IDS),
                MarketSourceEndpoint.collection_enabled.is_(True),
            )
        )
        or 0
    )
    status: OperationsStatus = "healthy" if source_count > 0 else "warning"
    message = (
        "Registered source endpoints are present."
        if source_count > 0
        else "No public source registry entries are present in this database."
    )
    return OperationsHealthItem(
        key="source_registry",
        label="Source Registry",
        status=status,
        message=message,
        observed_at=None,
        details={
            "source_count": source_count,
            "endpoint_count": endpoint_count,
            "collection_enabled_count": collection_enabled_count,
            "disabled_count": disabled_count,
            "blocked_count": blocked_count,
            "manual_only_count": manual_only_count,
            "policy_allowlist_endpoint_ids": list(POLICY_RESEARCH_ENDPOINT_IDS),
            "policy_allowlist_collection_enabled_count": enabled_policy_count,
        },
    )


def _endpoint_health_summary(session: Session) -> OperationsHealthItem:
    checks = list(
        session.scalars(
            select(MarketEndpointHealthCheck)
            .order_by(MarketEndpointHealthCheck.checked_at.desc())
            .limit(5)
        )
    )
    latest_check = checks[0] if checks else None
    if any(check.health_status == "failed" for check in checks):
        status: OperationsStatus = "critical"
    elif any(check.health_status == "warning" for check in checks):
        status = "warning"
    else:
        status = "healthy"
    message = (
        "Latest endpoint health records are stored from prior checks."
        if checks
        else "No endpoint health records are stored; overview did not run a probe."
    )
    return OperationsHealthItem(
        key="endpoint_health",
        label="Endpoint Health Records",
        status=status,
        message=message,
        observed_at=(
            _as_local_datetime(latest_check.checked_at) if latest_check is not None else None
        ),
        details={
            "recent_check_count": len(checks),
            "recent_statuses": [
                {
                    "endpoint_id": check.endpoint_id,
                    "health_status": check.health_status,
                    "checked_at": _datetime_isoformat(check.checked_at),
                    "error_code": check.error_code,
                }
                for check in checks
            ],
            "network_probe_performed": False,
        },
    )


def _operation_action_items(
    freshness: list[OperationsFreshnessItem],
    recent_incidents: list[WorkflowRun],
) -> list[OperationsActionItem]:
    label_by_job = {
        "weather_refresh": "Refresh Weather Reference Points",
        "policy_research_refresh": "Check Policy Research Sources",
        "bench_dispatch_research": "Archive BENCH Research Benchmark",
        "daily_intelligence_brief": "Generate Daily Intelligence Brief",
        "demo_research_workspace_seed": "Seed Local RC Demo Data",
    }
    freshness_by_job = {
        "weather_refresh": next(
            item for item in freshness if item.key == "weather_features"
        ).status,
        "daily_intelligence_brief": next(
            item for item in freshness if item.key == "daily_brief"
        ).status,
        "bench_dispatch_research": next(
            item for item in freshness if item.key == "bench_dispatch_research"
        ).status,
        "policy_research_refresh": next(
            item for item in freshness if item.key == "policy_documents"
        ).status,
        "demo_research_workspace_seed": "healthy",
    }
    incident_job_keys = {run.workflow_key for run in recent_incidents}
    actions: list[OperationsActionItem] = []
    for job in OPERATION_JOBS:
        has_incident = job.job_key in incident_job_keys
        freshness_status = freshness_by_job[job.job_key]
        recommended = job.manual_trigger_enabled and (
            has_incident or freshness_status in {"warning", "critical"}
        )
        if has_incident:
            reason = "Recent failed or retry-wait run exists for this fixed job."
        elif freshness_status in {"warning", "critical"}:
            reason = "Related data freshness item needs attention."
        else:
            reason = "Available for manual operator-triggered rerun."
        actions.append(
            OperationsActionItem(
                job_key=job.job_key,
                label=label_by_job[job.job_key],
                description=job.description,
                schedule=job.schedule,
                timezone=job.timezone,
                manual_trigger_enabled=job.manual_trigger_enabled,
                research_only=job.research_only,
                recommended=recommended,
                reason=reason,
            )
        )
    return actions


def _short_bench_region(region_code: str) -> str:
    return region_code.removeprefix("BENCH_NEM_")


def claim_operation_job(
    *,
    worker_id: str,
    session: Session,
    claimed_at: datetime | None = None,
    lease_seconds: int = DEFAULT_WORKFLOW_LEASE_SECONDS,
) -> ClaimedWorkflowRun | None:
    if lease_seconds <= 0:
        raise ValueError("Workflow lease_seconds must be positive.")
    now = claimed_at or _now()
    lease_token = uuid4().hex
    with session.begin():
        fail_exhausted_workflow_leases(
            session,
            expired_at=now,
            max_attempts=MAX_WORKFLOW_ATTEMPTS,
        )
        run = claim_next_workflow_run(
            session,
            claimed_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            worker_id=worker_id,
            lease_token=lease_token,
            max_attempts=MAX_WORKFLOW_ATTEMPTS,
        )
    if run is None:
        return None
    return ClaimedWorkflowRun(run=_to_workflow_run_response(run), lease_token=lease_token)


def renew_operation_job_lease(
    workflow_run_id: str,
    *,
    worker_id: str,
    lease_token: str,
    session: Session,
    renewed_at: datetime | None = None,
    lease_seconds: int = DEFAULT_WORKFLOW_LEASE_SECONDS,
) -> WorkflowRunResponse:
    if lease_seconds <= 0:
        raise ValueError("Workflow lease_seconds must be positive.")
    now = renewed_at or _now()
    with session.begin():
        run = _require_claimed_workflow_run(
            session,
            workflow_run_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
    return _to_workflow_run_response(run)


def complete_operation_job(
    workflow_run_id: str,
    *,
    worker_id: str,
    lease_token: str,
    status: str,
    summary: dict[str, object],
    session: Session,
    completed_at: datetime | None = None,
) -> WorkflowRunResponse:
    if status not in {"succeeded", "skipped"}:
        raise ValueError("Completed workflow status must be succeeded or skipped.")
    with session.begin():
        run = _require_claimed_workflow_run(
            session,
            workflow_run_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        run.status = status
        run.completed_at = completed_at or _now()
        run.summary_json = summary
        run.lease_expires_at = None
        run.lease_token = None
        run.error_code = None
        run.error_message = None
    return _to_workflow_run_response(run)


def fail_operation_job(
    workflow_run_id: str,
    *,
    worker_id: str,
    lease_token: str,
    code: str,
    message: str,
    summary: dict[str, object],
    transient: bool,
    session: Session,
    failed_at: datetime | None = None,
    retry_delay_seconds: int = DEFAULT_WORKFLOW_RETRY_DELAY_SECONDS,
) -> WorkflowRunResponse:
    if retry_delay_seconds < 0:
        raise ValueError("Workflow retry_delay_seconds must not be negative.")
    now = failed_at or _now()
    with session.begin():
        run = _require_claimed_workflow_run(
            session,
            workflow_run_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        retry = transient and run.attempt_count < MAX_WORKFLOW_ATTEMPTS
        run.status = "retry_wait" if retry else "failed"
        run.available_at = now + timedelta(seconds=retry_delay_seconds) if retry else now
        run.completed_at = None if retry else now
        run.summary_json = summary
        run.lease_expires_at = None
        run.lease_token = None
        run.error_code = code
        run.error_message = message
    return _to_workflow_run_response(run)


def queue_operation_job(job_key: str, *, session: Session) -> WorkflowRunResponse:
    job = _get_registered_job(job_key)
    if not job.manual_trigger_enabled:
        raise OperationJobManualTriggerDisabledError(job_key)
    return _queue_operation_job(
        job_key,
        trigger_mode="manual_request",
        prefect_flow_run_id=None,
        started_at=_now(),
        scheduled_for=None,
        schedule_identity=None,
        session=session,
    )


def queue_scheduled_operation_job(
    job_key: str,
    *,
    scheduled_for: datetime,
    prefect_flow_run_id: str | None,
    session: Session,
) -> WorkflowRunResponse | None:
    _get_registered_job(job_key)
    local_schedule_time = scheduled_for.astimezone(ZoneInfo("Asia/Shanghai"))
    schedule_identity = f"{job_key}:{local_schedule_time.isoformat()}"
    with session.begin():
        if job_key == "daily_intelligence_brief" and not is_mainland_workday(
            local_schedule_time.date(),
            session=session,
        ):
            return None
        existing = get_workflow_run_by_schedule_identity(session, schedule_identity)
        if existing is not None:
            return _to_workflow_run_response(existing)
        try:
            with session.begin_nested():
                run = _add_queued_operation_job(
                    job_key,
                    trigger_mode="prefect_schedule",
                    prefect_flow_run_id=prefect_flow_run_id,
                    started_at=_now(),
                    scheduled_for=local_schedule_time,
                    schedule_identity=schedule_identity,
                    session=session,
                )
                session.flush()
        except IntegrityError:
            existing = get_workflow_run_by_schedule_identity(session, schedule_identity)
            if existing is None:
                raise
            run = existing
    return _to_workflow_run_response(run)


def _queue_operation_job(
    job_key: str,
    *,
    trigger_mode: str,
    prefect_flow_run_id: str | None,
    started_at: datetime,
    scheduled_for: datetime | None,
    schedule_identity: str | None,
    session: Session,
) -> WorkflowRunResponse:
    _get_registered_job(job_key)
    with session.begin():
        run = _add_queued_operation_job(
            job_key,
            trigger_mode=trigger_mode,
            prefect_flow_run_id=prefect_flow_run_id,
            started_at=started_at,
            scheduled_for=scheduled_for,
            schedule_identity=schedule_identity,
            session=session,
        )
    return _to_workflow_run_response(run)


def _get_registered_job(job_key: str) -> OperationJob:
    for job in OPERATION_JOBS:
        if job.job_key == job_key:
            return job
    raise OperationJobNotFoundError(job_key)


def _add_queued_operation_job(
    job_key: str,
    *,
    trigger_mode: str,
    prefect_flow_run_id: str | None,
    started_at: datetime,
    scheduled_for: datetime | None,
    schedule_identity: str | None,
    session: Session,
) -> WorkflowRun:
    return add_workflow_run(
        session,
        WorkflowRun(
            workflow_run_id=f"workflow_{uuid4().hex}",
            workflow_key=job_key,
            trigger_mode=trigger_mode,
            prefect_flow_run_id=prefect_flow_run_id,
            scheduled_for=scheduled_for,
            schedule_identity=schedule_identity,
            status="queued",
            started_at=started_at,
            available_at=started_at,
            claimed_at=None,
            lease_expires_at=None,
            worker_id=None,
            lease_token=None,
            attempt_count=0,
            completed_at=None,
            summary_json={
                "message": "Queued for the local workstation worker.",
                "research_only": job_key == "bench_dispatch_research",
            },
            error_code=None,
            error_message=None,
        ),
    )


def _to_workflow_run_response(run: WorkflowRun) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        workflow_run_id=run.workflow_run_id,
        workflow_key=run.workflow_key,
        trigger_mode=run.trigger_mode,
        prefect_flow_run_id=run.prefect_flow_run_id,
        scheduled_for=run.scheduled_for,
        status=run.status,
        started_at=run.started_at,
        available_at=run.available_at,
        claimed_at=run.claimed_at,
        lease_expires_at=run.lease_expires_at,
        worker_id=run.worker_id,
        attempt_count=run.attempt_count,
        completed_at=run.completed_at,
        summary=run.summary_json,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _require_claimed_workflow_run(
    session: Session,
    workflow_run_id: str,
    *,
    worker_id: str,
    lease_token: str,
) -> WorkflowRun:
    run = get_workflow_run(session, workflow_run_id)
    if run is None:
        raise WorkflowRunNotFoundError(workflow_run_id)
    if run.status != "running" or run.worker_id != worker_id or run.lease_token != lease_token:
        raise WorkflowLeaseLostError("Workflow run lease is no longer owned by this worker.")
    return run
