from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.adapters.bench_dispatch import (
    BENCH_NEM_REGION_IDS,
    BenchDispatchClient,
)
from backend.app.adapters.open_meteo import OpenMeteoClient
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import AppError
from backend.app.repositories.market import list_market_endpoints
from backend.app.repositories.weather import list_collection_enabled_weather_locations
from backend.app.schemas.intelligence import IntelligenceBriefGenerateRequest
from backend.app.schemas.weather import OpenMeteoForecastIngestRequest
from backend.app.services.deepseek import DeepSeekClient, get_deepseek_client
from backend.app.services.demo_seed import seed_demo_research_workspace
from backend.app.services.embeddings import EmbeddingClient, get_embedding_client
from backend.app.services.forecasting import (
    get_bench_dispatch_client,
    import_fetched_bench_dispatch_benchmarks,
)
from backend.app.services.intelligence import generate_intelligence_brief
from backend.app.services.operations import is_mainland_workday, preserve_raw_object
from backend.app.services.registered_source_collector import (
    REGISTERED_STATIC_HTTP_ADAPTER_KEY,
    RegisteredSourceCollectionError,
    RegisteredSourceHttpClient,
    collect_registered_source_endpoint,
)
from backend.app.services.weather import get_open_meteo_client, ingest_open_meteo_forecast
from backend.app.storage.blob_store import BlobStore, BlobStoreError, MinioBlobStore

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("Asia/Shanghai")
BENCH_REGIONS = tuple(sorted(BENCH_NEM_REGION_IDS))
POLICY_RESEARCH_ENDPOINT_IDS = frozenset(
    {
        "southern_regulator_downloads",
        "council_home",
        "association_home",
        "institute_home",
    }
)
POLICY_RESEARCH_ADAPTER_KEYS: frozenset[str] = frozenset({REGISTERED_STATIC_HTTP_ADAPTER_KEY})
TRANSIENT_ERROR_CODES = frozenset(
    {
        "bench_dispatch_network_error",
        "open_meteo_network_error",
        "workstation_storage_error",
        "registered_source_network_error",
        "registered_source_timeout",
        "registered_source_robots_unavailable",
    }
)


@dataclass(frozen=True)
class FixedJobResult:
    status: Literal["succeeded", "skipped"]
    summary: dict[str, object]


class FixedJobExecutionError(RuntimeError):
    def __init__(self, *, code: str, message: str, transient: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.transient = transient


@dataclass(frozen=True)
class WorkstationJobContext:
    session: Session
    settings: Settings
    store: BlobStore | None
    open_meteo_client: OpenMeteoClient | None
    bench_dispatch_client: BenchDispatchClient | None
    registered_source_client: RegisteredSourceHttpClient | None
    deepseek_client: DeepSeekClient | None
    embedding_client: EmbeddingClient | None
    now: datetime


@dataclass(frozen=True)
class WeatherReferencePoint:
    location_id: str
    name: str
    latitude: float
    longitude: float
    timezone: str
    verification_status: str


FixedJobHandler = Callable[[WorkstationJobContext], FixedJobResult]


def execute_fixed_workstation_job(
    job_key: str,
    *,
    session: Session,
    settings: Settings | None = None,
    store: BlobStore | None = None,
    open_meteo_client: OpenMeteoClient | None = None,
    bench_dispatch_client: BenchDispatchClient | None = None,
    registered_source_client: RegisteredSourceHttpClient | None = None,
    deepseek_client: DeepSeekClient | None = None,
    embedding_client: EmbeddingClient | None = None,
    now: datetime | None = None,
) -> FixedJobResult:
    handler = FIXED_JOB_HANDLERS.get(job_key)
    if handler is None:
        raise FixedJobExecutionError(
            code="workstation_job_handler_not_registered",
            message=f"Fixed workstation job handler '{job_key}' is not registered.",
            transient=False,
        )
    resolved_settings = settings or get_settings()
    context = WorkstationJobContext(
        session=session,
        settings=resolved_settings,
        store=store,
        open_meteo_client=open_meteo_client,
        bench_dispatch_client=bench_dispatch_client,
        registered_source_client=registered_source_client,
        deepseek_client=deepseek_client,
        embedding_client=embedding_client,
        now=now or datetime.now(tz=TIMEZONE),
    )
    try:
        return handler(context)
    except FixedJobExecutionError:
        raise
    except AppError as exc:
        raise FixedJobExecutionError(
            code=exc.code,
            message=exc.message,
            transient=exc.code in TRANSIENT_ERROR_CODES,
        ) from exc
    except OSError as exc:
        raise FixedJobExecutionError(
            code="workstation_storage_error",
            message=f"Local workstation storage failed: {type(exc).__name__}.",
            transient=True,
        ) from exc
    except BlobStoreError as exc:
        raise FixedJobExecutionError(
            code="workstation_storage_error",
            message=str(exc),
            transient=True,
        ) from exc


def _refresh_weather(context: WorkstationJobContext) -> FixedJobResult:
    configured_locations = [
        WeatherReferencePoint(
            location_id=location.location_id,
            name=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
            timezone=location.timezone,
            verification_status=location.verification_status,
        )
        for location in list_collection_enabled_weather_locations(context.session)
    ]
    context.session.rollback()
    if not configured_locations:
        return FixedJobResult(
            status="skipped",
            summary={
                "message": "No enabled public weather reference point is registered.",
                "request_count": 0,
            },
        )
    ingestions: list[dict[str, object]] = []
    client = context.open_meteo_client or get_open_meteo_client()
    for location in configured_locations:
        response = ingest_open_meteo_forecast(
            OpenMeteoForecastIngestRequest(
                location_id=location.location_id,
                location_name=location.name,
                latitude=location.latitude,
                longitude=location.longitude,
                timezone=location.timezone,
            ),
            session=context.session,
            client=client,
        )
        ingestions.append(
            {
                "location_id": response.location_id,
                "ingestion_run_id": response.ingestion_run_id,
                "feature_snapshot_id": response.feature_snapshot_id,
                "verification_status": location.verification_status,
                "quality_status": response.quality_status,
            }
        )
    return FixedJobResult(
        status="succeeded",
        summary={
            "message": "Refreshed enabled public weather reference points.",
            "request_count": len(ingestions),
            "locations": ingestions,
        },
    )


def _refresh_policy_research(context: WorkstationJobContext) -> FixedJobResult:
    endpoints = [
        endpoint
        for endpoint in list_market_endpoints(context.session, source_id=None)
        if endpoint.endpoint_id in POLICY_RESEARCH_ENDPOINT_IDS and endpoint.collection_enabled
    ]
    for endpoint in endpoints:
        context.session.expunge(endpoint)
    context.session.rollback()
    if not endpoints:
        return FixedJobResult(
            status="skipped",
            summary={
                "message": "No reviewed allowlisted policy collection endpoint is enabled.",
                "request_count": 0,
            },
        )
    blocked_endpoint_ids = [
        endpoint.endpoint_id
        for endpoint in endpoints
        if endpoint.access_mode == "manual_submission_only"
        or endpoint.lifecycle_status.startswith("blocked_")
    ]
    if blocked_endpoint_ids:
        raise FixedJobExecutionError(
            code="policy_collection_endpoint_not_allowed",
            message=(
                "Policy collection endpoints are permanently manual-only or blocked: "
                + ", ".join(blocked_endpoint_ids)
                + "."
            ),
            transient=False,
        )
    unreviewed_endpoint_ids = [
        endpoint.endpoint_id
        for endpoint in endpoints
        if endpoint.adapter_key is None or endpoint.adapter_key not in POLICY_RESEARCH_ADAPTER_KEYS
    ]
    if unreviewed_endpoint_ids:
        raise FixedJobExecutionError(
            code="policy_collection_adapter_not_registered",
            message=(
                "Enabled policy collection endpoints do not have reviewed fixed adapters: "
                + ", ".join(unreviewed_endpoint_ids)
                + "."
            ),
            transient=False,
        )
    collection_results: list[dict[str, object]] = []
    request_count = 0
    for endpoint in endpoints:
        try:
            result = collect_registered_source_endpoint(
                endpoint,
                session=context.session,
                client=context.registered_source_client,
                now=context.now,
                sleep=lambda _seconds: None,
            )
        except RegisteredSourceCollectionError as exc:
            raise FixedJobExecutionError(
                code=exc.code,
                message=exc.message,
                transient=exc.transient,
            ) from exc
        request_count += result.request_count
        collection_results.append(
            {
                "endpoint_id": result.endpoint_id,
                "ingestion_run_id": result.ingestion_run_id,
                "artifact_id": result.artifact_id,
                "item_status": result.item_status,
                "duplicate_artifact": result.duplicate_artifact,
                "content_sha256": result.content_sha256,
                "quality_status": result.quality_status,
                "quality_issue_count": result.quality_issue_count,
                "media_type": result.media_type,
                "byte_length": result.byte_length,
                "robots_status": result.robots_status,
            }
        )
    return FixedJobResult(
        status="succeeded",
        summary={
            "message": "Collected reviewed allowlisted policy research endpoints.",
            "request_count": request_count,
            "endpoints": collection_results,
        },
    )


def _archive_bench_dispatch(context: WorkstationJobContext) -> FixedJobResult:
    archive_date = context.now.astimezone(TIMEZONE).date() - timedelta(days=2)
    report_filename = f"PUBLIC_DISPATCHIS_{archive_date:%Y%m%d}.zip"
    bench_dispatch_client = context.bench_dispatch_client or get_bench_dispatch_client()
    archive = bench_dispatch_client.fetch_daily_archive(
        report_filename,
        fetched_at=context.now,
    )
    raw_object, duplicate = preserve_raw_object(
        content=archive.zip_content,
        media_type=archive.content_type or "application/zip",
        data_mode="public_observed",
        source_url=archive.source_url,
        metadata={
            "provider": "bench",
            "report_filename": archive.report_filename,
            "last_modified": archive.last_modified,
            "zip_sha256": archive.zip_sha256,
            "usage_scope": "research_only",
        },
        store=context.store or MinioBlobStore(context.settings),
        session=context.session,
    )
    raw_metadata = [
        {
            "raw_object_id": raw_object.raw_object_id,
            "object_key": raw_object.object_key,
            "content_sha256": raw_object.content_sha256,
            "duplicate": duplicate,
        }
    ]
    imported = import_fetched_bench_dispatch_benchmarks(
        (archive,),
        region_ids=BENCH_REGIONS,
        raw_object_metadata=raw_metadata,
        session=context.session,
    )
    return FixedJobResult(
        status="succeeded",
        summary={
            "message": "Archived fixed official BENCH Dispatch D-2 benchmark.",
            "report_filename": report_filename,
            "raw_object_id": raw_object.raw_object_id,
            "raw_object_duplicate": duplicate,
            "research_only": True,
            "datasets": {
                region_id: {
                    "dataset_id": response.dataset_id,
                    "status": response.status,
                    "usage_scope": response.usage_scope,
                }
                for region_id, response in imported.items()
            },
        },
    )


def _generate_daily_brief(context: WorkstationJobContext) -> FixedJobResult:
    target_date = context.now.astimezone(TIMEZONE).date()
    if not is_mainland_workday(target_date, session=context.session):
        return FixedJobResult(
            status="skipped",
            summary={
                "message": "Daily intelligence brief is generated only on mainland workdays.",
                "target_date": target_date.isoformat(),
            },
        )
    brief = generate_intelligence_brief(
        IntelligenceBriefGenerateRequest(target_date=target_date),
        session=context.session,
        embedding_client=context.embedding_client or get_embedding_client(),
        deepseek_client=context.deepseek_client or get_deepseek_client(),
    )
    return FixedJobResult(
        status="succeeded",
        summary={
            "message": "Generated daily intelligence brief for operator review.",
            "brief_id": brief.brief_id,
            "target_date": brief.target_date.isoformat(),
            "human_review_status": brief.human_review_status,
            "llm_used": brief.llm_used,
        },
    )


def _seed_demo_research_workspace(context: WorkstationJobContext) -> FixedJobResult:
    summary = seed_demo_research_workspace(session=context.session)
    return FixedJobResult(
        status="succeeded",
        summary={
            "message": "Seeded local deterministic v0.1 RC demo data.",
            **summary.model_dump(mode="json"),
        },
    )


FIXED_JOB_HANDLERS: dict[str, FixedJobHandler] = {
    "weather_refresh": _refresh_weather,
    "policy_research_refresh": _refresh_policy_research,
    "bench_dispatch_research": _archive_bench_dispatch,
    "daily_intelligence_brief": _generate_daily_brief,
    "demo_research_workspace_seed": _seed_demo_research_workspace,
}
