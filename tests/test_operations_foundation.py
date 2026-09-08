from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.operations import WorkdayCalendarOverride
from backend.app.services import operations
from backend.app.services.operations import (
    OPERATION_JOBS,
    is_mainland_workday,
    preserve_raw_object,
    queue_scheduled_operation_job,
)
from backend.app.storage.blob_store import MemoryBlobStore


def test_raw_object_preservation_uses_sha256_and_deduplicates(
    db_session_factory: sessionmaker[Session],
) -> None:
    store = MemoryBlobStore()
    with db_session_factory() as session:
        first, first_duplicate = preserve_raw_object(
            content=b"official policy",
            media_type="text/plain",
            data_mode="public_observed",
            source_url="https://example.test/policy.txt",
            metadata={"provider": "test"},
            store=store,
            session=session,
        )
        second, second_duplicate = preserve_raw_object(
            content=b"official policy",
            media_type="text/plain",
            data_mode="public_observed",
            source_url="https://example.test/policy.txt",
            metadata={"provider": "test"},
            store=store,
            session=session,
        )

    assert first_duplicate is False
    assert second_duplicate is True
    assert second.raw_object_id == first.raw_object_id
    assert store.get(object_key=first.object_key) == b"official policy"


def test_workday_calendar_uses_weekdays_and_persisted_overrides(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        session.add(
            WorkdayCalendarOverride(
                calendar_date=date(2026, 10, 10),
                is_workday=True,
                source_kind="official_2026_adjusted_workday",
                source_url="https://calendar.example.invalid/",
                note="Adjusted workday.",
            )
        )
    with db_session_factory() as session:
        assert is_mainland_workday(date(2026, 6, 2), session=session) is True
        assert is_mainland_workday(date(2026, 6, 6), session=session) is False
        assert is_mainland_workday(date(2026, 10, 10), session=session) is True


def test_operation_jobs_are_visible_and_keep_bench_research_only(client: TestClient) -> None:
    response = client.get("/v1/operations/jobs")

    assert response.status_code == 200
    jobs = {item["job_key"]: item for item in response.json()["items"]}
    assert jobs["weather_refresh"]["schedule"] == "0 7,16 * * *"
    assert jobs["daily_intelligence_brief"]["timezone"] == "Asia/Shanghai"
    assert jobs["bench_dispatch_research"]["research_only"] is True
    assert jobs["demo_research_workspace_seed"]["schedule"] == "manual"
    assert jobs["demo_research_workspace_seed"]["manual_trigger_enabled"] is True


def test_operation_job_manual_trigger_queues_only_registered_job(client: TestClient) -> None:
    queued = client.post("/v1/operations/jobs/weather_refresh/run")
    fetched = client.get(f"/v1/operations/runs/{queued.json()['workflow_run_id']}")
    unknown = client.post("/v1/operations/jobs/arbitrary_network_task/run")
    missing = client.get("/v1/operations/runs/workflow_missing")

    assert queued.status_code == 200
    assert queued.json()["workflow_key"] == "weather_refresh"
    assert queued.json()["status"] == "queued"
    assert queued.json()["attempt_count"] == 0
    assert fetched.status_code == 200
    assert fetched.json()["workflow_run_id"] == queued.json()["workflow_run_id"]
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "operation_job_not_found"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "workflow_run_not_found"


def test_operation_job_manual_trigger_respects_registry_capability(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operations,
        "OPERATION_JOBS",
        tuple(
            replace(job, manual_trigger_enabled=False) if job.job_key == "weather_refresh" else job
            for job in OPERATION_JOBS
        ),
    )

    response = client.post("/v1/operations/jobs/weather_refresh/run")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "operation_job_manual_trigger_disabled"


def test_daily_brief_schedule_skips_weekend_until_official_override(
    db_session_factory: sessionmaker[Session],
) -> None:
    scheduled_for = datetime(2026, 10, 10, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    with db_session_factory() as session:
        assert (
            queue_scheduled_operation_job(
                "daily_intelligence_brief",
                scheduled_for=scheduled_for,
                prefect_flow_run_id="prefect_skipped",
                session=session,
            )
            is None
        )
    with db_session_factory.begin() as session:
        session.add(
            WorkdayCalendarOverride(
                calendar_date=scheduled_for.date(),
                is_workday=True,
                source_kind="official_2026_adjusted_workday",
                source_url="https://calendar.example.invalid/",
                note="Adjusted workday.",
            )
        )
    with db_session_factory() as session:
        queued = queue_scheduled_operation_job(
            "daily_intelligence_brief",
            scheduled_for=scheduled_for,
            prefect_flow_run_id="prefect_queued",
            session=session,
        )

    assert queued is not None
    assert queued.trigger_mode == "prefect_schedule"
    assert queued.prefect_flow_run_id == "prefect_queued"


def test_bench_schedule_queue_remains_research_only(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        queued = queue_scheduled_operation_job(
            "bench_dispatch_research",
            scheduled_for=datetime(2026, 6, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
            prefect_flow_run_id="prefect_bench",
            session=session,
        )

    assert queued is not None
    assert queued.summary["research_only"] is True


def test_schedule_queue_is_idempotent_for_the_same_planned_slot(
    db_session_factory: sessionmaker[Session],
) -> None:
    scheduled_for = datetime(2026, 6, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    with db_session_factory() as session:
        first = queue_scheduled_operation_job(
            "bench_dispatch_research",
            scheduled_for=scheduled_for,
            prefect_flow_run_id="prefect_first",
            session=session,
        )
    with db_session_factory() as session:
        second = queue_scheduled_operation_job(
            "bench_dispatch_research",
            scheduled_for=scheduled_for,
            prefect_flow_run_id="prefect_duplicate",
            session=session,
        )

    assert first is not None
    assert second is not None
    assert second.workflow_run_id == first.workflow_run_id
    assert second.prefect_flow_run_id == "prefect_first"
    assert second.scheduled_for is not None
    assert second.scheduled_for.replace(tzinfo=ZoneInfo("Asia/Shanghai")) == scheduled_for
