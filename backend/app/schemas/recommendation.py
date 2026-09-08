from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.common import Evidence, RecommendedWindow

ReviewStatus = Literal["pending_review", "approved", "rejected", "needs_revision"]
ReviewAction = Literal["approved", "rejected", "needs_revision"]
RecommendationAuditStatus = Literal["healthy", "warning", "critical"]
RecommendationDecisionStatus = Literal["adopted", "partially_adopted", "not_adopted", "deferred"]
RecommendationDecisionOutcomeStatus = Literal[
    "pending_observation", "useful", "neutral", "not_useful", "uncertain"
]


class RecommendationRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_date: date
    asset_id: str = "demo_hydro_a"
    scenario_id: str = "demo_hydro_a_normal_storage_normal_inflow_v1"
    weather_feature_snapshot_id: str | None = None


class RecommendationContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_date: date
    asset_id: str
    data_mode: str
    scenario_id: str
    weather_feature_snapshot_id: str | None = None
    horizon: str
    market_view: str
    recommended_windows: list[RecommendedWindow]
    hydro_action: str
    risk_level: str
    confidence: float
    missing_data_warnings: list[str]
    evidence: list[Evidence]
    human_check_required: bool
    no_auto_trading: bool


class RecommendationRunResponse(RecommendationContent):
    recommendation_id: str
    input_snapshot_id: str
    created_at: datetime
    review_status: ReviewStatus


class RecommendationReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_status: ReviewAction
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("Review note must not be blank.")
        return note


class RecommendationReviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    recommendation_id: str
    created_at: datetime
    actor: str
    review_status: ReviewAction
    note: str


class RecommendationDetailResponse(RecommendationRunResponse):
    reviews: list[RecommendationReviewResponse]


class RecommendationRecentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[RecommendationRunResponse]


class RecommendationAuditCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    status: RecommendationAuditStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class RecommendationEvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_count: int
    missing_data_count: int
    data_modes: dict[str, int]
    source_types: dict[str, int]
    weather_evidence_present: bool
    incomplete_evidence_count: int
    research_only_evidence_count: int
    bench_evidence_count: int
    policy_watch_evidence_count: int


class RecommendationAuditResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommendation_id: str
    generated_at: datetime
    audited_at: datetime
    review_status: ReviewStatus
    overall_status: RecommendationAuditStatus
    evidence_summary: RecommendationEvidenceSummary
    checks: list[RecommendationAuditCheck]
    recommended_actions: list[str]
    human_check_required: bool
    no_auto_trading: bool


class RecommendationEvidenceExportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommendation_id: str
    input_snapshot_id: str
    trade_date: date
    asset_id: str
    scenario_id: str
    generated_at: datetime
    exported_at: datetime
    review_status: ReviewStatus
    audit_status: RecommendationAuditStatus
    data_mode: str
    risk_level: str
    confidence: float
    human_check_required: bool
    no_auto_trading: bool
    missing_data_warnings: list[str]
    evidence_summary: RecommendationEvidenceSummary
    checks: list[RecommendationAuditCheck]
    recommended_actions: list[str]
    evidence: list[Evidence]


class RecommendationDecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_status: RecommendationDecisionStatus
    selected_windows: list[str] = Field(default_factory=list, max_length=24)
    note: str = Field(min_length=1, max_length=2000)
    safety_boundary_acknowledged: bool

    @field_validator("note")
    @classmethod
    def decision_note_must_not_be_blank(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("Decision note must not be blank.")
        return note

    @field_validator("safety_boundary_acknowledged")
    @classmethod
    def safety_boundary_must_be_acknowledged(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Safety boundary must be acknowledged.")
        return value


class RecommendationDecisionFeedbackRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome_status: RecommendationDecisionOutcomeStatus
    observed_at: date | None = None
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def feedback_note_must_not_be_blank(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("Feedback note must not be blank.")
        return note


class RecommendationDecisionFeedbackResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    feedback_id: str
    decision_id: str
    recommendation_id: str
    created_at: datetime
    actor: str
    outcome_status: RecommendationDecisionOutcomeStatus
    observed_at: date | None
    note: str
    data_mode: str


class RecommendationDecisionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    recommendation_id: str
    created_at: datetime
    actor: str
    decision_status: RecommendationDecisionStatus
    selected_windows: list[str]
    note: str
    safety_boundary_acknowledged: bool
    no_auto_trading: bool
    audit_snapshot: dict[str, object]
    feedback: list[RecommendationDecisionFeedbackResponse]


class RecommendationDecisionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[RecommendationDecisionResponse]


class RecommendationFeedbackAnalyticsSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommendation_count: int
    decision_count: int
    feedback_count: int
    pending_observation_count: int
    critical_audit_not_adopted_count: int
    no_auto_trading_false_count: int
    safety_boundary_unacknowledged_count: int
    audit_status_counts: dict[str, int]
    review_status_counts: dict[str, int]
    decision_status_counts: dict[str, int]
    outcome_status_counts: dict[str, int]
    feedback_data_modes: dict[str, int]


class RecommendationFeedbackAnalyticsDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    recommendation_id: str
    created_at: datetime
    actor: str
    decision_status: RecommendationDecisionStatus
    audit_status: RecommendationAuditStatus | None
    selected_windows: list[str]
    note: str
    no_auto_trading: bool
    safety_boundary_acknowledged: bool
    feedback_count: int
    latest_outcome_status: RecommendationDecisionOutcomeStatus | None
    latest_feedback_at: datetime | None


class RecommendationFeedbackAnalyticsFeedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    feedback_id: str
    decision_id: str
    recommendation_id: str
    created_at: datetime
    actor: str
    decision_status: RecommendationDecisionStatus | None
    outcome_status: RecommendationDecisionOutcomeStatus
    observed_at: date | None
    note: str
    data_mode: str


class RecommendationFeedbackAnalyticsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    status: RecommendationAuditStatus
    message: str
    summary: RecommendationFeedbackAnalyticsSummary
    recent_decisions: list[RecommendationFeedbackAnalyticsDecision]
    recent_feedback: list[RecommendationFeedbackAnalyticsFeedback]
    pending_observation_decisions: list[RecommendationFeedbackAnalyticsDecision]
    critical_audit_not_adopted: list[RecommendationFeedbackAnalyticsDecision]
    recommended_actions: list[str]
    no_auto_trading: bool
