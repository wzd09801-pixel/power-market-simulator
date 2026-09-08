from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.forecasting.baselines import (
    FEATURE_VERSION,
    INTERVALS_PER_DAY,
    MODEL_VERSION,
    ResearchPricePoint,
    run_research_backtest,
)
from backend.app.models.forecasting import (
    ForecastResearchDataset,
    ForecastResearchDatasetImportRun,
    ForecastResearchModelRun,
    ForecastResearchPrediction,
    ForecastResearchPricePoint,
)
from backend.app.models.intelligence import IntelligenceBrief
from backend.app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
from backend.app.models.market import (
    MarketDataSource,
    MarketIngestionRun,
    MarketIngestionRunItem,
    MarketRawArtifact,
    MarketSourceEndpoint,
)
from backend.app.models.operations import RawObject
from backend.app.models.recommendation import (
    AuditEvent,
    FeatureSnapshot,
    RecommendationDecision,
    RecommendationDecisionFeedback,
    RecommendationRun,
)
from backend.app.models.weather import (
    WeatherFeatureSnapshot,
    WeatherIngestionRun,
    WeatherLocation,
    WeatherRawPayload,
)
from backend.app.schemas.system import DemoSeedSummary
from backend.app.services.weather_features import FEATURE_VERSION as WEATHER_FEATURE_VERSION

TIMEZONE = ZoneInfo("Asia/Shanghai")
DEMO_SEED_KEY = "mvp_rc_demo_v1"
DEMO_GENERATED_AT = datetime(2026, 6, 2, 8, 30, tzinfo=TIMEZONE)
DEMO_TARGET_DATE = date(2026, 6, 2)
DEMO_FORECAST_START = datetime(2026, 6, 2, 0, 0, tzinfo=TIMEZONE)

DEMO_IDS = {
    "weather_location": "demo_rc_demo_hydro_reference",
    "weather_raw_payload": "demo_rc_weather_raw_payload",
    "weather_ingestion_run": "demo_rc_weather_ingestion",
    "weather_feature_snapshot": "demo_rc_weather_features",
    "market_source": "demo_rc_policy_source",
    "market_endpoint": "demo_rc_policy_endpoint",
    "market_artifact": "demo_rc_policy_artifact",
    "market_ingestion_run": "demo_rc_market_ingestion",
    "market_ingestion_item": "demo_rc_market_item",
    "raw_object": "demo_rc_policy_raw",
    "knowledge_document": "demo_rc_policy_document",
    "knowledge_version": "demo_rc_policy_version",
    "knowledge_chunk": "demo_rc_policy_chunk",
    "brief": "demo_rc_daily_brief",
    "recommendation_snapshot": "demo_rc_recommendation_snapshot",
    "recommendation": "demo_rc_recommendation",
    "recommendation_decision": "demo_rc_decision",
    "recommendation_feedback": "demo_rc_feedback",
    "recommendation_audit_generated": "demo_rc_audit_recommendation_generated",
    "recommendation_audit_decision": "demo_rc_audit_decision",
    "recommendation_audit_feedback": "demo_rc_audit_feedback",
    "forecast_dataset": "demo_rc_forecast_dataset",
    "forecast_import_run": "demo_rc_forecast_import",
    "forecast_model_run": "demo_rc_forecast_model_seasonal",
}


def seed_demo_research_workspace(*, session: Session) -> DemoSeedSummary:
    with session.begin():
        created_flags = {
            "weather_snapshot": _ensure_weather_demo(session),
            "market_artifact": _ensure_market_demo(session),
            "policy_document": _ensure_policy_document_demo(session),
            "brief": _ensure_brief_demo(session),
            "recommendation": _ensure_recommendation_demo(session),
            "forecast_dataset": _ensure_forecast_demo(session),
        }

    return DemoSeedSummary(
        seed_key=DEMO_SEED_KEY,
        created=created_flags,
        object_ids={
            "weather_feature_snapshot_id": DEMO_IDS["weather_feature_snapshot"],
            "market_artifact_id": DEMO_IDS["market_artifact"],
            "policy_document_id": DEMO_IDS["knowledge_document"],
            "brief_id": DEMO_IDS["brief"],
            "recommendation_id": DEMO_IDS["recommendation"],
            "recommendation_decision_id": DEMO_IDS["recommendation_decision"],
            "forecast_dataset_id": DEMO_IDS["forecast_dataset"],
            "forecast_model_run_id": DEMO_IDS["forecast_model_run"],
        },
        data_modes={
            "weather": "public_derived",
            "market_artifact": "user_uploaded",
            "policy_document": "user_uploaded",
            "brief": "scenario_simulated",
            "recommendation": "scenario_simulated",
            "decision_feedback": "user_uploaded",
            "forecast_dataset": "scenario_simulated",
            "forecast_model_run": "public_derived",
        },
        research_only=True,
        no_auto_trading=True,
    )


def demo_seed_presence(session: Session) -> dict[str, bool]:
    return {
        "weather_snapshot": session.get(
            WeatherFeatureSnapshot, DEMO_IDS["weather_feature_snapshot"]
        )
        is not None,
        "market_artifact": session.get(MarketRawArtifact, DEMO_IDS["market_artifact"]) is not None,
        "policy_document": session.get(KnowledgeDocument, DEMO_IDS["knowledge_document"])
        is not None,
        "brief": session.get(IntelligenceBrief, DEMO_IDS["brief"]) is not None,
        "recommendation": session.get(RecommendationRun, DEMO_IDS["recommendation"]) is not None,
        "decision_feedback": session.get(
            RecommendationDecisionFeedback, DEMO_IDS["recommendation_feedback"]
        )
        is not None,
        "forecast_dataset": session.get(ForecastResearchDataset, DEMO_IDS["forecast_dataset"])
        is not None,
        "forecast_model_run": session.get(ForecastResearchModelRun, DEMO_IDS["forecast_model_run"])
        is not None,
    }


def _ensure_weather_demo(session: Session) -> bool:
    created = False
    if session.get(WeatherLocation, DEMO_IDS["weather_location"]) is None:
        session.add(
            WeatherLocation(
                location_id=DEMO_IDS["weather_location"],
                name="Demo Demo Hydro A public reference point",
                latitude=30.0,
                longitude=110.0,
                timezone="Asia/Shanghai",
                data_mode="public_derived",
                collection_enabled=False,
                verification_status="unverified_analysis_input",
                source_url="https://open-meteo.com/",
                notes="Demo reference point for RC seed only; not a station sensor.",
            )
        )
        created = True
        session.flush()
    if session.get(WeatherRawPayload, DEMO_IDS["weather_raw_payload"]) is None:
        payload = {
            "seed_key": DEMO_SEED_KEY,
            "location_id": DEMO_IDS["weather_location"],
            "note": "Deterministic local demo payload; no external request was made.",
        }
        session.add(
            WeatherRawPayload(
                raw_payload_id=DEMO_IDS["weather_raw_payload"],
                provider="demo_seed",
                location_id=DEMO_IDS["weather_location"],
                fetched_at=DEMO_GENERATED_AT,
                request_url="demo://weather/open-meteo-reference",
                request_params_json={"seed_key": DEMO_SEED_KEY},
                payload_json=payload,
                raw_content=_json(payload),
                content_hash=_hash_json(payload),
                data_mode="public_derived",
                quality_flag="valid",
            )
        )
        created = True
        session.flush()
    if session.get(WeatherIngestionRun, DEMO_IDS["weather_ingestion_run"]) is None:
        session.add(
            WeatherIngestionRun(
                ingestion_run_id=DEMO_IDS["weather_ingestion_run"],
                provider="demo_seed",
                location_id=DEMO_IDS["weather_location"],
                started_at=DEMO_GENERATED_AT,
                completed_at=DEMO_GENERATED_AT + timedelta(seconds=1),
                status="succeeded",
                request_url="demo://weather/open-meteo-reference",
                raw_payload_id=DEMO_IDS["weather_raw_payload"],
                records_received=0,
                records_inserted=0,
                duplicate_records=0,
                quality_status="valid",
                quality_issue_count=0,
            )
        )
        created = True
        session.flush()
    if session.get(WeatherFeatureSnapshot, DEMO_IDS["weather_feature_snapshot"]) is None:
        features = {
            "precipitation_sum_24h": 8.4,
            "precipitation_sum_72h": 26.2,
            "rain_sum_24h": 7.9,
            "rain_sum_72h": 24.6,
            "temperature_mean_24h": 23.4,
            "temperature_min_24h": 19.8,
            "temperature_max_24h": 28.1,
        }
        evidence = [
            {
                "source": "demo_seed",
                "source_type": "public_weather_reference_demo",
                "data_mode": "public_derived",
                "field": key,
                "value": value,
                "unit": "derived_demo_unit",
                "raw_payload_id": DEMO_IDS["weather_raw_payload"],
                "note": "Demo feature derived from deterministic local fixture.",
            }
            for key, value in features.items()
        ]
        session.add(
            WeatherFeatureSnapshot(
                feature_snapshot_id=DEMO_IDS["weather_feature_snapshot"],
                ingestion_run_id=DEMO_IDS["weather_ingestion_run"],
                raw_payload_id=DEMO_IDS["weather_raw_payload"],
                provider="demo_seed",
                location_id=DEMO_IDS["weather_location"],
                generated_at=DEMO_GENERATED_AT,
                forecast_start=DEMO_FORECAST_START,
                feature_version=WEATHER_FEATURE_VERSION,
                quality_status="valid",
                human_review_status="approved",
                features_json=features,
                evidence_json=evidence,
                missing_data_warnings_json=[
                    "Demo weather features are public-derived and not station sensor data."
                ],
                content_hash=_hash_json({"seed": DEMO_SEED_KEY, "features": features}),
                data_mode="public_derived",
            )
        )
        created = True
    return created


def _ensure_market_demo(session: Session) -> bool:
    created = False
    if session.get(MarketDataSource, DEMO_IDS["market_source"]) is None:
        session.add(
            MarketDataSource(
                source_id=DEMO_IDS["market_source"],
                name="Demo local policy source",
                operator_name="Local RC seed",
                official_url="https://example.invalid/demo-policy",
                market_scope="demo_research",
                notes="Local demo source only; not an automated collection endpoint.",
                data_mode="user_uploaded",
                trust_tier="demo_fixture",
                attribution_text="Demo fixture for local research workstation.",
                collection_permission_note="No network collection is performed.",
            )
        )
        created = True
        session.flush()
    if session.get(MarketSourceEndpoint, DEMO_IDS["market_endpoint"]) is None:
        session.add(
            MarketSourceEndpoint(
                endpoint_id=DEMO_IDS["market_endpoint"],
                source_id=DEMO_IDS["market_source"],
                name="Demo manual policy artifact endpoint",
                canonical_url="https://example.invalid/demo-policy",
                endpoint_kind="policy_document",
                allowed_domains_json=["example.invalid"],
                visibility_scope="public_demo",
                access_mode="manual_submission_only",
                lifecycle_status="disabled",
                content_formats_json=["text/html"],
                data_granularity="document",
                adapter_key=None,
                parser_key=None,
                parser_version=None,
                health_check_enabled=False,
                manual_submission_enabled=True,
                collection_enabled=False,
                cadence=None,
                notes="Demo endpoint remains disabled and manual-only.",
            )
        )
        created = True
        session.flush()
    if session.get(MarketIngestionRun, DEMO_IDS["market_ingestion_run"]) is None:
        session.add(
            MarketIngestionRun(
                ingestion_run_id=DEMO_IDS["market_ingestion_run"],
                source_id=DEMO_IDS["market_source"],
                endpoint_id=DEMO_IDS["market_endpoint"],
                trigger_mode="demo_seed",
                adapter_key=None,
                adapter_version=None,
                started_at=DEMO_GENERATED_AT,
                completed_at=DEMO_GENERATED_AT + timedelta(seconds=1),
                status="succeeded",
                items_received=1,
                items_inserted=1,
                duplicate_items=0,
                rejected_items=0,
                quality_status="valid",
                quality_issue_count=0,
            )
        )
        created = True
    artifact_text = _demo_policy_text()
    artifact_hash = _hash_text(artifact_text)
    if session.get(MarketRawArtifact, DEMO_IDS["market_artifact"]) is None:
        session.add(
            MarketRawArtifact(
                artifact_id=DEMO_IDS["market_artifact"],
                source_id=DEMO_IDS["market_source"],
                endpoint_id=DEMO_IDS["market_endpoint"],
                source_url="https://example.invalid/demo-policy",
                title="Demo local market policy artifact",
                media_type="text/html",
                storage_backend="inline",
                inline_text=artifact_text,
                object_key=None,
                content_sha256=artifact_hash,
                byte_length=len(artifact_text.encode("utf-8")),
                published_at=DEMO_GENERATED_AT,
                captured_at=DEMO_GENERATED_AT,
                ingestion_method="demo_seed",
                transport_security_status="not_applicable_local_seed",
                human_review_status="pending_review",
                data_mode="user_uploaded",
            )
        )
        created = True
    session.flush()
    if session.get(MarketIngestionRunItem, DEMO_IDS["market_ingestion_item"]) is None:
        session.add(
            MarketIngestionRunItem(
                ingestion_run_item_id=DEMO_IDS["market_ingestion_item"],
                ingestion_run_id=DEMO_IDS["market_ingestion_run"],
                artifact_id=DEMO_IDS["market_artifact"],
                source_url="https://example.invalid/demo-policy",
                item_status="accepted",
            )
        )
        created = True
    return created


def _ensure_policy_document_demo(session: Session) -> bool:
    created = False
    parent_created = False
    text = _demo_policy_text()
    digest = _hash_text(text)
    if session.get(RawObject, DEMO_IDS["raw_object"]) is None:
        session.add(
            RawObject(
                raw_object_id=DEMO_IDS["raw_object"],
                content_sha256=digest,
                storage_backend="inline_demo",
                bucket_name="local-demo",
                object_key=f"demo://raw/{DEMO_IDS['raw_object']}",
                media_type="text/html",
                byte_length=len(text.encode("utf-8")),
                source_url="https://example.invalid/demo-policy",
                captured_at=DEMO_GENERATED_AT,
                metadata_json={
                    "seed_key": DEMO_SEED_KEY,
                    "market_artifact_imports": [
                        {
                            "artifact_id": DEMO_IDS["market_artifact"],
                            "source_id": DEMO_IDS["market_source"],
                            "endpoint_id": DEMO_IDS["market_endpoint"],
                            "source_url": "https://example.invalid/demo-policy",
                        }
                    ],
                },
                data_mode="user_uploaded",
            )
        )
        created = True
        parent_created = True
    if session.get(KnowledgeDocument, DEMO_IDS["knowledge_document"]) is None:
        session.add(
            KnowledgeDocument(
                document_id=DEMO_IDS["knowledge_document"],
                title="Demo policy note for RC checklist",
                document_layer="official_policy",
                trust_tier="demo_fixture",
                source_name="Demo local policy source",
                source_url="https://example.invalid/demo-policy",
                media_type="text/html",
                published_at=DEMO_GENERATED_AT,
                effective_at=DEMO_GENERATED_AT,
                captured_at=DEMO_GENERATED_AT,
                external_processing_allowed=False,
                human_review_status="pending_review",
                data_mode="user_uploaded",
            )
        )
        created = True
        parent_created = True
    if parent_created:
        session.flush()
    if session.get(KnowledgeDocumentVersion, DEMO_IDS["knowledge_version"]) is None:
        session.add(
            KnowledgeDocumentVersion(
                version_id=DEMO_IDS["knowledge_version"],
                document_id=DEMO_IDS["knowledge_document"],
                raw_object_id=DEMO_IDS["raw_object"],
                version_number=1,
                content_sha256=digest,
                parser_key="demo_html_text",
                parsed_text=text,
            )
        )
        created = True
        session.flush()
    if session.get(KnowledgeChunk, DEMO_IDS["knowledge_chunk"]) is None:
        session.add(
            KnowledgeChunk(
                chunk_id=DEMO_IDS["knowledge_chunk"],
                version_id=DEMO_IDS["knowledge_version"],
                ordinal=0,
                section_heading="Demo policy watch",
                content=text,
                character_count=len(text),
                content_sha256=digest,
                embedding=None,
                embedding_model=None,
            )
        )
        created = True
    return created


def _ensure_brief_demo(session: Session) -> bool:
    if session.get(IntelligenceBrief, DEMO_IDS["brief"]) is not None:
        return False
    citation = _demo_citation()
    policy_watch_item = {
        "watch_id": DEMO_IDS["knowledge_chunk"],
        "title": "Demo policy note for RC checklist",
        "observation": "Official policy evidence for operator review.",
        "excerpt": "Demo local policy note for RC readiness and citation checks.",
        "citation": citation,
        "captured_at": DEMO_GENERATED_AT.isoformat(),
        "source_role": "official_policy",
        "external_processing_allowed": False,
        "score": 0.82,
    }
    session.add(
        IntelligenceBrief(
            brief_id=DEMO_IDS["brief"],
            target_date=DEMO_TARGET_DATE,
            generated_at=DEMO_GENERATED_AT,
            status="generated",
            human_review_status="pending_review",
            risk_level="medium",
            confidence_score=0.52,
            deterministic_facts_json={
                "seed_key": DEMO_SEED_KEY,
                "weather_snapshot_count": 1,
                "knowledge_document_count": 1,
                "policy_watch": {
                    "item_count": 1,
                    "excluded_restricted_chunks": 1,
                    "local_only": True,
                    "items": [policy_watch_item],
                },
            },
            narrative_json={
                "summary": "Demo deterministic brief generated for RC operator review.",
                "risks": [
                    "Demo data is not verified company operational data.",
                    "No automatic trading action is produced.",
                ],
                "policy_watch": [
                    {
                        "title": policy_watch_item["title"],
                        "source_name": citation["source_name"],
                        "external_processing_allowed": False,
                    }
                ],
            },
            citations_json=[citation],
            missing_information_json=[
                "Demo seed has no verified internal reservoir operation data."
            ],
            llm_used=False,
            llm_model=None,
            no_auto_trading=True,
        )
    )
    return True


def _ensure_recommendation_demo(session: Session) -> bool:
    created = False
    if session.get(FeatureSnapshot, DEMO_IDS["recommendation_snapshot"]) is None:
        evidence = [_scenario_evidence()]
        session.add(
            FeatureSnapshot(
                snapshot_id=DEMO_IDS["recommendation_snapshot"],
                created_at=DEMO_GENERATED_AT,
                trade_date=DEMO_TARGET_DATE,
                asset_id="demo_hydro_a",
                scenario_id="demo_hydro_a_normal_storage_normal_inflow_v1",
                data_mode="scenario_simulated",
                inputs_json={
                    "seed_key": DEMO_SEED_KEY,
                    "weather_feature_snapshot_id": DEMO_IDS["weather_feature_snapshot"],
                    "assumption": "Demo scenario calibrated from public information.",
                },
                evidence_json=evidence,
            )
        )
        created = True
        session.flush()
    if session.get(RecommendationRun, DEMO_IDS["recommendation"]) is None:
        content = _demo_recommendation_content()
        session.add(
            RecommendationRun(
                rec_id=DEMO_IDS["recommendation"],
                created_at=DEMO_GENERATED_AT,
                input_snapshot_id=DEMO_IDS["recommendation_snapshot"],
                trade_date=DEMO_TARGET_DATE,
                asset_id="demo_hydro_a",
                data_mode="scenario_simulated",
                scenario_id="demo_hydro_a_normal_storage_normal_inflow_v1",
                risk_level="medium",
                confidence=0.58,
                strategy_json=content,
                review_status="pending_review",
            )
        )
        session.add(
            AuditEvent(
                event_id=DEMO_IDS["recommendation_audit_generated"],
                event_type="recommendation_generated",
                created_at=DEMO_GENERATED_AT,
                actor="demo_seed",
                data_mode="scenario_simulated",
                payload_json={
                    "recommendation_id": DEMO_IDS["recommendation"],
                    "seed_key": DEMO_SEED_KEY,
                    "review_status": "pending_review",
                    "no_auto_trading": True,
                },
            )
        )
        created = True
        session.flush()
    if session.get(RecommendationDecision, DEMO_IDS["recommendation_decision"]) is None:
        audit_snapshot = {
            "recommendation_id": DEMO_IDS["recommendation"],
            "overall_status": "warning",
            "no_auto_trading": True,
            "human_check_required": True,
            "seed_key": DEMO_SEED_KEY,
        }
        session.add(
            RecommendationDecision(
                decision_id=DEMO_IDS["recommendation_decision"],
                recommendation_id=DEMO_IDS["recommendation"],
                created_at=DEMO_GENERATED_AT + timedelta(minutes=10),
                actor="local_operator",
                decision_status="deferred",
                selected_windows_json=["18:00-21:00"],
                note="Demo decision log for RC feedback loop; no trade was executed.",
                safety_boundary_acknowledged=True,
                no_auto_trading=True,
                audit_snapshot_json=audit_snapshot,
            )
        )
        session.add(
            AuditEvent(
                event_id=DEMO_IDS["recommendation_audit_decision"],
                event_type="recommendation_decision_recorded",
                created_at=DEMO_GENERATED_AT + timedelta(minutes=10),
                actor="local_operator",
                data_mode="user_uploaded",
                payload_json=audit_snapshot,
            )
        )
        created = True
        session.flush()
    if session.get(RecommendationDecisionFeedback, DEMO_IDS["recommendation_feedback"]) is None:
        session.add(
            RecommendationDecisionFeedback(
                feedback_id=DEMO_IDS["recommendation_feedback"],
                decision_id=DEMO_IDS["recommendation_decision"],
                recommendation_id=DEMO_IDS["recommendation"],
                created_at=DEMO_GENERATED_AT + timedelta(days=1),
                actor="local_operator",
                outcome_status="pending_observation",
                observed_at=DEMO_TARGET_DATE + timedelta(days=1),
                note="Demo follow-up remains pending observation.",
                data_mode="user_uploaded",
            )
        )
        session.add(
            AuditEvent(
                event_id=DEMO_IDS["recommendation_audit_feedback"],
                event_type="recommendation_decision_feedback_recorded",
                created_at=DEMO_GENERATED_AT + timedelta(days=1),
                actor="local_operator",
                data_mode="user_uploaded",
                payload_json={
                    "recommendation_id": DEMO_IDS["recommendation"],
                    "decision_id": DEMO_IDS["recommendation_decision"],
                    "feedback_id": DEMO_IDS["recommendation_feedback"],
                    "outcome_status": "pending_observation",
                    "seed_key": DEMO_SEED_KEY,
                },
            )
        )
        created = True
    return created


def _ensure_forecast_demo(session: Session) -> bool:
    created = False
    points = _forecast_points()
    payload = {
        "seed_key": DEMO_SEED_KEY,
        "name": "Demo RC 15-minute scenario research curve",
        "source_name": "Local RC seed",
        "source_url": "https://example.invalid/demo-forecast",
        "region_code": "DEMO_RC",
        "region_name": "Demo RC research region",
        "market_scope": "demo_forecast_research",
        "market_stage": "day_ahead",
        "price_scope": "regional_reference_price",
        "interval_minutes": 15,
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "price_unit": "CNY_per_MWh",
        "data_mode": "scenario_simulated",
        "usage_scope": "research_only",
        "notes": "Synthetic forecast research curve for RC checklist; not observed market data.",
        "points": [
            {"interval_start": point.interval_start.isoformat(), "price": str(point.price)}
            for point in points
        ],
    }
    digest = _hash_json(payload)
    if session.get(ForecastResearchDataset, DEMO_IDS["forecast_dataset"]) is None:
        session.add(
            ForecastResearchDataset(
                dataset_id=DEMO_IDS["forecast_dataset"],
                name=str(payload["name"]),
                source_name=str(payload["source_name"]),
                source_url=str(payload["source_url"]),
                region_code=str(payload["region_code"]),
                region_name=str(payload["region_name"]),
                market_scope=str(payload["market_scope"]),
                market_stage=str(payload["market_stage"]),
                price_scope=str(payload["price_scope"]),
                interval_minutes=15,
                timezone=str(payload["timezone"]),
                currency=str(payload["currency"]),
                price_unit=str(payload["price_unit"]),
                data_mode="scenario_simulated",
                usage_scope="research_only",
                content_sha256=digest,
                raw_payload_json=payload,
                imported_at=DEMO_GENERATED_AT,
                quality_status="valid",
                quality_issue_count=0,
                normalized_point_count=len(points),
                trade_date_count=15,
                notes=str(payload["notes"]),
            )
        )
        created = True
        session.flush()
    if session.get(ForecastResearchDatasetImportRun, DEMO_IDS["forecast_import_run"]) is None:
        session.add(
            ForecastResearchDatasetImportRun(
                import_run_id=DEMO_IDS["forecast_import_run"],
                dataset_id=DEMO_IDS["forecast_dataset"],
                started_at=DEMO_GENERATED_AT,
                completed_at=DEMO_GENERATED_AT + timedelta(seconds=1),
                status="accepted",
                submitted_point_count=len(points),
                normalized_point_count=len(points),
                quality_status="valid",
                quality_issue_count=0,
                data_mode="scenario_simulated",
                error_code=None,
                error_message=None,
            )
        )
        created = True
    existing_point_count = session.scalar(
        select(ForecastResearchPricePoint)
        .where(ForecastResearchPricePoint.dataset_id == DEMO_IDS["forecast_dataset"])
        .limit(1)
    )
    if existing_point_count is None:
        for point in points:
            session.add(
                ForecastResearchPricePoint(
                    point_id=(
                        f"demo_rc_forecast_point_"
                        f"{point.trade_date.isoformat().replace('-', '')}_"
                        f"{point.interval_index:03d}"
                    ),
                    dataset_id=DEMO_IDS["forecast_dataset"],
                    interval_start=point.interval_start,
                    trade_date=point.trade_date,
                    interval_index=point.interval_index,
                    price=point.price,
                    data_mode="scenario_simulated",
                )
            )
        created = True
    if session.get(ForecastResearchModelRun, DEMO_IDS["forecast_model_run"]) is None:
        result = run_research_backtest(
            points,
            model_key="seasonal_naive",
            evaluation_days=3,
            lag_days=7,
            lookback_days=7,
        )
        session.add(
            ForecastResearchModelRun(
                model_run_id=DEMO_IDS["forecast_model_run"],
                dataset_id=DEMO_IDS["forecast_dataset"],
                model_key="seasonal_naive",
                model_version=MODEL_VERSION,
                feature_version=FEATURE_VERSION,
                started_at=DEMO_GENERATED_AT + timedelta(minutes=5),
                completed_at=DEMO_GENERATED_AT + timedelta(minutes=5, seconds=1),
                status="succeeded",
                registry_status="candidate",
                train_start=result.train_start,
                train_end=result.train_end,
                evaluation_start=result.evaluation_start,
                evaluation_end=result.evaluation_end,
                horizon_intervals=INTERVALS_PER_DAY,
                parameters_json=result.parameters,
                metrics_json=result.metrics,
                artifact_path=None,
                usage_scope="research_only",
                data_mode="public_derived",
            )
        )
        session.flush()
        for prediction in result.predictions:
            session.add(
                ForecastResearchPrediction(
                    prediction_id=(
                        f"demo_rc_prediction_"
                        f"{prediction.trade_date.isoformat().replace('-', '')}_"
                        f"{prediction.interval_index:03d}"
                    ),
                    model_run_id=DEMO_IDS["forecast_model_run"],
                    target_interval_start=prediction.target_interval_start,
                    trade_date=prediction.trade_date,
                    interval_index=prediction.interval_index,
                    actual_price=prediction.actual_price,
                    predicted_price=prediction.predicted_price,
                    data_mode="public_derived",
                )
            )
        created = True
    return created


def _forecast_points() -> list[ResearchPricePoint]:
    start = datetime(2026, 5, 18, 0, 0, tzinfo=TIMEZONE)
    points: list[ResearchPricePoint] = []
    for offset in range(15 * INTERVALS_PER_DAY):
        interval_start = start + timedelta(minutes=15 * offset)
        day_number = offset // INTERVALS_PER_DAY
        interval_index = offset % INTERVALS_PER_DAY + 1
        price = Decimal("320.0") + Decimal(day_number) + Decimal(interval_index) / Decimal("10")
        points.append(
            ResearchPricePoint(
                interval_start=interval_start,
                trade_date=interval_start.date(),
                interval_index=interval_index,
                price=price.quantize(Decimal("0.0001")),
            )
        )
    return points


def _demo_policy_text() -> str:
    return (
        "Demo local policy note for RC readiness. This fixture is for personal "
        "research workflow validation only. It is not fetched from the network, "
        "does not grant external model authorization, and must not be used as "
        "automatic trading evidence."
    )


def _demo_citation() -> dict[str, object]:
    return {
        "document_id": DEMO_IDS["knowledge_document"],
        "chunk_id": DEMO_IDS["knowledge_chunk"],
        "title": "Demo policy note for RC checklist",
        "source_name": "Demo local policy source",
        "source_url": "https://example.invalid/demo-policy",
        "document_layer": "official_policy",
        "data_mode": "user_uploaded",
    }


def _scenario_evidence() -> dict[str, object]:
    return {
        "source": "demo_seed",
        "source_type": "scenario_fixture",
        "data_mode": "scenario_simulated",
        "timestamp": DEMO_GENERATED_AT.isoformat(),
        "field": "available_energy_mwh",
        "value": 12000.0,
        "unit": "MWh",
        "confidence": 0.5,
        "url": None,
        "note": "Demo scenario value; not verified company operational data.",
    }


def _demo_recommendation_content() -> dict[str, object]:
    evidence = [
        _scenario_evidence(),
        {
            "source": "demo_seed",
            "source_type": "weather_feature_snapshot",
            "data_mode": "public_derived",
            "timestamp": DEMO_GENERATED_AT.isoformat(),
            "field": "weather_feature_snapshot_id",
            "value": DEMO_IDS["weather_feature_snapshot"],
            "unit": None,
            "confidence": 0.6,
            "url": None,
            "note": "Approved demo weather feature snapshot linked for audit visibility.",
        },
    ]
    return {
        "trade_date": DEMO_TARGET_DATE.isoformat(),
        "asset_id": "demo_hydro_a",
        "data_mode": "scenario_simulated",
        "scenario_id": "demo_hydro_a_normal_storage_normal_inflow_v1",
        "weather_feature_snapshot_id": DEMO_IDS["weather_feature_snapshot"],
        "horizon": "day_ahead_scenario",
        "market_view": "Demo scenario view for RC checklist; not a market instruction.",
        "recommended_windows": [
            {
                "time": "10:00-14:00",
                "stance": "neutral",
                "reason": "Demo window only; no verified Example Province price curve is linked.",
            },
            {
                "time": "18:00-21:00",
                "stance": "preserve_flexibility",
                "reason": "Demo evening peak review point; human check remains required.",
            },
        ],
        "hydro_action": "Review manually; do not execute trades from this demo recommendation.",
        "risk_level": "medium",
        "confidence": 0.58,
        "missing_data_warnings": [
            "No verified internal reservoir operation data is connected.",
            "No verified Example Province spot 96-point curve is connected.",
        ],
        "evidence": evidence,
        "human_check_required": True,
        "no_auto_trading": True,
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _hash_json(value: object) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
