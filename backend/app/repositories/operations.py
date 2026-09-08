from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.operations import RawObject, WorkdayCalendarOverride, WorkflowRun


def get_raw_object_by_hash(session: Session, content_sha256: str) -> RawObject | None:
    return session.scalar(select(RawObject).where(RawObject.content_sha256 == content_sha256))


def get_raw_object(session: Session, raw_object_id: str) -> RawObject | None:
    return session.get(RawObject, raw_object_id)


def add_raw_object(session: Session, raw_object: RawObject) -> RawObject:
    session.add(raw_object)
    return raw_object


def list_workflow_runs(session: Session, *, limit: int) -> list[WorkflowRun]:
    statement = select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(limit)
    return list(session.scalars(statement))


def get_workflow_run(session: Session, workflow_run_id: str) -> WorkflowRun | None:
    return session.get(WorkflowRun, workflow_run_id)


def add_workflow_run(session: Session, run: WorkflowRun) -> WorkflowRun:
    session.add(run)
    return run


def get_workflow_run_by_schedule_identity(
    session: Session, schedule_identity: str
) -> WorkflowRun | None:
    return session.scalar(
        select(WorkflowRun).where(WorkflowRun.schedule_identity == schedule_identity)
    )


def fail_exhausted_workflow_leases(
    session: Session,
    *,
    expired_at: datetime,
    max_attempts: int,
) -> list[WorkflowRun]:
    statement = (
        select(WorkflowRun)
        .where(
            (WorkflowRun.status == "running")
            & (WorkflowRun.lease_expires_at.is_not(None))
            & (WorkflowRun.lease_expires_at <= expired_at)
            & (WorkflowRun.attempt_count >= max_attempts)
        )
        .with_for_update(skip_locked=True)
    )
    runs = list(session.scalars(statement))
    for run in runs:
        run.status = "failed"
        run.available_at = expired_at
        run.completed_at = expired_at
        run.lease_expires_at = None
        run.lease_token = None
        run.summary_json = {
            "message": "Workflow lease expired after the allowed recovery attempt.",
            "transient": False,
        }
        run.error_code = "workflow_lease_exhausted"
        run.error_message = "Workflow lease expired after the allowed recovery attempt."
    return runs


def claim_next_workflow_run(
    session: Session,
    *,
    claimed_at: datetime,
    lease_expires_at: datetime,
    worker_id: str,
    lease_token: str,
    max_attempts: int,
) -> WorkflowRun | None:
    statement = (
        select(WorkflowRun)
        .where(
            or_(
                (
                    WorkflowRun.status.in_(("queued", "retry_wait"))
                    & (WorkflowRun.available_at <= claimed_at)
                ),
                (
                    (WorkflowRun.status == "running")
                    & (WorkflowRun.lease_expires_at.is_not(None))
                    & (WorkflowRun.lease_expires_at <= claimed_at)
                ),
            )
            & (WorkflowRun.attempt_count < max_attempts)
        )
        .order_by(WorkflowRun.available_at, WorkflowRun.started_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    run = session.scalar(statement)
    if run is None:
        return None
    run.status = "running"
    run.claimed_at = claimed_at
    run.lease_expires_at = lease_expires_at
    run.worker_id = worker_id
    run.lease_token = lease_token
    run.attempt_count += 1
    run.completed_at = None
    run.error_code = None
    run.error_message = None
    return run


def get_workday_override(session: Session, calendar_date: date) -> WorkdayCalendarOverride | None:
    return session.get(WorkdayCalendarOverride, calendar_date)
