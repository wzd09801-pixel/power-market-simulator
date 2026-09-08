from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.core.errors import (
    RecommendationAuditNotAdoptableError,
    RecommendationDecisionNotFoundError,
    RecommendationNotFoundError,
    WeatherFeatureSnapshotNotFoundError,
    WeatherFeatureSnapshotNotUsableError,
)
from backend.app.models.recommendation import (
    RecommendationDecision,
    RecommendationDecisionFeedback,
    RecommendationReview,
    RecommendationRun,
)
from backend.app.models.weather import WeatherFeatureSnapshot
from backend.app.repositories.recommendations import (
    add_audit_event,
    add_feature_snapshot,
    add_recommendation_decision,
    add_recommendation_decision_feedback,
    add_recommendation_review,
    add_recommendation_run,
    get_recommendation_decision,
    get_recommendation_run,
    list_all_recommendation_decision_feedback,
    list_all_recommendation_decisions,
    list_all_recommendation_runs,
    list_recent_recommendation_runs,
    list_recommendation_decision_feedback,
    list_recommendation_decisions,
    list_recommendation_reviews,
)
from backend.app.repositories.weather import get_weather_feature_snapshot_by_id
from backend.app.schemas.common import Evidence, RecommendedWindow
from backend.app.schemas.recommendation import (
    RecommendationAuditCheck,
    RecommendationAuditResponse,
    RecommendationAuditStatus,
    RecommendationContent,
    RecommendationDecisionFeedbackRequest,
    RecommendationDecisionFeedbackResponse,
    RecommendationDecisionListResponse,
    RecommendationDecisionOutcomeStatus,
    RecommendationDecisionRequest,
    RecommendationDecisionResponse,
    RecommendationDecisionStatus,
    RecommendationDetailResponse,
    RecommendationEvidenceExportResponse,
    RecommendationEvidenceSummary,
    RecommendationFeedbackAnalyticsDecision,
    RecommendationFeedbackAnalyticsFeedback,
    RecommendationFeedbackAnalyticsResponse,
    RecommendationFeedbackAnalyticsSummary,
    RecommendationRecentResponse,
    RecommendationReviewRequest,
    RecommendationReviewResponse,
    RecommendationRunRequest,
    RecommendationRunResponse,
    ReviewAction,
    ReviewStatus,
)
from backend.app.services.scenarios import get_default_demo_hydro_scenario
from backend.app.services.weather_features import REQUIRED_HYDRO_WEATHER_FEATURES


def _now() -> datetime:
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _build_recommendation_content(
    request: RecommendationRunRequest,
    weather_snapshot: WeatherFeatureSnapshot | None,
) -> RecommendationContent:
    scenario = get_default_demo_hydro_scenario()

    if request.asset_id != scenario.asset_id or request.scenario_id != scenario.scenario_id:
        missing = ["第一阶段仅提供示例水电站 A默认模拟场景，本次请求已按默认场景生成。"]
    else:
        missing = []

    missing.extend(
        [
            "尚未接入经过核验的公司水库运行数据。",
            "尚未接入经过核验的中长期持仓数据。",
            "尚未接入示例甲省现货价格序列。",
        ]
    )
    evidence = list(scenario.evidence)
    if weather_snapshot is None:
        missing.append(
            "No approved public-derived weather feature snapshot is linked to this draft."
        )
    else:
        missing.append(
            "Linked weather context is public-derived from a public reference point; "
            "it is not verified station sensor or internal operational data."
        )
        evidence.extend(_build_weather_evidence(weather_snapshot))

    if scenario.storage_condition == "high" or scenario.inflow_regime == "wet":
        market_view = "模拟研判：较高库水位或偏丰来水可能增加消纳压力。"
        hydro_action = "优先关注安全消纳，不将仅基于价格的优化结果作为约束性指令。"
        risk_level = "medium_high"
        confidence = 0.58
    elif scenario.storage_condition == "low" or scenario.inflow_regime == "dry":
        market_view = "模拟研判：可用电量受到约束，水量机会成本上升。"
        hydro_action = "在人工复核下保留灵活水量，重点关注晚高峰窗口。"
        risk_level = "medium"
        confidence = 0.6
    else:
        market_view = "模拟研判：正常库水位与正常来水支持相对均衡的调度姿态。"
        hydro_action = "保持均衡计划，并为晚高峰条件预留调节灵活性。"
        risk_level = "medium"
        confidence = 0.62

    return RecommendationContent(
        trade_date=request.trade_date,
        asset_id=scenario.asset_id,
        data_mode=scenario.data_mode,
        scenario_id=scenario.scenario_id,
        weather_feature_snapshot_id=(
            weather_snapshot.feature_snapshot_id if weather_snapshot is not None else None
        ),
        horizon="day_ahead_scenario",
        market_view=market_view,
        recommended_windows=[
            RecommendedWindow(
                time="10:00-14:00",
                stance="neutral",
                reason="尚未接入经过核验的现货价格曲线，不将该时段认定为真实低价窗口。",
            ),
            RecommendedWindow(
                time="18:00-21:00",
                stance="preserve_flexibility",
                reason="晚高峰是常见重点窗口，但当前动作仍仅为模拟建议。",
            ),
        ],
        hydro_action=hydro_action,
        risk_level=risk_level,
        confidence=confidence,
        missing_data_warnings=missing,
        evidence=evidence,
        human_check_required=True,
        no_auto_trading=True,
    )


def _to_run_response(run: RecommendationRun) -> RecommendationRunResponse:
    content = RecommendationContent.model_validate(run.strategy_json)
    return RecommendationRunResponse(
        **content.model_dump(),
        recommendation_id=run.rec_id,
        input_snapshot_id=run.input_snapshot_id,
        created_at=run.created_at,
        review_status=cast(ReviewStatus, run.review_status),
    )


def _to_review_response(review: RecommendationReview) -> RecommendationReviewResponse:
    return RecommendationReviewResponse(
        review_id=review.review_id,
        recommendation_id=review.recommendation_id,
        created_at=review.created_at,
        actor=review.actor,
        review_status=cast(ReviewAction, review.review_status),
        note=review.note,
    )


def _to_feedback_response(
    feedback: RecommendationDecisionFeedback,
) -> RecommendationDecisionFeedbackResponse:
    return RecommendationDecisionFeedbackResponse(
        feedback_id=feedback.feedback_id,
        decision_id=feedback.decision_id,
        recommendation_id=feedback.recommendation_id,
        created_at=feedback.created_at,
        actor=feedback.actor,
        outcome_status=cast(RecommendationDecisionOutcomeStatus, feedback.outcome_status),
        observed_at=feedback.observed_at,
        note=feedback.note,
        data_mode=feedback.data_mode,
    )


def _to_decision_response(
    decision: RecommendationDecision,
    feedback_items: list[RecommendationDecisionFeedback],
) -> RecommendationDecisionResponse:
    return RecommendationDecisionResponse(
        decision_id=decision.decision_id,
        recommendation_id=decision.recommendation_id,
        created_at=decision.created_at,
        actor=decision.actor,
        decision_status=cast(RecommendationDecisionStatus, decision.decision_status),
        selected_windows=list(decision.selected_windows_json),
        note=decision.note,
        safety_boundary_acknowledged=decision.safety_boundary_acknowledged,
        no_auto_trading=decision.no_auto_trading,
        audit_snapshot=decision.audit_snapshot_json,
        feedback=[_to_feedback_response(item) for item in feedback_items],
    )


def _to_feedback_analytics_decision(
    decision: RecommendationDecision,
    *,
    feedback_count_by_decision: Counter[str],
    latest_feedback_by_decision: dict[str, RecommendationDecisionFeedback],
) -> RecommendationFeedbackAnalyticsDecision:
    latest_feedback = latest_feedback_by_decision.get(decision.decision_id)
    return RecommendationFeedbackAnalyticsDecision(
        decision_id=decision.decision_id,
        recommendation_id=decision.recommendation_id,
        created_at=decision.created_at,
        actor=decision.actor,
        decision_status=cast(RecommendationDecisionStatus, decision.decision_status),
        audit_status=_decision_audit_status(decision),
        selected_windows=list(decision.selected_windows_json),
        note=decision.note,
        no_auto_trading=decision.no_auto_trading,
        safety_boundary_acknowledged=decision.safety_boundary_acknowledged,
        feedback_count=feedback_count_by_decision[decision.decision_id],
        latest_outcome_status=(
            cast(RecommendationDecisionOutcomeStatus, latest_feedback.outcome_status)
            if latest_feedback is not None
            else None
        ),
        latest_feedback_at=latest_feedback.created_at if latest_feedback is not None else None,
    )


def _to_feedback_analytics_feedback(
    feedback: RecommendationDecisionFeedback,
    decision: RecommendationDecision | None,
) -> RecommendationFeedbackAnalyticsFeedback:
    return RecommendationFeedbackAnalyticsFeedback(
        feedback_id=feedback.feedback_id,
        decision_id=feedback.decision_id,
        recommendation_id=feedback.recommendation_id,
        created_at=feedback.created_at,
        actor=feedback.actor,
        decision_status=(
            cast(RecommendationDecisionStatus, decision.decision_status)
            if decision is not None
            else None
        ),
        outcome_status=cast(RecommendationDecisionOutcomeStatus, feedback.outcome_status),
        observed_at=feedback.observed_at,
        note=feedback.note,
        data_mode=feedback.data_mode,
    )


def generate_recommendation(
    request: RecommendationRunRequest, session: Session
) -> RecommendationRunResponse:
    scenario = get_default_demo_hydro_scenario()
    created_at = _now()
    recommendation_id = _new_id("rec")
    input_snapshot_id = _new_id("snapshot")

    with session.begin():
        weather_snapshot = _get_linked_weather_feature_snapshot(request, session)
        content = _build_recommendation_content(request, weather_snapshot)
        add_feature_snapshot(
            session,
            snapshot_id=input_snapshot_id,
            created_at=created_at,
            trade_date=request.trade_date,
            asset_id=scenario.asset_id,
            scenario_id=scenario.scenario_id,
            data_mode=scenario.data_mode,
            inputs_json=_build_snapshot_inputs(
                scenario.model_dump(mode="json", exclude={"evidence"}),
                weather_snapshot,
            ),
            evidence_json=[item.model_dump(mode="json") for item in content.evidence],
        )
        run = add_recommendation_run(
            session,
            recommendation_id=recommendation_id,
            created_at=created_at,
            input_snapshot_id=input_snapshot_id,
            trade_date=request.trade_date,
            asset_id=content.asset_id,
            data_mode=content.data_mode,
            scenario_id=content.scenario_id,
            risk_level=content.risk_level,
            confidence=content.confidence,
            strategy_json=content.model_dump(mode="json"),
        )
        add_audit_event(
            session,
            event_id=_new_id("audit"),
            created_at=created_at,
            event_type="recommendation_generated",
            data_mode=content.data_mode,
            payload_json={
                "recommendation_id": recommendation_id,
                "input_snapshot_id": input_snapshot_id,
                "scenario_id": content.scenario_id,
                "review_status": "pending_review",
                "weather_feature_snapshot_id": content.weather_feature_snapshot_id,
            },
        )

    return _to_run_response(run)


def _get_linked_weather_feature_snapshot(
    request: RecommendationRunRequest,
    session: Session,
) -> WeatherFeatureSnapshot | None:
    snapshot_id = request.weather_feature_snapshot_id
    if snapshot_id is None:
        return None
    snapshot = get_weather_feature_snapshot_by_id(session, snapshot_id)
    if snapshot is None:
        raise WeatherFeatureSnapshotNotFoundError(snapshot_id, identifier_type="snapshot")
    _ensure_weather_snapshot_is_linkable(snapshot, trade_date=request.trade_date)
    return snapshot


def _ensure_weather_snapshot_is_linkable(
    snapshot: WeatherFeatureSnapshot,
    *,
    trade_date: date,
) -> None:
    if snapshot.quality_status != "valid":
        raise WeatherFeatureSnapshotNotUsableError(
            snapshot.feature_snapshot_id,
            "quality status is not valid",
        )
    if snapshot.human_review_status != "approved":
        raise WeatherFeatureSnapshotNotUsableError(
            snapshot.feature_snapshot_id,
            "human review status is not approved",
        )
    if snapshot.forecast_start is None or snapshot.forecast_start.date() != trade_date:
        raise WeatherFeatureSnapshotNotUsableError(
            snapshot.feature_snapshot_id,
            f"forecast window does not start on trade date {trade_date.isoformat()}",
        )
    missing = sorted(
        feature
        for feature in REQUIRED_HYDRO_WEATHER_FEATURES
        if snapshot.features_json.get(feature) is None
    )
    if missing:
        raise WeatherFeatureSnapshotNotUsableError(
            snapshot.feature_snapshot_id,
            f"required derived features are missing: {', '.join(missing)}",
        )


def _build_snapshot_inputs(
    scenario_inputs: dict[str, Any],
    weather_snapshot: WeatherFeatureSnapshot | None,
) -> dict[str, Any]:
    if weather_snapshot is None:
        return scenario_inputs
    return {
        **scenario_inputs,
        "weather_feature_snapshot": {
            "feature_snapshot_id": weather_snapshot.feature_snapshot_id,
            "provider": weather_snapshot.provider,
            "location_id": weather_snapshot.location_id,
            "generated_at": weather_snapshot.generated_at.isoformat(),
            "forecast_start": (
                weather_snapshot.forecast_start.isoformat()
                if weather_snapshot.forecast_start is not None
                else None
            ),
            "feature_version": weather_snapshot.feature_version,
            "quality_status": weather_snapshot.quality_status,
            "human_review_status": weather_snapshot.human_review_status,
            "data_mode": weather_snapshot.data_mode,
            "features": weather_snapshot.features_json,
        },
    }


def _build_weather_evidence(snapshot: WeatherFeatureSnapshot) -> list[Evidence]:
    evidence: list[Evidence] = []
    for item in snapshot.evidence_json:
        value = item.get("value")
        if not isinstance(value, (str, float, int, bool)):
            continue
        evidence.append(
            Evidence(
                source=snapshot.provider,
                source_type="weather_feature",
                data_mode=snapshot.data_mode,
                timestamp=snapshot.generated_at,
                field=str(item.get("field")),
                value=value,
                unit=str(item["unit"]) if item.get("unit") is not None else None,
                confidence=0.85,
                url="https://open-meteo.com/",
                note=(
                    f"Approved {snapshot.feature_version} public-derived feature; "
                    f"raw_payload_id={snapshot.raw_payload_id}; formula={item.get('formula')}."
                ),
            )
        )
    return evidence


def get_recommendation_detail(
    recommendation_id: str, session: Session
) -> RecommendationDetailResponse:
    run = get_recommendation_run(session, recommendation_id)
    if run is None:
        raise RecommendationNotFoundError(recommendation_id)
    response = _to_run_response(run)
    reviews = [
        _to_review_response(review)
        for review in list_recommendation_reviews(session, recommendation_id)
    ]
    return RecommendationDetailResponse(**response.model_dump(), reviews=reviews)


def get_recent_recommendations(*, limit: int, session: Session) -> RecommendationRecentResponse:
    runs = list_recent_recommendation_runs(session, limit=limit)
    return RecommendationRecentResponse(items=[_to_run_response(run) for run in runs])


def get_recommendation_feedback_analytics(
    *,
    limit: int,
    session: Session,
) -> RecommendationFeedbackAnalyticsResponse:
    runs = list_all_recommendation_runs(session)
    decisions = list_all_recommendation_decisions(session)
    feedback_items = list_all_recommendation_decision_feedback(session)
    feedback_count_by_decision: Counter[str] = Counter()
    latest_feedback_by_decision: dict[str, RecommendationDecisionFeedback] = {}
    decision_by_id = {decision.decision_id: decision for decision in decisions}
    for feedback in feedback_items:
        feedback_count_by_decision[feedback.decision_id] += 1
        latest_feedback_by_decision.setdefault(feedback.decision_id, feedback)

    decision_status_counts = Counter(decision.decision_status for decision in decisions)
    review_status_counts = Counter(run.review_status for run in runs)
    audit_status_counts = Counter(_build_audit_response(run).overall_status for run in runs)
    outcome_status_counts = Counter(feedback.outcome_status for feedback in feedback_items)
    feedback_data_modes = Counter(feedback.data_mode for feedback in feedback_items)
    pending_decisions = [
        decision
        for decision in decisions
        if _decision_needs_observation(decision, latest_feedback_by_decision)
    ]
    critical_not_adopted = [
        decision
        for decision in decisions
        if _decision_audit_status(decision) == "critical"
        and decision.decision_status in {"not_adopted", "deferred"}
    ]
    no_auto_false_count = sum(1 for decision in decisions if not decision.no_auto_trading)
    safety_unacknowledged_count = sum(
        1 for decision in decisions if not decision.safety_boundary_acknowledged
    )
    status = _feedback_analytics_status(
        decision_count=len(decisions),
        pending_observation_count=len(pending_decisions),
        critical_audit_not_adopted_count=len(critical_not_adopted),
        no_auto_trading_false_count=no_auto_false_count,
        safety_boundary_unacknowledged_count=safety_unacknowledged_count,
    )
    return RecommendationFeedbackAnalyticsResponse(
        generated_at=_now(),
        status=status,
        message=_feedback_analytics_message(status, decision_count=len(decisions)),
        summary=RecommendationFeedbackAnalyticsSummary(
            recommendation_count=len(runs),
            decision_count=len(decisions),
            feedback_count=len(feedback_items),
            pending_observation_count=len(pending_decisions),
            critical_audit_not_adopted_count=len(critical_not_adopted),
            no_auto_trading_false_count=no_auto_false_count,
            safety_boundary_unacknowledged_count=safety_unacknowledged_count,
            audit_status_counts={
                str(status): count for status, count in audit_status_counts.items()
            },
            review_status_counts=dict(review_status_counts),
            decision_status_counts=dict(decision_status_counts),
            outcome_status_counts=dict(outcome_status_counts),
            feedback_data_modes=dict(feedback_data_modes),
        ),
        recent_decisions=[
            _to_feedback_analytics_decision(
                decision,
                feedback_count_by_decision=feedback_count_by_decision,
                latest_feedback_by_decision=latest_feedback_by_decision,
            )
            for decision in decisions[:limit]
        ],
        recent_feedback=[
            _to_feedback_analytics_feedback(feedback, decision_by_id.get(feedback.decision_id))
            for feedback in feedback_items[:limit]
        ],
        pending_observation_decisions=[
            _to_feedback_analytics_decision(
                decision,
                feedback_count_by_decision=feedback_count_by_decision,
                latest_feedback_by_decision=latest_feedback_by_decision,
            )
            for decision in pending_decisions[:limit]
        ],
        critical_audit_not_adopted=[
            _to_feedback_analytics_decision(
                decision,
                feedback_count_by_decision=feedback_count_by_decision,
                latest_feedback_by_decision=latest_feedback_by_decision,
            )
            for decision in critical_not_adopted[:limit]
        ],
        recommended_actions=_feedback_analytics_actions(
            decision_count=len(decisions),
            pending_observation_count=len(pending_decisions),
            critical_audit_not_adopted_count=len(critical_not_adopted),
            no_auto_trading_false_count=no_auto_false_count,
            safety_boundary_unacknowledged_count=safety_unacknowledged_count,
        ),
        no_auto_trading=True,
    )


def get_recommendation_audit(
    recommendation_id: str, session: Session
) -> RecommendationAuditResponse:
    run = get_recommendation_run(session, recommendation_id)
    if run is None:
        raise RecommendationNotFoundError(recommendation_id)
    return _build_audit_response(run)


def get_recommendation_evidence_export(
    recommendation_id: str, session: Session
) -> RecommendationEvidenceExportResponse:
    run = get_recommendation_run(session, recommendation_id)
    if run is None:
        raise RecommendationNotFoundError(recommendation_id)
    content = RecommendationContent.model_validate(run.strategy_json)
    audit = _build_audit_response(run)
    return RecommendationEvidenceExportResponse(
        recommendation_id=run.rec_id,
        input_snapshot_id=run.input_snapshot_id,
        trade_date=run.trade_date,
        asset_id=run.asset_id,
        scenario_id=run.scenario_id,
        generated_at=run.created_at,
        exported_at=_now(),
        review_status=cast(ReviewStatus, run.review_status),
        audit_status=audit.overall_status,
        data_mode=run.data_mode,
        risk_level=run.risk_level,
        confidence=run.confidence,
        human_check_required=audit.human_check_required,
        no_auto_trading=audit.no_auto_trading,
        missing_data_warnings=content.missing_data_warnings,
        evidence_summary=audit.evidence_summary,
        checks=audit.checks,
        recommended_actions=audit.recommended_actions,
        evidence=content.evidence,
    )


def create_recommendation_decision(
    recommendation_id: str,
    request: RecommendationDecisionRequest,
    session: Session,
) -> RecommendationDecisionResponse:
    created_at = _now()
    with session.begin():
        run = get_recommendation_run(session, recommendation_id)
        if run is None:
            raise RecommendationNotFoundError(recommendation_id)
        audit = _build_audit_response(run)
        if audit.overall_status == "critical" and request.decision_status in {
            "adopted",
            "partially_adopted",
        }:
            raise RecommendationAuditNotAdoptableError(recommendation_id)
        audit_snapshot = audit.model_dump(mode="json")
        decision = add_recommendation_decision(
            session,
            decision_id=_new_id("decision"),
            recommendation_id=recommendation_id,
            created_at=created_at,
            decision_status=request.decision_status,
            selected_windows_json=request.selected_windows,
            note=request.note,
            safety_boundary_acknowledged=request.safety_boundary_acknowledged,
            no_auto_trading=audit.no_auto_trading,
            audit_snapshot_json=audit_snapshot,
            actor="local_operator",
        )
        add_audit_event(
            session,
            event_id=_new_id("audit"),
            created_at=created_at,
            event_type="recommendation_decision_recorded",
            data_mode="user_uploaded",
            actor="local_operator",
            payload_json={
                "recommendation_id": recommendation_id,
                "decision_id": decision.decision_id,
                "decision_status": request.decision_status,
                "selected_windows": request.selected_windows,
                "safety_boundary_acknowledged": request.safety_boundary_acknowledged,
                "no_auto_trading": audit.no_auto_trading,
                "audit_status": audit.overall_status,
            },
        )
    return _to_decision_response(decision, [])


def list_recommendation_decision_log(
    recommendation_id: str,
    session: Session,
) -> RecommendationDecisionListResponse:
    run = get_recommendation_run(session, recommendation_id)
    if run is None:
        raise RecommendationNotFoundError(recommendation_id)
    decisions = list_recommendation_decisions(session, recommendation_id)
    return RecommendationDecisionListResponse(
        items=[
            _to_decision_response(
                decision,
                list_recommendation_decision_feedback(session, decision.decision_id),
            )
            for decision in decisions
        ]
    )


def create_recommendation_decision_feedback(
    decision_id: str,
    request: RecommendationDecisionFeedbackRequest,
    session: Session,
) -> RecommendationDecisionFeedbackResponse:
    created_at = _now()
    with session.begin():
        decision = get_recommendation_decision(session, decision_id)
        if decision is None:
            raise RecommendationDecisionNotFoundError(decision_id)
        feedback = add_recommendation_decision_feedback(
            session,
            feedback_id=_new_id("feedback"),
            decision_id=decision_id,
            recommendation_id=decision.recommendation_id,
            created_at=created_at,
            outcome_status=request.outcome_status,
            observed_at=request.observed_at,
            note=request.note,
            actor="local_operator",
            data_mode="user_uploaded",
        )
        add_audit_event(
            session,
            event_id=_new_id("audit"),
            created_at=created_at,
            event_type="recommendation_decision_feedback_recorded",
            data_mode="user_uploaded",
            actor="local_operator",
            payload_json={
                "recommendation_id": decision.recommendation_id,
                "decision_id": decision_id,
                "feedback_id": feedback.feedback_id,
                "outcome_status": request.outcome_status,
                "observed_at": (
                    request.observed_at.isoformat() if request.observed_at is not None else None
                ),
            },
        )
    return _to_feedback_response(feedback)


def _build_audit_response(run: RecommendationRun) -> RecommendationAuditResponse:
    content = RecommendationContent.model_validate(run.strategy_json)
    summary = _build_evidence_summary(content)
    checks = _build_recommendation_audit_checks(content, run=run, summary=summary)
    overall_status = _overall_audit_status(checks)
    return RecommendationAuditResponse(
        recommendation_id=run.rec_id,
        generated_at=run.created_at,
        audited_at=_now(),
        review_status=cast(ReviewStatus, run.review_status),
        overall_status=overall_status,
        evidence_summary=summary,
        checks=checks,
        recommended_actions=_recommended_audit_actions(checks),
        human_check_required=content.human_check_required,
        no_auto_trading=content.no_auto_trading,
    )


def _decision_audit_status(
    decision: RecommendationDecision,
) -> RecommendationAuditStatus | None:
    value = decision.audit_snapshot_json.get("overall_status")
    if value in {"healthy", "warning", "critical"}:
        return cast(RecommendationAuditStatus, value)
    return None


def _decision_needs_observation(
    decision: RecommendationDecision,
    latest_feedback_by_decision: dict[str, RecommendationDecisionFeedback],
) -> bool:
    latest_feedback = latest_feedback_by_decision.get(decision.decision_id)
    return latest_feedback is None or latest_feedback.outcome_status == "pending_observation"


def _feedback_analytics_status(
    *,
    decision_count: int,
    pending_observation_count: int,
    critical_audit_not_adopted_count: int,
    no_auto_trading_false_count: int,
    safety_boundary_unacknowledged_count: int,
) -> RecommendationAuditStatus:
    if no_auto_trading_false_count or safety_boundary_unacknowledged_count:
        return "critical"
    if decision_count == 0 or pending_observation_count or critical_audit_not_adopted_count:
        return "warning"
    return "healthy"


def _feedback_analytics_message(
    status: RecommendationAuditStatus,
    *,
    decision_count: int,
) -> str:
    if decision_count == 0:
        return "No local recommendation decisions have been recorded yet."
    if status == "critical":
        return "Recommendation feedback contains critical safety-boundary records."
    if status == "warning":
        return "Recommendation feedback contains pending observations or critical-audit notes."
    return "Recommendation feedback records have no pending analytics warnings."


def _feedback_analytics_actions(
    *,
    decision_count: int,
    pending_observation_count: int,
    critical_audit_not_adopted_count: int,
    no_auto_trading_false_count: int,
    safety_boundary_unacknowledged_count: int,
) -> list[str]:
    actions: list[str] = []
    if decision_count == 0:
        actions.append("Record operator decisions after reviewing recommendation audits.")
    if pending_observation_count:
        actions.append("Add follow-up feedback for decisions still pending observation.")
    if critical_audit_not_adopted_count:
        actions.append("Review critical-audit not-adopted or deferred notes before reuse.")
    if no_auto_trading_false_count or safety_boundary_unacknowledged_count:
        actions.append("Investigate decision records with failed safety-boundary fields.")
    return actions or ["No feedback follow-up is required beyond normal operator review."]


def review_recommendation(
    recommendation_id: str,
    request: RecommendationReviewRequest,
    session: Session,
) -> RecommendationReviewResponse:
    created_at = _now()
    with session.begin():
        run = get_recommendation_run(session, recommendation_id)
        if run is None:
            raise RecommendationNotFoundError(recommendation_id)
        review = add_recommendation_review(
            session,
            review_id=_new_id("review"),
            recommendation_id=recommendation_id,
            created_at=created_at,
            review_status=request.review_status,
            note=request.note,
            actor="local_operator",
        )
        run.review_status = request.review_status
        add_audit_event(
            session,
            event_id=_new_id("audit"),
            created_at=created_at,
            event_type="recommendation_reviewed",
            data_mode=run.data_mode,
            actor="local_operator",
            payload_json={
                "recommendation_id": recommendation_id,
                "review_id": review.review_id,
                "review_status": request.review_status,
                "note": request.note,
            },
        )

    return _to_review_response(review)


def _build_evidence_summary(content: RecommendationContent) -> RecommendationEvidenceSummary:
    data_modes: dict[str, int] = {}
    source_types: dict[str, int] = {}
    incomplete_count = 0
    research_only_count = 0
    bench_count = 0
    policy_watch_count = 0
    weather_evidence_present = False
    for evidence in content.evidence:
        data_modes[evidence.data_mode] = data_modes.get(evidence.data_mode, 0) + 1
        source_types[evidence.source_type] = source_types.get(evidence.source_type, 0) + 1
        if evidence.source_type == "weather_feature":
            weather_evidence_present = True
        if _evidence_is_incomplete(evidence):
            incomplete_count += 1
        haystack = _evidence_haystack(evidence)
        if "research_only" in haystack:
            research_only_count += 1
        if any(marker in haystack for marker in ("bench", "dispatchis", "nemweb")):
            bench_count += 1
        if any(marker in haystack for marker in ("policy_watch", "policy watch", "policy-watch")):
            policy_watch_count += 1
    return RecommendationEvidenceSummary(
        evidence_count=len(content.evidence),
        missing_data_count=len(content.missing_data_warnings),
        data_modes=data_modes,
        source_types=source_types,
        weather_evidence_present=weather_evidence_present,
        incomplete_evidence_count=incomplete_count,
        research_only_evidence_count=research_only_count,
        bench_evidence_count=bench_count,
        policy_watch_evidence_count=policy_watch_count,
    )


def _build_recommendation_audit_checks(
    content: RecommendationContent,
    *,
    run: RecommendationRun,
    summary: RecommendationEvidenceSummary,
) -> list[RecommendationAuditCheck]:
    restricted_count = (
        summary.research_only_evidence_count
        + summary.bench_evidence_count
        + summary.policy_watch_evidence_count
    )
    return [
        RecommendationAuditCheck(
            key="no_auto_trading",
            label="No Automatic Trading",
            status="healthy" if content.no_auto_trading else "critical",
            message=(
                "Recommendation explicitly disables automatic trading."
                if content.no_auto_trading
                else "Recommendation does not explicitly disable automatic trading."
            ),
            details={"no_auto_trading": content.no_auto_trading},
        ),
        RecommendationAuditCheck(
            key="human_review_required",
            label="Human Review Required",
            status="healthy" if content.human_check_required else "critical",
            message=(
                "Recommendation requires human review."
                if content.human_check_required
                else "Recommendation is missing the human review requirement."
            ),
            details={"human_check_required": content.human_check_required},
        ),
        RecommendationAuditCheck(
            key="scenario_data_mode",
            label="Scenario Data Mode",
            status=(
                "healthy"
                if content.data_mode == "scenario_simulated"
                and run.data_mode == "scenario_simulated"
                else "critical"
            ),
            message=(
                "Recommendation is explicitly marked as scenario_simulated."
                if content.data_mode == "scenario_simulated"
                and run.data_mode == "scenario_simulated"
                else "Recommendation is not consistently marked as scenario_simulated."
            ),
            details={"run_data_mode": run.data_mode, "content_data_mode": content.data_mode},
        ),
        RecommendationAuditCheck(
            key="evidence_integrity",
            label="Evidence Integrity",
            status=_evidence_integrity_status(summary),
            message=_evidence_integrity_message(summary),
            details={
                "evidence_count": summary.evidence_count,
                "incomplete_evidence_count": summary.incomplete_evidence_count,
            },
        ),
        RecommendationAuditCheck(
            key="recommendation_chain_isolation",
            label="Recommendation Chain Isolation",
            status="critical" if restricted_count else "healthy",
            message=(
                "Recommendation evidence is isolated from BENCH, research_only, and policy watch."
                if restricted_count == 0
                else (
                    "Recommendation evidence contains BENCH, research_only, "
                    "or policy watch markers."
                )
            ),
            details={
                "research_only_evidence_count": summary.research_only_evidence_count,
                "bench_evidence_count": summary.bench_evidence_count,
                "policy_watch_evidence_count": summary.policy_watch_evidence_count,
            },
        ),
        RecommendationAuditCheck(
            key="weather_context",
            label="Weather Context",
            status=(
                "healthy"
                if content.weather_feature_snapshot_id and summary.weather_evidence_present
                else "warning"
            ),
            message=(
                "Approved public-derived weather feature evidence is linked."
                if content.weather_feature_snapshot_id and summary.weather_evidence_present
                else "No approved public-derived weather feature evidence is linked."
            ),
            details={
                "weather_feature_snapshot_id": content.weather_feature_snapshot_id,
                "weather_evidence_present": summary.weather_evidence_present,
            },
        ),
        RecommendationAuditCheck(
            key="missing_data",
            label="Missing Data Warnings",
            status="warning" if summary.missing_data_count else "healthy",
            message=(
                f"{summary.missing_data_count} missing-data warnings require operator review."
                if summary.missing_data_count
                else "No missing-data warnings are attached."
            ),
            details={"missing_data_warnings": content.missing_data_warnings},
        ),
        RecommendationAuditCheck(
            key="review_status",
            label="Review Status",
            status="warning" if run.review_status == "pending_review" else "healthy",
            message=(
                "Recommendation is still pending human review."
                if run.review_status == "pending_review"
                else f"Latest recommendation review status is {run.review_status}."
            ),
            details={"review_status": run.review_status},
        ),
    ]


def _evidence_integrity_status(
    summary: RecommendationEvidenceSummary,
) -> RecommendationAuditStatus:
    if summary.evidence_count == 0 or summary.incomplete_evidence_count > 0:
        return "critical"
    return "healthy"


def _evidence_integrity_message(summary: RecommendationEvidenceSummary) -> str:
    if summary.evidence_count == 0:
        return "Recommendation has no structured evidence."
    if summary.incomplete_evidence_count:
        return "Recommendation contains incomplete structured evidence."
    return "Recommendation evidence has required structured fields."


def _overall_audit_status(checks: list[RecommendationAuditCheck]) -> RecommendationAuditStatus:
    if any(check.status == "critical" for check in checks):
        return "critical"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "healthy"


def _recommended_audit_actions(checks: list[RecommendationAuditCheck]) -> list[str]:
    actions: list[str] = []
    if any(check.status == "critical" for check in checks):
        actions.append("Resolve critical safety or evidence issues before operator approval.")
    if any(check.key == "missing_data" and check.status == "warning" for check in checks):
        actions.append(
            "Review missing internal reservoir, contract, and Example Province spot data warnings."
        )
    if any(check.key == "weather_context" and check.status == "warning" for check in checks):
        actions.append("Optionally link an approved public-derived weather feature snapshot.")
    if any(check.key == "review_status" and check.status == "warning" for check in checks):
        actions.append("Complete human review before using this draft as decision support.")
    return actions or ["No audit follow-up is required beyond normal operator review."]


def _evidence_is_incomplete(evidence: Evidence) -> bool:
    return any(
        not value.strip()
        for value in (
            evidence.source,
            evidence.source_type,
            evidence.data_mode,
            evidence.field,
        )
    )


def _evidence_haystack(evidence: Evidence) -> str:
    return " ".join(
        (
            evidence.source,
            evidence.source_type,
            evidence.data_mode,
            evidence.field,
            evidence.url or "",
            evidence.note or "",
        )
    ).lower()
