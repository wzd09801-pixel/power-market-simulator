from __future__ import annotations

import logging
import os
import socket
import time
from collections.abc import Callable
from threading import Event, Thread

from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings
from backend.app.db.session import get_session_factory
from backend.app.schemas.operations import WorkflowRunResponse
from backend.app.services.operations import (
    WorkflowLeaseLostError,
    claim_operation_job,
    complete_operation_job,
    fail_operation_job,
    get_workflow_run_by_id,
    renew_operation_job_lease,
)
from backend.app.services.workstation_jobs import (
    FixedJobExecutionError,
    FixedJobResult,
    execute_fixed_workstation_job,
)

logger = logging.getLogger(__name__)
JobExecutor = Callable[..., FixedJobResult]


def consume_one_workflow_run(
    factory: sessionmaker[Session],
    *,
    worker_id: str,
    execute_job: JobExecutor = execute_fixed_workstation_job,
    lease_seconds: int = 300,
    retry_delay_seconds: int = 60,
) -> WorkflowRunResponse | None:
    with factory() as session:
        claimed = claim_operation_job(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            session=session,
        )
    if claimed is None:
        return None

    stop_renewal = Event()
    renewal_thread = Thread(
        target=_renew_lease_until_stopped,
        kwargs={
            "factory": factory,
            "workflow_run_id": claimed.run.workflow_run_id,
            "worker_id": worker_id,
            "lease_token": claimed.lease_token,
            "lease_seconds": lease_seconds,
            "stop": stop_renewal,
        },
        daemon=True,
    )
    renewal_thread.start()
    try:
        with factory() as session:
            result = execute_job(claimed.run.workflow_key, session=session)
    except FixedJobExecutionError as exc:
        logger.warning(
            "Fixed workstation job failed run=%s key=%s code=%s transient=%s",
            claimed.run.workflow_run_id,
            claimed.run.workflow_key,
            exc.code,
            exc.transient,
        )
        return _fail_claimed_workflow_run(
            factory,
            workflow_run_id=claimed.run.workflow_run_id,
            worker_id=worker_id,
            lease_token=claimed.lease_token,
            code=exc.code,
            message=exc.message,
            summary={
                "message": "Fixed workstation job failed.",
                "transient": exc.transient,
            },
            transient=exc.transient,
            retry_delay_seconds=retry_delay_seconds,
        )
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        logger.exception(
            "Unexpected fixed workstation job failure run=%s key=%s",
            claimed.run.workflow_run_id,
            claimed.run.workflow_key,
        )
        return _fail_claimed_workflow_run(
            factory,
            workflow_run_id=claimed.run.workflow_run_id,
            worker_id=worker_id,
            lease_token=claimed.lease_token,
            code="workstation_job_unhandled_error",
            message=f"Fixed workstation job failed unexpectedly: {type(exc).__name__}.",
            summary={"message": "Fixed workstation job failed unexpectedly."},
            transient=False,
            retry_delay_seconds=retry_delay_seconds,
        )
    finally:
        stop_renewal.set()
        renewal_thread.join()

    try:
        with factory() as session:
            completed = complete_operation_job(
                claimed.run.workflow_run_id,
                worker_id=worker_id,
                lease_token=claimed.lease_token,
                status=result.status,
                summary=result.summary,
                session=session,
            )
    except WorkflowLeaseLostError:
        return _get_run_after_lost_lease(factory, claimed.run.workflow_run_id)
    logger.info(
        "Completed fixed workstation job run=%s key=%s status=%s",
        claimed.run.workflow_run_id,
        claimed.run.workflow_key,
        completed.status,
    )
    return completed


def _renew_lease_until_stopped(
    *,
    factory: sessionmaker[Session],
    workflow_run_id: str,
    worker_id: str,
    lease_token: str,
    lease_seconds: int,
    stop: Event,
) -> None:
    interval_seconds = max(0.1, lease_seconds / 3)
    while not stop.wait(interval_seconds):
        try:
            with factory() as session:
                renew_operation_job_lease(
                    workflow_run_id,
                    worker_id=worker_id,
                    lease_token=lease_token,
                    lease_seconds=lease_seconds,
                    session=session,
                )
        except WorkflowLeaseLostError:
            logger.warning("Stopped lease renewal after ownership changed run=%s", workflow_run_id)
            return
        except Exception:  # pragma: no cover - defensive renewal boundary
            logger.exception("Workflow lease renewal failed run=%s", workflow_run_id)


def _fail_claimed_workflow_run(
    factory: sessionmaker[Session],
    *,
    workflow_run_id: str,
    worker_id: str,
    lease_token: str,
    code: str,
    message: str,
    summary: dict[str, object],
    transient: bool,
    retry_delay_seconds: int,
) -> WorkflowRunResponse:
    try:
        with factory() as session:
            return fail_operation_job(
                workflow_run_id,
                worker_id=worker_id,
                lease_token=lease_token,
                code=code,
                message=message,
                summary=summary,
                transient=transient,
                retry_delay_seconds=retry_delay_seconds,
                session=session,
            )
    except WorkflowLeaseLostError:
        return _get_run_after_lost_lease(factory, workflow_run_id)


def _get_run_after_lost_lease(
    factory: sessionmaker[Session], workflow_run_id: str
) -> WorkflowRunResponse:
    logger.warning(
        "Ignored stale workflow completion after lease ownership changed run=%s",
        workflow_run_id,
    )
    with factory() as session:
        return get_workflow_run_by_id(workflow_run_id, session=session)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    factory = get_session_factory(settings.database_url)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("Starting fixed workstation operation worker id=%s", worker_id)
    while True:
        try:
            run = consume_one_workflow_run(
                factory,
                worker_id=worker_id,
                lease_seconds=settings.operation_worker_lease_seconds,
                retry_delay_seconds=settings.operation_worker_retry_delay_seconds,
            )
        except Exception:  # pragma: no cover - defensive daemon boundary
            logger.exception("Operation worker loop failed; polling will continue.")
            run = None
        if run is None:
            time.sleep(settings.operation_worker_poll_seconds)


if __name__ == "__main__":
    main()
