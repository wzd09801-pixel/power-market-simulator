from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.knowledge import get_blob_store
from backend.app.services.deepseek import DeepSeekProviderError, get_deepseek_client
from backend.app.services.embeddings import HashEmbeddingClient, get_embedding_client
from backend.app.storage.blob_store import MemoryBlobStore


class FakeDeepSeekClient:
    prompts: list[str] = []

    def complete_json(self, *, prompt: str, deep_analysis: bool) -> tuple[dict[str, object], str]:
        self.__class__.prompts.append(prompt)
        return {"answer": "Evidence-backed answer.", "summary": "Daily summary.", "risks": []}, (
            "deepseek-v4-pro" if deep_analysis else "deepseek-v4-flash"
        )


class FailingDeepSeekClient:
    def complete_json(self, *, prompt: str, deep_analysis: bool) -> tuple[dict[str, object], str]:
        del prompt, deep_analysis
        raise DeepSeekProviderError("offline")


@pytest.fixture
def intelligence_client(client: TestClient) -> Iterator[TestClient]:
    app = client.app
    assert isinstance(app, FastAPI)
    store = MemoryBlobStore()
    FakeDeepSeekClient.prompts = []
    app.dependency_overrides[get_blob_store] = lambda: store
    app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    app.dependency_overrides[get_deepseek_client] = lambda: FakeDeepSeekClient()
    yield client


def _upload(
    client: TestClient,
    *,
    title: str,
    content: str,
    document_layer: str = "official_policy",
    source_name: str = "Official source",
    source_url: str | None = None,
) -> dict[str, object]:
    form_data = {
        "title": title,
        "document_layer": document_layer,
        "source_name": source_name,
    }
    if source_url is not None:
        form_data["source_url"] = source_url
    response = client.post(
        "/v1/policy/documents/upload",
        data=form_data,
        files={"file": ("notice.txt", content, "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_question_excludes_restricted_chunks_until_explicit_authorization(
    intelligence_client: TestClient,
) -> None:
    document = _upload(intelligence_client, title="Market notice", content="market risk adjustment")
    restricted = intelligence_client.post(
        "/v1/intelligence/questions",
        json={"question": "market risk", "analysis_mode": "simple"},
    )
    intelligence_client.post(
        f"/v1/policy/documents/{document['document_id']}/external-processing-authorization",
        json={"external_processing_allowed": True, "note": "Reviewed official public notice."},
    )
    allowed = intelligence_client.post(
        "/v1/intelligence/questions",
        json={"question": "market risk", "analysis_mode": "deep"},
    )

    assert restricted.status_code == 200
    assert restricted.json()["llm_used"] is False
    assert restricted.json()["excluded_restricted_chunks"] == 1
    assert allowed.status_code == 200
    assert allowed.json()["llm_used"] is True
    assert allowed.json()["llm_model"] == "deepseek-v4-pro"
    assert allowed.json()["citations"][0]["document_id"] == document["document_id"]
    assert allowed.json()["citations"][0]["source_name"] == "Official source"
    assert allowed.json()["citations"][0]["data_mode"] == "public_observed"


def test_brief_generation_falls_back_and_remains_human_reviewed(
    intelligence_client: TestClient,
) -> None:
    app = intelligence_client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_deepseek_client] = lambda: FailingDeepSeekClient()

    generated = intelligence_client.post("/v1/intelligence/briefs/generate", json={})
    latest = intelligence_client.get("/v1/intelligence/briefs/latest")
    brief_id = generated.json()["brief_id"]
    review = intelligence_client.post(
        f"/v1/intelligence/briefs/{brief_id}/reviews",
        json={"review_status": "needs_revision", "note": "Collect missing evidence."},
    )

    assert generated.status_code == 200
    assert generated.json()["llm_used"] is False
    assert generated.json()["no_auto_trading"] is True
    assert (
        generated.json()["deterministic_facts"]["bench_dispatch_benchmark"]["usage_scope"]
        == "research_only"
    )
    assert latest.json()["brief_id"] == brief_id
    assert review.status_code == 200
    assert review.json()["review_status"] == "needs_revision"


def test_brief_list_is_empty_without_generated_briefs(
    intelligence_client: TestClient,
) -> None:
    response = intelligence_client.get("/v1/intelligence/briefs")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_brief_list_detail_and_review_history_are_auditable(
    intelligence_client: TestClient,
) -> None:
    first = intelligence_client.post(
        "/v1/intelligence/briefs/generate", json={"target_date": "2026-06-01"}
    )
    second = intelligence_client.post(
        "/v1/intelligence/briefs/generate", json={"target_date": "2026-06-02"}
    )
    review = intelligence_client.post(
        f"/v1/intelligence/briefs/{second.json()['brief_id']}/reviews",
        json={"review_status": "approved", "note": "Reviewed for local research use."},
    )
    listing = intelligence_client.get("/v1/intelligence/briefs?limit=10")
    detail = intelligence_client.get(f"/v1/intelligence/briefs/{second.json()['brief_id']}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert review.status_code == 200
    assert listing.status_code == 200
    assert [item["brief_id"] for item in listing.json()["items"]] == [
        second.json()["brief_id"],
        first.json()["brief_id"],
    ]
    assert listing.json()["items"][0]["human_review_status"] == "approved"
    assert listing.json()["items"][0]["policy_watch_count"] == 0
    assert listing.json()["items"][0]["missing_information_count"] >= 1
    assert detail.status_code == 200
    assert detail.json()["brief_id"] == second.json()["brief_id"]
    assert detail.json()["human_review_status"] == "approved"
    assert detail.json()["reviews"][0]["review_status"] == "approved"
    assert detail.json()["reviews"][0]["note"] == "Reviewed for local research use."
    assert detail.json()["no_auto_trading"] is True


def test_missing_brief_detail_and_review_return_stable_error(
    intelligence_client: TestClient,
) -> None:
    detail = intelligence_client.get("/v1/intelligence/briefs/brief_missing")
    review = intelligence_client.post(
        "/v1/intelligence/briefs/brief_missing/reviews",
        json={"review_status": "needs_revision", "note": "Missing brief."},
    )

    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "intelligence_brief_not_found"
    assert review.status_code == 404
    assert review.json()["error"]["code"] == "intelligence_brief_not_found"


def test_empty_policy_watch_still_allows_brief_generation(
    intelligence_client: TestClient,
) -> None:
    watch = intelligence_client.get("/v1/intelligence/policy-watch")
    generated = intelligence_client.post("/v1/intelligence/briefs/generate", json={})

    assert watch.status_code == 200
    assert watch.json()["items"] == []
    assert watch.json()["local_only"] is True
    assert watch.json()["no_auto_trading"] is True
    assert watch.json()["missing_information"] == [
        "No local policy knowledge chunks are available for policy watch."
    ]
    assert generated.status_code == 200
    assert generated.json()["policy_watch"] == []
    assert generated.json()["deterministic_facts"]["policy_watch"]["item_count"] == 0


def test_policy_watch_excludes_unauthorized_body_from_deepseek_prompt(
    intelligence_client: TestClient,
) -> None:
    document = _upload(
        intelligence_client,
        title="Unauthorized official policy",
        content="restricted policy body market rule risk adjustment",
        source_url="https://official.example/policy",
    )

    watch = intelligence_client.get("/v1/intelligence/policy-watch")
    generated = intelligence_client.post("/v1/intelligence/briefs/generate", json={})

    assert watch.status_code == 200
    assert watch.json()["items"][0]["citation"]["document_id"] == document["document_id"]
    assert watch.json()["items"][0]["external_processing_allowed"] is False
    assert watch.json()["items"][0]["source_role"] == "official_policy"
    assert watch.json()["excluded_restricted_chunks"] == 1
    assert generated.status_code == 200
    assert generated.json()["policy_watch"][0]["citation"]["document_id"] == document["document_id"]
    assert generated.json()["citations"][0]["document_id"] == document["document_id"]
    assert (
        generated.json()["deterministic_facts"]["policy_watch"]["excluded_restricted_chunks"] == 1
    )
    assert "restricted policy body" not in FakeDeepSeekClient.prompts[-1]
    assert "Unauthorized official policy" in FakeDeepSeekClient.prompts[-1]


def test_authorized_policy_watch_enters_prompt_and_research_is_supplemental(
    intelligence_client: TestClient,
) -> None:
    document = _upload(
        intelligence_client,
        title="Authorized official market policy",
        content="authorized policy body market settlement rule impact",
        source_url="https://official.example/authorized",
    )
    _upload(
        intelligence_client,
        title="Supplemental public research",
        content="public research market trading hydro impact",
        document_layer="public_research",
        source_name="Research institute",
        source_url="https://research.example/report",
    )
    intelligence_client.post(
        f"/v1/policy/documents/{document['document_id']}/external-processing-authorization",
        json={"external_processing_allowed": True, "note": "Reviewed official public notice."},
    )

    watch = intelligence_client.get("/v1/intelligence/policy-watch?limit=5")
    generated = intelligence_client.post("/v1/intelligence/briefs/generate", json={})

    assert watch.status_code == 200
    roles = {item["title"]: item["source_role"] for item in watch.json()["items"]}
    assert roles["Authorized official market policy"] == "official_policy"
    assert roles["Supplemental public research"] == "supplemental_research"
    assert generated.status_code == 200
    assert generated.json()["llm_used"] is True
    assert generated.json()["policy_watch"][0]["citation"]["source_name"] == "Official source"
    assert "authorized policy body" in FakeDeepSeekClient.prompts[-1]


def test_bench_research_only_documents_do_not_enter_policy_watch(
    intelligence_client: TestClient,
) -> None:
    _upload(
        intelligence_client,
        title="BENCH research_only benchmark",
        content="BENCH research_only dispatch benchmark market price body",
        document_layer="public_research",
        source_name="BENCH",
        source_url="https://bench.example/dispatch",
    )

    watch = intelligence_client.get("/v1/intelligence/policy-watch")
    generated = intelligence_client.post("/v1/intelligence/briefs/generate", json={})

    assert watch.status_code == 200
    assert watch.json()["items"] == []
    assert generated.status_code == 200
    assert generated.json()["policy_watch"] == []
    assert generated.json()["citations"] == []
