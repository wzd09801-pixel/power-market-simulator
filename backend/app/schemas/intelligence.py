from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CitationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    chunk_id: str
    title: str
    source_name: str
    source_url: str | None
    document_layer: str
    data_mode: str


class IntelligenceSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=20)


class IntelligenceSearchResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation: CitationResponse
    excerpt: str
    score: float
    external_processing_allowed: bool


class IntelligenceSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[IntelligenceSearchResultResponse]


class PolicyWatchItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    watch_id: str
    title: str
    observation: str
    excerpt: str
    citation: CitationResponse
    captured_at: datetime
    source_role: Literal["official_policy", "official_market_notice", "supplemental_research"]
    external_processing_allowed: bool
    score: float


class PolicyWatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    items: list[PolicyWatchItemResponse]
    missing_information: list[str]
    excluded_restricted_chunks: int
    local_only: bool
    no_auto_trading: bool


class IntelligenceQuestionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, max_length=2000)
    analysis_mode: Literal["simple", "deep"] = "simple"
    limit: int = Field(default=6, ge=1, le=12)


class IntelligenceQuestionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_run_id: str
    answer: str
    citations: list[CitationResponse]
    missing_information: list[str]
    retrieved_chunk_ids: list[str]
    excluded_restricted_chunks: int
    confidence_score: float
    human_review_required: bool
    llm_used: bool
    llm_model: str | None


class IntelligenceBriefGenerateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_date: date | None = None


class IntelligenceBriefResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    brief_id: str
    target_date: date
    generated_at: datetime
    status: str
    human_review_status: str
    risk_level: str
    confidence_score: float
    deterministic_facts: dict[str, object]
    narrative: dict[str, object]
    citations: list[dict[str, object]]
    policy_watch: list[PolicyWatchItemResponse]
    missing_information: list[str]
    llm_used: bool
    llm_model: str | None
    no_auto_trading: bool


class IntelligenceBriefSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    brief_id: str
    target_date: date
    generated_at: datetime
    human_review_status: str
    risk_level: str
    confidence_score: float
    policy_watch_count: int
    missing_information_count: int
    llm_used: bool
    no_auto_trading: bool


class IntelligenceBriefListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[IntelligenceBriefSummaryResponse]


class IntelligenceBriefReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_status: Literal["approved", "needs_revision"]
    note: str = Field(min_length=1, max_length=1000)


class IntelligenceBriefReviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    brief_id: str
    actor: str
    review_status: str
    note: str
    created_at: datetime


class IntelligenceBriefDetailResponse(IntelligenceBriefResponse):
    model_config = ConfigDict(frozen=True)

    reviews: list[IntelligenceBriefReviewResponse]
