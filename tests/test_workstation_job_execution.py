from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.adapters.bench_dispatch import BenchDispatchClient
from backend.app.models.forecasting import ForecastResearchDataset
from backend.app.models.market import MarketDataSource, MarketIngestionRun, MarketSourceEndpoint
from backend.app.models.operations import RawObject
from backend.app.models.weather import WeatherFeatureSnapshot, WeatherLocation
from backend.app.services.deepseek import DeepSeekProviderError
from backend.app.services.embeddings import EmbeddingClient, HashEmbeddingClient
from backend.app.services.operations import (
    WorkflowLeaseLostError,
    claim_operation_job,
    complete_operation_job,
    get_workflow_run_by_id,
    queue_operation_job,
    renew_operation_job_lease,
)
from backend.app.services.registered_source_collector import REGISTERED_STATIC_HTTP_ADAPTER_KEY
from backend.app.services.workstation_jobs import (
    BENCH_REGIONS,
    FixedJobExecutionError,
    FixedJobResult,
    execute_fixed_workstation_job,
)
from backend.app.storage.blob_store import BlobStoreError, MemoryBlobStore
from tests.test_bench_dispatch_adapter import FakeResponse, FakeSession, _make_daily_archive
from tests.test_registered_source_collector import (
    FakeHttpClient as RegisteredFakeHttpClient,
)
from tests.test_registered_source_collector import (
    FakeResponse as RegisteredFakeResponse,
)
from tests.test_weather import build_client
from workers.consume import consume_one_workflow_run

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FailingDeepSeekClient:
    def complete_json(self, *, prompt: str, deep_analysis: bool) -> tuple[dict[str, object], str]:
        del prompt, deep_analysis
        raise DeepSeekProviderError("offline")


def _add_market_endpoint(
    session: Session,
    *,
    endpoint_id: str,
    collection_enabled: bool,
    access_mode: str = "anonymous_https",
    lifecycle_status: str = "candidate_unverified",
    adapter_key: str | None = None,
) -> None:
    source_id = f"source_{endpoint_id}"
    session.add(
        MarketDataSource(
            source_id=source_id,
            name=source_id,
            operator_name=source_id,
            official_url="https://example.test/",
            market_scope="test",
            notes="Test source.",
            data_mode="public_derived",
            trust_tier="candidate",
            attribution_text="Test source.",
            collection_permission_note="Test only.",
        )
    )
    session.add(
        MarketSourceEndpoint(
            endpoint_id=endpoint_id,
            source_id=source_id,
            name=endpoint_id,
            canonical_url="https://example.test/",
            endpoint_kind="test",
            allowed_domains_json=["example.test"],
            visibility_scope="internet_public",
            access_mode=access_mode,
            lifecycle_status=lifecycle_status,
            content_formats_json=["text/html"],
            data_granularity="test",
            adapter_key=adapter_key,
            parser_key=None,
            parser_version=None,
            health_check_enabled=False,
            manual_submission_enabled=False,
            collection_enabled=collection_enabled,
            health_probe_not_before=None,
            cadence=None,
            notes="Test endpoint.",
        )
    )


def test_worker_completes_claimed_fixed_job(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        queued = queue_operation_job("policy_research_refresh", session=session)

    completed = consume_one_workflow_run(
        db_session_factory,
        worker_id="worker-success",
        execute_job=lambda _job_key, *, session: FixedJobResult(
            status="skipped",
            summary={"message": "No enabled endpoints.", "request_count": 0},
        ),
    )

    assert completed is not None
    assert completed.workflow_run_id == queued.workflow_run_id
    assert completed.status == "skipped"
    assert completed.attempt_count == 1
    assert completed.completed_at is not None


def test_worker_retries_transient_failure_only_once(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        queue_operation_job("weather_refresh", session=session)

    def fail_transient(_job_key: str, *, session: Session) -> FixedJobResult:
        del session
        raise FixedJobExecutionError(
            code="open_meteo_network_error",
            message="offline",
            transient=True,
        )

    first = consume_one_workflow_run(
        db_session_factory,
        worker_id="worker-retry",
        execute_job=fail_transient,
        retry_delay_seconds=0,
    )
    second = consume_one_workflow_run(
        db_session_factory,
        worker_id="worker-retry",
        execute_job=fail_transient,
        retry_delay_seconds=0,
    )

    assert first is not None
    assert first.status == "retry_wait"
    assert first.attempt_count == 1
    assert second is not None
    assert second.status == "failed"
    assert second.attempt_count == 2
    assert second.error_code == "open_meteo_network_error"


def test_worker_does_not_retry_deterministic_failure(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        queue_operation_job("policy_research_refresh", session=session)

    def fail_deterministic(_job_key: str, *, session: Session) -> FixedJobResult:
        del session
        raise FixedJobExecutionError(
            code="policy_collection_adapter_not_registered",
            message="adapter missing",
            transient=False,
        )

    failed = consume_one_workflow_run(
        db_session_factory,
        worker_id="worker-deterministic",
        execute_job=fail_deterministic,
    )

    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempt_count == 1


def test_expired_workflow_lease_can_be_recovered(
    db_session_factory: sessionmaker[Session],
) -> None:
    queued_at = datetime.now(tz=SHANGHAI) + timedelta(seconds=1)
    with db_session_factory() as session:
        queued = queue_operation_job("weather_refresh", session=session)
    with db_session_factory() as session:
        first = claim_operation_job(
            worker_id="worker-one",
            claimed_at=queued_at,
            lease_seconds=1,
            session=session,
        )
    with db_session_factory() as session:
        second = claim_operation_job(
            worker_id="worker-two",
            claimed_at=queued_at + timedelta(seconds=2),
            session=session,
        )

    assert first is not None
    assert first.run.workflow_run_id == queued.workflow_run_id
    assert first.run.attempt_count == 1
    assert second is not None
    assert second.run.workflow_run_id == queued.workflow_run_id
    assert second.run.worker_id == "worker-two"
    assert second.run.attempt_count == 2


def test_expired_workflow_lease_fails_after_one_recovery_attempt(
    db_session_factory: sessionmaker[Session],
) -> None:
    queued_at = datetime.now(tz=SHANGHAI) + timedelta(seconds=1)
    with db_session_factory() as session:
        queued = queue_operation_job("weather_refresh", session=session)
    with db_session_factory() as session:
        first = claim_operation_job(
            worker_id="worker-one",
            claimed_at=queued_at,
            lease_seconds=1,
            session=session,
        )
    with db_session_factory() as session:
        second = claim_operation_job(
            worker_id="worker-two",
            claimed_at=queued_at + timedelta(seconds=2),
            lease_seconds=1,
            session=session,
        )
    with db_session_factory() as session:
        third = claim_operation_job(
            worker_id="worker-three",
            claimed_at=queued_at + timedelta(seconds=4),
            lease_seconds=1,
            session=session,
        )
    with db_session_factory() as session:
        failed = get_workflow_run_by_id(queued.workflow_run_id, session=session)

    assert first is not None
    assert second is not None
    assert third is None
    assert failed.status == "failed"
    assert failed.attempt_count == 2
    assert failed.error_code == "workflow_lease_exhausted"


def test_workflow_lease_renewal_prevents_early_recovery(
    db_session_factory: sessionmaker[Session],
) -> None:
    queued_at = datetime.now(tz=SHANGHAI) + timedelta(seconds=1)
    with db_session_factory() as session:
        queue_operation_job("weather_refresh", session=session)
    with db_session_factory() as session:
        claimed = claim_operation_job(
            worker_id="worker-one",
            claimed_at=queued_at,
            lease_seconds=2,
            session=session,
        )
    assert claimed is not None
    with db_session_factory() as session:
        renewed = renew_operation_job_lease(
            claimed.run.workflow_run_id,
            worker_id="worker-one",
            lease_token=claimed.lease_token,
            renewed_at=queued_at + timedelta(seconds=1),
            lease_seconds=4,
            session=session,
        )
    with db_session_factory() as session:
        replacement = claim_operation_job(
            worker_id="worker-two",
            claimed_at=queued_at + timedelta(seconds=3),
            lease_seconds=2,
            session=session,
        )

    assert renewed.lease_expires_at == queued_at + timedelta(seconds=5)
    assert replacement is None


def test_stale_worker_cannot_complete_recovered_workflow_run(
    db_session_factory: sessionmaker[Session],
) -> None:
    queued_at = datetime.now(tz=SHANGHAI) + timedelta(seconds=1)
    with db_session_factory() as session:
        queue_operation_job("weather_refresh", session=session)
    with db_session_factory() as session:
        first = claim_operation_job(
            worker_id="worker-one",
            claimed_at=queued_at,
            lease_seconds=1,
            session=session,
        )
    with db_session_factory() as session:
        second = claim_operation_job(
            worker_id="worker-two",
            claimed_at=queued_at + timedelta(seconds=2),
            session=session,
        )
    assert first is not None
    assert second is not None

    with db_session_factory() as session:
        with pytest.raises(WorkflowLeaseLostError):
            complete_operation_job(
                first.run.workflow_run_id,
                worker_id="worker-one",
                lease_token=first.lease_token,
                status="succeeded",
                summary={"message": "stale"},
                session=session,
            )
    with db_session_factory() as session:
        completed = complete_operation_job(
            second.run.workflow_run_id,
            worker_id="worker-two",
            lease_token=second.lease_token,
            status="succeeded",
            summary={"message": "current"},
            session=session,
        )

    assert completed.status == "succeeded"
    assert completed.summary["message"] == "current"


def test_worker_ignores_stale_completion_after_lease_recovery(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        queued = queue_operation_job("weather_refresh", session=session)

    def recover_during_execution(_job_key: str, *, session: Session) -> FixedJobResult:
        del session
        with db_session_factory() as recovery_session:
            recovered = claim_operation_job(
                worker_id="worker-two",
                claimed_at=datetime.now(tz=SHANGHAI) + timedelta(seconds=2),
                lease_seconds=300,
                session=recovery_session,
            )
        assert recovered is not None
        return FixedJobResult(status="succeeded", summary={"message": "stale"})

    current = consume_one_workflow_run(
        db_session_factory,
        worker_id="worker-one",
        execute_job=recover_during_execution,
        lease_seconds=1,
    )

    assert current is not None
    assert current.workflow_run_id == queued.workflow_run_id
    assert current.worker_id == "worker-two"
    assert current.status == "running"
    assert current.summary["message"] == "Queued for the local workstation worker."


def test_policy_refresh_skips_when_all_collection_endpoints_are_disabled(
    db_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_initialized(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Disabled policy refresh must not initialize external clients.")

    monkeypatch.setattr(
        "backend.app.services.workstation_jobs.MinioBlobStore",
        fail_if_initialized,
    )
    monkeypatch.setattr(
        "backend.app.services.workstation_jobs.get_open_meteo_client",
        fail_if_initialized,
    )
    monkeypatch.setattr(
        "backend.app.services.workstation_jobs.get_bench_dispatch_client",
        fail_if_initialized,
    )
    monkeypatch.setattr(
        "backend.app.services.workstation_jobs.get_deepseek_client",
        fail_if_initialized,
    )
    with db_session_factory() as session:
        result = execute_fixed_workstation_job(
            "policy_research_refresh",
            session=session,
        )

    assert result.status == "skipped"
    assert result.summary["request_count"] == 0


def test_policy_refresh_ignores_enabled_non_policy_endpoint(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        _add_market_endpoint(
            session,
            endpoint_id="example_province_portal_home",
            collection_enabled=True,
        )
    with db_session_factory() as session:
        result = execute_fixed_workstation_job("policy_research_refresh", session=session)

    assert result.status == "skipped"
    assert result.summary["request_count"] == 0


def test_policy_refresh_rejects_enabled_manual_only_endpoint_without_request(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        _add_market_endpoint(
            session,
            endpoint_id="institute_home",
            collection_enabled=True,
            access_mode="manual_submission_only",
            lifecycle_status="blocked_anti_automation",
        )
    with db_session_factory() as session:
        with pytest.raises(FixedJobExecutionError) as exc_info:
            execute_fixed_workstation_job("policy_research_refresh", session=session)

    assert exc_info.value.code == "policy_collection_endpoint_not_allowed"
    assert exc_info.value.transient is False


def test_policy_refresh_collects_reviewed_allowlisted_endpoint(
    db_session_factory: sessionmaker[Session],
) -> None:
    content = b"<html><body>reviewed policy source</body></html>"
    client = RegisteredFakeHttpClient(
        [
            RegisteredFakeResponse(content=b"", status_code=404),
            RegisteredFakeResponse(content=content),
        ]
    )
    with db_session_factory.begin() as session:
        _add_market_endpoint(
            session,
            endpoint_id="council_home",
            collection_enabled=True,
            lifecycle_status="verified",
            adapter_key=REGISTERED_STATIC_HTTP_ADAPTER_KEY,
        )

    with db_session_factory() as session:
        result = execute_fixed_workstation_job(
            "policy_research_refresh",
            session=session,
            registered_source_client=client,
            now=datetime(2026, 6, 8, 9, 0, tzinfo=SHANGHAI),
        )

    with db_session_factory() as session:
        run = session.scalar(select(MarketIngestionRun))

    assert result.status == "succeeded"
    assert result.summary["request_count"] == 2
    endpoints = cast(list[dict[str, object]], result.summary["endpoints"])
    assert endpoints[0]["endpoint_id"] == "council_home"
    assert endpoints[0]["item_status"] == "inserted"
    assert endpoints[0]["robots_status"] == "missing"
    assert [call["url"] for call in client.calls] == [
        "https://example.test/robots.txt",
        "https://example.test/",
    ]
    assert run is not None
    assert run.adapter_key == REGISTERED_STATIC_HTTP_ADAPTER_KEY
    assert run.status == "succeeded"


def test_daily_brief_worker_uses_embedding_client_and_fallback(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        result = execute_fixed_workstation_job(
            "daily_intelligence_brief",
            session=session,
            embedding_client=cast(EmbeddingClient, HashEmbeddingClient()),
            deepseek_client=FailingDeepSeekClient(),
            now=datetime(2026, 6, 2, 8, 30, tzinfo=SHANGHAI),
        )

    assert result.status == "succeeded"
    assert result.summary["target_date"] == "2026-06-02"
    assert result.summary["human_review_status"] == "pending_review"
    assert result.summary["llm_used"] is False


def test_weather_refresh_keeps_enabled_reference_point_unverified(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        session.add(
            WeatherLocation(
                location_id="demo_hydro_a_reference",
                name="Demo Hydro A public reference point",
                latitude=30.0,
                longitude=110.0,
                timezone="Asia/Shanghai",
                data_mode="public_derived",
                collection_enabled=True,
                verification_status="unverified_analysis_input",
                source_url="https://api.open-meteo.com/v1/forecast",
                notes="Not a verified station sensor.",
            )
        )
    times = [f"2026-06-{1 + hour // 24:02d}T{hour % 24:02d}:00" for hour in range(72)]
    payload: dict[str, object] = {
        "timezone": "Asia/Shanghai",
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "C",
            "precipitation": "mm",
            "rain": "mm",
            "weather_code": "wmo code",
            "cloud_cover": "%",
            "wind_speed_10m": "km/h",
        },
        "hourly": {
            "time": times,
            "temperature_2m": [22.0] * 72,
            "precipitation": [1.0] * 72,
            "rain": [0.5] * 72,
            "weather_code": [1] * 72,
            "cloud_cover": [50] * 72,
            "wind_speed_10m": [5.0] * 72,
        },
    }
    with db_session_factory() as session:
        result = execute_fixed_workstation_job(
            "weather_refresh",
            session=session,
            store=MemoryBlobStore(),
            open_meteo_client=build_client(payload),
        )
    with db_session_factory() as session:
        snapshot = session.scalar(select(WeatherFeatureSnapshot))

    assert result.status == "succeeded"
    locations = cast(list[dict[str, object]], result.summary["locations"])
    assert locations[0]["verification_status"] == "unverified_analysis_input"
    assert snapshot is not None
    assert snapshot.human_review_status == "pending_review"


def test_bench_refresh_preserves_one_d2_zip_and_imports_five_research_regions(
    db_session_factory: sessionmaker[Session],
) -> None:
    content = _make_daily_archive(interval_count=288, region_ids=BENCH_REGIONS)
    http_session = FakeSession([FakeResponse(content=content)])
    store = MemoryBlobStore()
    bench_client = BenchDispatchClient(
        timeout_seconds=3,
        max_retries=0,
        retry_backoff_seconds=0,
        session=http_session,
    )

    with db_session_factory() as session:
        result = execute_fixed_workstation_job(
            "bench_dispatch_research",
            session=session,
            store=store,
            bench_dispatch_client=bench_client,
            now=datetime(2026, 6, 2, 9, 30, tzinfo=SHANGHAI),
        )
    with db_session_factory() as session:
        raw_object = session.scalar(select(RawObject))
        datasets = list(session.scalars(select(ForecastResearchDataset)))
        raw_count = session.scalar(select(func.count()).select_from(RawObject))

    assert result.status == "succeeded"
    assert result.summary["report_filename"] == "PUBLIC_DISPATCHIS_20260531.zip"
    assert result.summary["research_only"] is True
    assert raw_object is not None
    assert raw_count == 1
    assert store.get(object_key=raw_object.object_key) == content
    assert {dataset.region_code for dataset in datasets} == {
        f"BENCH_NEM_{region}" for region in BENCH_REGIONS
    }
    assert {dataset.usage_scope for dataset in datasets} == {"research_only"}
    assert len(http_session.calls) == 1


def test_bench_refresh_classifies_blob_store_failure_as_transient(
    db_session_factory: sessionmaker[Session],
) -> None:
    class FailingStore:
        bucket_name = "test-raw"

        def put(self, *, object_key: str, content: bytes, media_type: str) -> None:
            del object_key, content, media_type
            raise BlobStoreError("MinIO unavailable.")

        def get(self, *, object_key: str) -> bytes:
            raise AssertionError(f"Unexpected read for {object_key}.")

    content = _make_daily_archive(interval_count=288, region_ids=BENCH_REGIONS)
    bench_client = BenchDispatchClient(
        timeout_seconds=3,
        max_retries=0,
        retry_backoff_seconds=0,
        session=FakeSession([FakeResponse(content=content)]),
    )

    with db_session_factory() as session:
        with pytest.raises(FixedJobExecutionError) as exc_info:
            execute_fixed_workstation_job(
                "bench_dispatch_research",
                session=session,
                store=FailingStore(),
                bench_dispatch_client=bench_client,
                now=datetime(2026, 6, 2, 9, 30, tzinfo=SHANGHAI),
            )

    assert exc_info.value.code == "workstation_storage_error"
    assert exc_info.value.transient is True
