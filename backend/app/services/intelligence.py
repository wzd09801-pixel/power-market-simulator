from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.models.intelligence import (
    IntelligenceBrief,
    IntelligenceBriefReview,
    IntelligenceQuestionRun,
)
from backend.app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from backend.app.repositories.intelligence import (
    add_brief,
    add_brief_review,
    add_question_run,
    count_documents,
    count_market_quality_issues,
    count_recent_workflow_failures,
    count_weather_snapshots,
    get_brief,
    get_latest_brief,
    list_brief_reviews,
    list_briefs,
    list_search_chunks,
)
from backend.app.schemas.intelligence import (
    CitationResponse,
    IntelligenceBriefDetailResponse,
    IntelligenceBriefGenerateRequest,
    IntelligenceBriefListResponse,
    IntelligenceBriefResponse,
    IntelligenceBriefReviewRequest,
    IntelligenceBriefReviewResponse,
    IntelligenceBriefSummaryResponse,
    IntelligenceQuestionRequest,
    IntelligenceQuestionResponse,
    IntelligenceSearchRequest,
    IntelligenceSearchResponse,
    IntelligenceSearchResultResponse,
    PolicyWatchItemResponse,
    PolicyWatchResponse,
)
from backend.app.services.deepseek import DeepSeekClient, DeepSeekProviderError
from backend.app.services.embeddings import EmbeddingClient, cosine_similarity

POLICY_WATCH_QUERIES = (
    "electricity market policy notice rule risk trading settlement hydro",
    "\u5e7f\u4e1c \u7535\u529b \u5e02\u573a \u653f\u7b56 \u901a\u77e5 "
    "\u89c4\u5219 \u4ea4\u6613 \u7ed3\u7b97 \u6c34\u7535 \u98ce\u9669",
    "official policy market notice public research power trading impact",
)
POLICY_WATCH_ALLOWED_LAYERS = frozenset(
    {"official_policy", "official_market_notice", "public_research"}
)
POLICY_WATCH_RESEARCH_MARKERS = (
    "bench",
    "australian energy market operator",
    "dispatch benchmark",
    "dispatchis",
    "nemweb",
    "research_only",
)


@dataclass(frozen=True)
class SearchDraft:
    citation: CitationResponse
    excerpt: str
    score: float
    external_processing_allowed: bool
    full_content: str
    captured_at: datetime


def _now() -> datetime:
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))


def search_intelligence(
    request: IntelligenceSearchRequest,
    *,
    embedding_client: EmbeddingClient,
    session: Session,
) -> IntelligenceSearchResponse:
    drafts = _search_drafts(
        request.query, limit=request.limit, embedding_client=embedding_client, session=session
    )
    return IntelligenceSearchResponse(
        items=[
            IntelligenceSearchResultResponse(
                citation=draft.citation,
                excerpt=draft.excerpt,
                score=draft.score,
                external_processing_allowed=draft.external_processing_allowed,
            )
            for draft in drafts
        ]
    )


def get_policy_watch(
    *,
    limit: int,
    embedding_client: EmbeddingClient,
    session: Session,
) -> PolicyWatchResponse:
    response, _drafts = _build_policy_watch(
        limit=limit,
        embedding_client=embedding_client,
        session=session,
    )
    return response


def answer_intelligence_question(
    request: IntelligenceQuestionRequest,
    *,
    embedding_client: EmbeddingClient,
    deepseek_client: DeepSeekClient,
    session: Session,
) -> IntelligenceQuestionResponse:
    drafts = _search_drafts(
        request.question, limit=request.limit, embedding_client=embedding_client, session=session
    )
    allowed = [draft for draft in drafts if draft.external_processing_allowed]
    excluded = len(drafts) - len(allowed)
    citations = [draft.citation for draft in allowed]
    missing = [] if allowed else ["No externally authorized evidence chunks are available."]
    llm_used = False
    llm_model: str | None = None
    answer = (
        "No evidence-backed answer is available. Review local documents and authorization settings."
    )
    if allowed:
        prompt = _question_prompt(request.question, allowed)
        try:
            payload, llm_model = deepseek_client.complete_json(
                prompt=prompt,
                deep_analysis=request.analysis_mode == "deep",
            )
            candidate = payload.get("answer")
            answer = (
                candidate
                if isinstance(candidate, str) and candidate.strip()
                else _fallback_answer(allowed)
            )
            llm_used = isinstance(candidate, str) and bool(candidate.strip())
        except DeepSeekProviderError:
            answer = _fallback_answer(allowed)
    confidence = min(0.9, 0.35 + 0.1 * len(citations)) if citations else 0.0
    run = IntelligenceQuestionRun(
        question_run_id=f"question_{uuid4().hex}",
        question=request.question,
        analysis_mode=request.analysis_mode,
        answer=answer,
        citations_json=[citation.model_dump(mode="json") for citation in citations],
        missing_information_json=missing,
        retrieved_chunk_ids_json=[draft.citation.chunk_id for draft in drafts],
        excluded_restricted_chunks=excluded,
        confidence_score=confidence,
        human_review_required=True,
        llm_used=llm_used,
        llm_model=llm_model if llm_used else None,
    )
    add_question_run(session, run)
    session.commit()
    return IntelligenceQuestionResponse(
        question_run_id=run.question_run_id,
        answer=run.answer,
        citations=citations,
        missing_information=missing,
        retrieved_chunk_ids=run.retrieved_chunk_ids_json,
        excluded_restricted_chunks=excluded,
        confidence_score=confidence,
        human_review_required=True,
        llm_used=run.llm_used,
        llm_model=run.llm_model,
    )


def generate_intelligence_brief(
    request: IntelligenceBriefGenerateRequest,
    *,
    embedding_client: EmbeddingClient,
    deepseek_client: DeepSeekClient,
    session: Session,
) -> IntelligenceBriefResponse:
    target_date = request.target_date or _now().date()
    policy_watch, policy_watch_drafts = _build_policy_watch(
        limit=5,
        embedding_client=embedding_client,
        session=session,
    )
    facts = {
        "target_date": target_date.isoformat(),
        "weather_snapshot_count": count_weather_snapshots(session),
        "knowledge_document_count": count_documents(session),
        "market_quality_issue_count": count_market_quality_issues(session),
        "workflow_failure_count": count_recent_workflow_failures(session),
        "policy_watch": {
            "item_count": len(policy_watch.items),
            "excluded_restricted_chunks": policy_watch.excluded_restricted_chunks,
            "items": [item.model_dump(mode="json") for item in policy_watch.items],
            "local_only": True,
        },
        "bench_dispatch_benchmark": {
            "usage_scope": "research_only",
            "included_in_example_province_recommendations": False,
        },
    }
    missing = [*policy_watch.missing_information, *_brief_missing_information(facts)]
    risk_level = "medium" if missing or facts["market_quality_issue_count"] else "low"
    narrative: dict[str, object] = _fallback_brief_narrative(facts, missing)
    llm_used = False
    llm_model: str | None = None
    allowed_policy_watch = [
        draft for draft in policy_watch_drafts if draft.external_processing_allowed
    ]
    try:
        candidate, llm_model = deepseek_client.complete_json(
            prompt=_brief_prompt(facts, missing, allowed_policy_watch),
            deep_analysis=False,
        )
        if isinstance(candidate.get("summary"), str):
            narrative = {
                **candidate,
                "policy_watch": candidate.get("policy_watch")
                if isinstance(candidate.get("policy_watch"), list)
                else _fallback_policy_watch_narrative(policy_watch.items),
            }
            llm_used = True
    except DeepSeekProviderError:
        pass
    brief = IntelligenceBrief(
        brief_id=f"brief_{uuid4().hex}",
        target_date=target_date,
        generated_at=_now(),
        status="draft",
        human_review_status="pending_review",
        risk_level=risk_level,
        confidence_score=0.75 if not missing else 0.45,
        deterministic_facts_json=facts,
        narrative_json=narrative,
        citations_json=[item.citation.model_dump(mode="json") for item in policy_watch.items],
        missing_information_json=missing,
        llm_used=llm_used,
        llm_model=llm_model if llm_used else None,
        no_auto_trading=True,
    )
    add_brief(session, brief)
    session.commit()
    return _to_brief_response(brief)


def get_latest_intelligence_brief(*, session: Session) -> IntelligenceBriefResponse:
    brief = get_latest_brief(session)
    if brief is None:
        raise AppError(
            status_code=404,
            code="intelligence_brief_not_found",
            message="No intelligence brief has been generated.",
        )
    return _to_brief_response(brief)


def list_intelligence_briefs(*, limit: int, session: Session) -> IntelligenceBriefListResponse:
    return IntelligenceBriefListResponse(
        items=[_to_brief_summary(brief) for brief in list_briefs(session, limit=limit)]
    )


def get_intelligence_brief_detail(
    brief_id: str, *, session: Session
) -> IntelligenceBriefDetailResponse:
    brief = get_brief(session, brief_id)
    if brief is None:
        raise AppError(
            status_code=404,
            code="intelligence_brief_not_found",
            message=f"Intelligence brief '{brief_id}' was not found.",
        )
    return _to_brief_detail(brief, session=session)


def review_intelligence_brief(
    brief_id: str,
    request: IntelligenceBriefReviewRequest,
    *,
    session: Session,
) -> IntelligenceBriefReviewResponse:
    with session.begin():
        brief = get_brief(session, brief_id)
        if brief is None:
            raise AppError(
                status_code=404,
                code="intelligence_brief_not_found",
                message=f"Intelligence brief '{brief_id}' was not found.",
            )
        brief.human_review_status = request.review_status
        review = add_brief_review(
            session,
            IntelligenceBriefReview(
                review_id=f"brief_review_{uuid4().hex}",
                brief_id=brief_id,
                actor="local_operator",
                review_status=request.review_status,
                note=request.note,
            ),
        )
    return IntelligenceBriefReviewResponse.model_validate(review, from_attributes=True)


def _search_drafts(
    query: str, *, limit: int, embedding_client: EmbeddingClient, session: Session
) -> list[SearchDraft]:
    candidates = list_search_chunks(session, limit=500)
    if not candidates:
        return []
    try:
        query_vector = embedding_client.embed([query])[0]
    except (IndexError, requests.RequestException):
        query_vector = []
    scored: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
    terms = {term for term in query.lower().split() if term}
    for chunk, document in candidates:
        lexical = float(sum(term in chunk.content.lower() for term in terms)) / max(len(terms), 1)
        vector = cosine_similarity(
            query_vector,
            list(chunk.embedding) if chunk.embedding is not None else [],
        )
        scored.append((0.65 * vector + 0.35 * lexical, chunk, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    shortlist = scored[: max(limit * 3, limit)]
    try:
        reranked = embedding_client.rerank(
            query=query, texts=[item[1].content for item in shortlist]
        )
    except requests.RequestException:
        reranked = [item[0] for item in shortlist]
    ordered = sorted(zip(reranked, shortlist, strict=True), key=lambda item: item[0], reverse=True)[
        :limit
    ]
    return [
        SearchDraft(
            citation=CitationResponse(
                document_id=document.document_id,
                chunk_id=chunk.chunk_id,
                title=document.title,
                source_name=document.source_name,
                source_url=document.source_url,
                document_layer=document.document_layer,
                data_mode=document.data_mode,
            ),
            excerpt=chunk.content[:500],
            score=float(score),
            external_processing_allowed=document.external_processing_allowed,
            full_content=chunk.content,
            captured_at=document.captured_at,
        )
        for score, (_initial, chunk, document) in ordered
    ]


def _build_policy_watch(
    *,
    limit: int,
    embedding_client: EmbeddingClient,
    session: Session,
) -> tuple[PolicyWatchResponse, list[SearchDraft]]:
    drafts = _policy_watch_drafts(
        limit=limit,
        embedding_client=embedding_client,
        session=session,
    )
    items = [_to_policy_watch_item(draft) for draft in drafts]
    missing = [] if items else ["No local policy knowledge chunks are available for policy watch."]
    response = PolicyWatchResponse(
        generated_at=_now(),
        items=items,
        missing_information=missing,
        excluded_restricted_chunks=sum(
            1 for draft in drafts if not draft.external_processing_allowed
        ),
        local_only=True,
        no_auto_trading=True,
    )
    return response, drafts


def _policy_watch_drafts(
    *,
    limit: int,
    embedding_client: EmbeddingClient,
    session: Session,
) -> list[SearchDraft]:
    candidates: list[SearchDraft] = []
    seen_chunk_ids: set[str] = set()
    per_query_limit = max(limit * 3, limit)
    for query in POLICY_WATCH_QUERIES:
        for draft in _search_drafts(
            query,
            limit=per_query_limit,
            embedding_client=embedding_client,
            session=session,
        ):
            if draft.citation.chunk_id in seen_chunk_ids:
                continue
            if not _is_policy_watch_draft(draft):
                continue
            seen_chunk_ids.add(draft.citation.chunk_id)
            candidates.append(draft)
    candidates.sort(
        key=lambda draft: (
            _policy_layer_priority(draft.citation.document_layer),
            -draft.score,
            -draft.captured_at.timestamp(),
        )
    )
    return candidates[:limit]


def _is_policy_watch_draft(draft: SearchDraft) -> bool:
    if draft.citation.document_layer not in POLICY_WATCH_ALLOWED_LAYERS:
        return False
    haystack = " ".join(
        (
            draft.citation.title,
            draft.citation.source_name,
            draft.citation.source_url or "",
            draft.citation.document_layer,
            draft.citation.data_mode,
            draft.full_content[:300],
        )
    ).lower()
    return not any(marker in haystack for marker in POLICY_WATCH_RESEARCH_MARKERS)


def _policy_layer_priority(document_layer: str) -> int:
    if document_layer == "official_policy":
        return 0
    if document_layer == "official_market_notice":
        return 1
    if document_layer == "public_research":
        return 2
    return 9


def _policy_source_role(
    document_layer: str,
) -> Literal["official_policy", "official_market_notice", "supplemental_research"]:
    if document_layer == "official_policy":
        return "official_policy"
    if document_layer == "official_market_notice":
        return "official_market_notice"
    return "supplemental_research"


def _policy_observation(draft: SearchDraft) -> str:
    if draft.citation.document_layer == "public_research":
        return "Supplemental public research evidence for operator review."
    if draft.citation.document_layer == "official_market_notice":
        return "Official market notice evidence for operator review."
    return "Official policy evidence for operator review."


def _to_policy_watch_item(draft: SearchDraft) -> PolicyWatchItemResponse:
    return PolicyWatchItemResponse(
        watch_id=draft.citation.chunk_id,
        title=draft.citation.title,
        observation=_policy_observation(draft),
        excerpt=draft.excerpt,
        citation=draft.citation,
        captured_at=draft.captured_at,
        source_role=_policy_source_role(draft.citation.document_layer),
        external_processing_allowed=draft.external_processing_allowed,
        score=draft.score,
    )


def _question_prompt(question: str, drafts: list[SearchDraft]) -> str:
    evidence = [
        {"citation": draft.citation.model_dump(mode="json"), "content": draft.full_content}
        for draft in drafts
    ]
    serialized = json.dumps(evidence, ensure_ascii=False)
    return (
        "Answer only from evidence. Return JSON with answer. "
        f"Question: {question}\nEvidence: {serialized}"
    )


def _brief_prompt(
    facts: dict[str, object],
    missing: list[str],
    authorized_policy_watch: list[SearchDraft],
) -> str:
    serialized_facts = json.dumps(_sanitized_brief_facts(facts), ensure_ascii=False)
    serialized_missing = json.dumps(missing, ensure_ascii=False)
    serialized_policy_watch = json.dumps(
        [
            {"citation": draft.citation.model_dump(mode="json"), "content": draft.full_content}
            for draft in authorized_policy_watch
        ],
        ensure_ascii=False,
    )
    return (
        "Explain this daily market research brief. Return JSON with summary, risks, "
        "and optional policy_watch. Use only Authorized policy watch evidence for "
        "policy interpretation. Facts contain local-only citation metadata and may "
        "include unauthorized chunks whose body text is intentionally excluded. "
        f"Facts: {serialized_facts} Missing: {serialized_missing} "
        f"Authorized policy watch evidence: {serialized_policy_watch}"
    )


def _sanitized_brief_facts(facts: dict[str, object]) -> dict[str, object]:
    sanitized = dict(facts)
    policy_watch = facts.get("policy_watch")
    if isinstance(policy_watch, dict):
        items = policy_watch.get("items")
        sanitized["policy_watch"] = {
            "item_count": policy_watch.get("item_count", 0),
            "excluded_restricted_chunks": policy_watch.get("excluded_restricted_chunks", 0),
            "local_only": True,
            "items": [
                _sanitized_policy_watch_item(item) for item in items if isinstance(item, dict)
            ]
            if isinstance(items, list)
            else [],
        }
    return sanitized


def _sanitized_policy_watch_item(item: dict[object, object]) -> dict[str, object]:
    citation = item.get("citation")
    return {
        "watch_id": item.get("watch_id"),
        "title": item.get("title"),
        "observation": item.get("observation"),
        "citation": citation if isinstance(citation, dict) else {},
        "captured_at": item.get("captured_at"),
        "source_role": item.get("source_role"),
        "external_processing_allowed": item.get("external_processing_allowed"),
        "score": item.get("score"),
    }


def _fallback_answer(drafts: list[SearchDraft]) -> str:
    return "DeepSeek is unavailable. Review the cited local evidence: " + " ".join(
        draft.excerpt for draft in drafts[:2]
    )


def _brief_missing_information(facts: dict[str, object]) -> list[str]:
    missing: list[str] = []
    if facts["weather_snapshot_count"] == 0:
        missing.append("No weather feature snapshot is available.")
    if facts["knowledge_document_count"] == 0:
        missing.append("No policy or research document is available.")
    return missing


def _fallback_brief_narrative(facts: dict[str, object], missing: list[str]) -> dict[str, object]:
    return {
        "summary": "Deterministic local brief generated for operator review.",
        "risks": missing,
        "facts": facts,
        "policy_watch": _fallback_policy_watch_narrative(_policy_watch_items_from_facts(facts)),
    }


def _fallback_policy_watch_narrative(
    items: list[PolicyWatchItemResponse],
) -> list[dict[str, object]]:
    return [
        {
            "title": item.title,
            "observation": item.observation,
            "source_name": item.citation.source_name,
            "source_role": item.source_role,
            "external_processing_allowed": item.external_processing_allowed,
            "citation": item.citation.model_dump(mode="json"),
        }
        for item in items
    ]


def _policy_watch_items_from_facts(facts: dict[str, object]) -> list[PolicyWatchItemResponse]:
    policy_watch = facts.get("policy_watch")
    if not isinstance(policy_watch, dict):
        return []
    items = policy_watch.get("items")
    if not isinstance(items, list):
        return []
    parsed: list[PolicyWatchItemResponse] = []
    for item in items:
        if isinstance(item, dict):
            parsed.append(PolicyWatchItemResponse.model_validate(item))
    return parsed


def _policy_watch_count(brief: IntelligenceBrief) -> int:
    policy_watch = brief.deterministic_facts_json.get("policy_watch")
    if not isinstance(policy_watch, dict):
        return 0
    item_count = policy_watch.get("item_count")
    if isinstance(item_count, int):
        return item_count
    items = policy_watch.get("items")
    return len(items) if isinstance(items, list) else 0


def _to_brief_summary(brief: IntelligenceBrief) -> IntelligenceBriefSummaryResponse:
    return IntelligenceBriefSummaryResponse(
        brief_id=brief.brief_id,
        target_date=brief.target_date,
        generated_at=brief.generated_at,
        human_review_status=brief.human_review_status,
        risk_level=brief.risk_level,
        confidence_score=brief.confidence_score,
        policy_watch_count=_policy_watch_count(brief),
        missing_information_count=len(brief.missing_information_json),
        llm_used=brief.llm_used,
        no_auto_trading=brief.no_auto_trading,
    )


def _to_brief_response(brief: IntelligenceBrief) -> IntelligenceBriefResponse:
    return IntelligenceBriefResponse(
        brief_id=brief.brief_id,
        target_date=brief.target_date,
        generated_at=brief.generated_at,
        status=brief.status,
        human_review_status=brief.human_review_status,
        risk_level=brief.risk_level,
        confidence_score=brief.confidence_score,
        deterministic_facts=brief.deterministic_facts_json,
        narrative=brief.narrative_json,
        citations=brief.citations_json,
        policy_watch=_policy_watch_items_from_facts(brief.deterministic_facts_json),
        missing_information=brief.missing_information_json,
        llm_used=brief.llm_used,
        llm_model=brief.llm_model,
        no_auto_trading=brief.no_auto_trading,
    )


def _to_brief_detail(
    brief: IntelligenceBrief, *, session: Session
) -> IntelligenceBriefDetailResponse:
    response = _to_brief_response(brief)
    reviews = [
        IntelligenceBriefReviewResponse.model_validate(review, from_attributes=True)
        for review in list_brief_reviews(session, brief.brief_id)
    ]
    return IntelligenceBriefDetailResponse(**response.model_dump(), reviews=reviews)
