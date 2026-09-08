from __future__ import annotations

import json
import logging
from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.adapters.reports_weekly_market_report import (
    PARSER_KEY,
    PARSER_VERSION,
    NormalizedMarketObservation,
    ReportsWeeklyMarketReportParserError,
    parse_reports_weekly_market_report,
)
from backend.app.core.errors import (
    MarketArtifactNotUsableError,
    MarketRawArtifactNotFoundError,
    MarketReportParsingError,
)
from backend.app.models.market import (
    MarketArtifactReview,
    MarketObservation,
    MarketParsingRun,
    MarketRawArtifact,
)
from backend.app.repositories.market import (
    add_market_artifact_review,
    add_market_observation,
    add_market_parsing_run,
    add_market_quality_issue,
    get_market_observation,
    get_market_raw_artifact,
    list_market_observations,
    list_market_parsing_runs,
)
from backend.app.schemas.market import (
    MarketArtifactReviewAction,
    MarketArtifactReviewRequest,
    MarketArtifactReviewResponse,
    MarketObservationListResponse,
    MarketObservationResponse,
    MarketParsingRunListResponse,
    MarketParsingRunResponse,
)
from backend.app.services.market import PUBLIC_DERIVED, _now

logger = logging.getLogger(__name__)


def review_market_artifact(
    artifact_id: str,
    request: MarketArtifactReviewRequest,
    *,
    session: Session,
) -> MarketArtifactReviewResponse:
    created_at = _now()
    with session.begin():
        artifact = get_market_raw_artifact(session, artifact_id)
        if artifact is None:
            raise MarketRawArtifactNotFoundError(artifact_id)
        review = add_market_artifact_review(
            session,
            review_id=_new_id("market_artifact_review"),
            artifact_id=artifact_id,
            created_at=created_at,
            actor="local_operator",
            review_status=request.review_status,
            note=request.note,
        )
        artifact.human_review_status = request.review_status
    return _to_review_response(review)


def parse_reviewed_reports_weekly_artifact(
    artifact_id: str,
    *,
    session: Session,
) -> MarketParsingRunResponse:
    started_at = _now()
    with session.begin():
        artifact = get_market_raw_artifact(session, artifact_id)
    if artifact is None:
        raise MarketRawArtifactNotFoundError(artifact_id)
    _ensure_artifact_can_be_parsed(artifact)
    assert artifact.inline_text is not None
    try:
        result = parse_reports_weekly_market_report(artifact.inline_text)
    except ReportsWeeklyMarketReportParserError as exc:
        _persist_failed_parsing_run(
            artifact_id=artifact_id,
            session=session,
            started_at=started_at,
            error=exc,
        )
        raise MarketReportParsingError(code=exc.code, message=exc.message) from exc

    completed_at = _now()
    parsing_run_id = _new_id("market_parse")
    quality_issue_count = 1 if result.has_unparsed_power_type_section else 0
    with session.begin():
        new_observations = [
            observation
            for observation in result.observations
            if _get_existing_observation(session, artifact_id, observation) is None
        ]
        add_market_parsing_run(
            session,
            parsing_run_id=parsing_run_id,
            artifact_id=artifact_id,
            parser_key=result.parser_key,
            parser_version=result.parser_version,
            started_at=started_at,
            completed_at=completed_at,
            status="succeeded",
            observations_parsed=len(result.observations),
            observations_inserted=len(new_observations),
            duplicate_observations=len(result.observations) - len(new_observations),
            quality_status="valid",
            quality_issue_count=quality_issue_count,
        )
        for observation in new_observations:
            _add_observation(
                session,
                artifact_id=artifact_id,
                parsing_run_id=parsing_run_id,
                observation=observation,
            )
        if result.has_unparsed_power_type_section:
            add_market_quality_issue(
                session,
                quality_issue_id=_new_id("market_quality"),
                source_id=artifact.source_id,
                endpoint_id=artifact.endpoint_id,
                ingestion_run_id=None,
                ingestion_run_item_id=None,
                parsing_run_id=parsing_run_id,
                endpoint_health_check_id=None,
                artifact_id=artifact_id,
                issue_scope="parsing_run",
                issue_code="power_type_section_not_normalized",
                severity="info",
                message=(
                    "The REPORTS weekly report power-type section remains preserved in the "
                    "raw artifact but is not normalized by parser v1."
                ),
                details_json={
                    "parser_key": result.parser_key,
                    "parser_version": result.parser_version,
                },
                data_mode=PUBLIC_DERIVED,
            )
    logger.info(
        "Parsed REPORTS weekly artifact run=%s artifact=%s inserted=%s duplicate=%s issues=%s",
        parsing_run_id,
        artifact_id,
        len(new_observations),
        len(result.observations) - len(new_observations),
        quality_issue_count,
    )
    with session.begin():
        run = _require_parsing_run(session, parsing_run_id)
    return _to_parsing_run_response(run)


def get_market_parsing_runs(
    *, artifact_id: str | None, limit: int, session: Session
) -> MarketParsingRunListResponse:
    return MarketParsingRunListResponse(
        items=[
            _to_parsing_run_response(run)
            for run in list_market_parsing_runs(session, artifact_id=artifact_id, limit=limit)
        ]
    )


def get_market_observations(
    *,
    artifact_id: str | None,
    area_code: str | None,
    market_stage: str | None,
    metric: str | None,
    limit: int,
    session: Session,
) -> MarketObservationListResponse:
    return MarketObservationListResponse(
        items=[
            _to_observation_response(observation)
            for observation in list_market_observations(
                session,
                artifact_id=artifact_id,
                area_code=area_code,
                market_stage=market_stage,
                metric=metric,
                limit=limit,
            )
        ]
    )


def _ensure_artifact_can_be_parsed(artifact: MarketRawArtifact) -> None:
    if artifact.human_review_status != "approved":
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            "human review status must be approved",
        )
    if artifact.endpoint_id != "reports_market_research":
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            "endpoint must be reports_market_research",
        )
    if artifact.media_type != "text/html":
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            "media type must be text/html",
        )
    if artifact.inline_text is None:
        raise MarketArtifactNotUsableError(
            artifact.artifact_id,
            "inline HTML text is required",
        )


def _persist_failed_parsing_run(
    *,
    artifact_id: str,
    session: Session,
    started_at: datetime,
    error: ReportsWeeklyMarketReportParserError,
) -> None:
    completed_at = _now()
    with session.begin():
        add_market_parsing_run(
            session,
            parsing_run_id=_new_id("market_parse"),
            artifact_id=artifact_id,
            parser_key=PARSER_KEY,
            parser_version=PARSER_VERSION,
            started_at=started_at,
            completed_at=completed_at,
            status="failed",
            observations_parsed=0,
            observations_inserted=0,
            duplicate_observations=0,
            quality_status="failed",
            quality_issue_count=0,
            error_code=error.code,
            error_message=error.message,
        )


def _get_existing_observation(
    session: Session,
    artifact_id: str,
    observation: NormalizedMarketObservation,
) -> MarketObservation | None:
    return get_market_observation(
        session,
        artifact_id=artifact_id,
        parser_key=PARSER_KEY,
        parser_version=PARSER_VERSION,
        area_code=observation.area_code,
        market_stage=observation.market_stage,
        metric=observation.metric,
    )


def _add_observation(
    session: Session,
    *,
    artifact_id: str,
    parsing_run_id: str,
    observation: NormalizedMarketObservation,
) -> MarketObservation:
    return add_market_observation(
        session,
        observation_id=_observation_id(artifact_id, observation),
        artifact_id=artifact_id,
        parsing_run_id=parsing_run_id,
        parser_key=PARSER_KEY,
        parser_version=PARSER_VERSION,
        period_start=observation.period_start,
        period_end=observation.period_end,
        area_scope=observation.area_scope,
        area_code=observation.area_code,
        area_name=observation.area_name,
        market_stage=observation.market_stage,
        participant_side=observation.participant_side,
        metric=observation.metric,
        value=observation.value,
        unit=observation.unit,
        settlement_status=observation.settlement_status,
        data_mode=observation.data_mode,
    )


def _observation_id(artifact_id: str, observation: NormalizedMarketObservation) -> str:
    serialized = json.dumps(
        {
            "artifact_id": artifact_id,
            "parser_key": PARSER_KEY,
            "parser_version": PARSER_VERSION,
            "area_code": observation.area_code,
            "market_stage": observation.market_stage,
            "metric": observation.metric,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _require_parsing_run(session: Session, parsing_run_id: str) -> MarketParsingRun:
    run = session.get(MarketParsingRun, parsing_run_id)
    assert run is not None
    return run


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _to_review_response(review: MarketArtifactReview) -> MarketArtifactReviewResponse:
    return MarketArtifactReviewResponse(
        review_id=review.review_id,
        artifact_id=review.artifact_id,
        created_at=review.created_at,
        actor=review.actor,
        review_status=cast(MarketArtifactReviewAction, review.review_status),
        note=review.note,
    )


def _to_parsing_run_response(run: MarketParsingRun) -> MarketParsingRunResponse:
    return MarketParsingRunResponse(
        parsing_run_id=run.parsing_run_id,
        artifact_id=run.artifact_id,
        parser_key=run.parser_key,
        parser_version=run.parser_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        observations_parsed=run.observations_parsed,
        observations_inserted=run.observations_inserted,
        duplicate_observations=run.duplicate_observations,
        quality_status=run.quality_status,
        quality_issue_count=run.quality_issue_count,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _to_observation_response(observation: MarketObservation) -> MarketObservationResponse:
    return MarketObservationResponse(
        observation_id=observation.observation_id,
        artifact_id=observation.artifact_id,
        parsing_run_id=observation.parsing_run_id,
        parser_key=observation.parser_key,
        parser_version=observation.parser_version,
        period_start=observation.period_start,
        period_end=observation.period_end,
        area_scope=observation.area_scope,
        area_code=observation.area_code,
        area_name=observation.area_name,
        market_stage=observation.market_stage,
        participant_side=observation.participant_side,
        metric=observation.metric,
        value=observation.value,
        unit=observation.unit,
        settlement_status=observation.settlement_status,
        data_mode=observation.data_mode,
    )
