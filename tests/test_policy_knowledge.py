from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.routes.knowledge import get_blob_store
from backend.app.models.knowledge import (
    KnowledgeAuthorizationAudit,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentReview,
    KnowledgeDocumentVersion,
)
from backend.app.models.market import MarketDataSource, MarketRawArtifact, MarketSourceEndpoint
from backend.app.models.operations import RawObject
from backend.app.services.deepseek import get_deepseek_client
from backend.app.services.embeddings import HashEmbeddingClient, get_embedding_client
from backend.app.storage.blob_store import MemoryBlobStore

CAPTURED_AT = datetime(2026, 6, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class FakeDeepSeekClient:
    def complete_json(self, *, prompt: str, deep_analysis: bool) -> tuple[dict[str, object], str]:
        del prompt, deep_analysis
        return {"answer": "Evidence-backed policy answer."}, "deepseek-v4-flash"


@pytest.fixture
def knowledge_client(client: TestClient) -> Iterator[TestClient]:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_blob_store] = lambda: MemoryBlobStore()
    app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    app.dependency_overrides[get_deepseek_client] = lambda: FakeDeepSeekClient()
    yield client


def test_empty_corpus_overview_warns_without_fetching(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get("/v1/policy/corpus/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["document_count"] == 0
    assert payload["chunk_count"] == 0
    assert payload["artifact_provenance_count"] == 0
    assert payload["network_probe_performed"] is False
    assert payload["fetch_performed"] is False
    assert payload["no_auto_trading"] is True


def test_upload_preserves_chunks_and_defaults_to_local_only(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    response = knowledge_client.post(
        "/v1/policy/documents/upload",
        data={"title": "Operator notes", "document_layer": "user_uploaded"},
        files={"file": ("notes.txt", "local research notes", "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_layer"] == "user_uploaded"
    assert payload["data_mode"] == "user_uploaded"
    assert payload["external_processing_allowed"] is False
    chunks = knowledge_client.get(f"/v1/policy/documents/{payload['document_id']}/chunks")
    assert chunks.status_code == 200
    assert chunks.json()["items"][0]["content"] == "local research notes"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeChunk)) == 1


def test_external_processing_authorization_is_explicit_and_audited(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    upload = knowledge_client.post(
        "/v1/policy/documents/upload",
        data={"title": "Public notice", "document_layer": "official_market_notice"},
        files={"file": ("notice.md", "# notice\npublic details", "text/markdown")},
    ).json()
    response = knowledge_client.post(
        f"/v1/policy/documents/{upload['document_id']}/external-processing-authorization",
        json={"external_processing_allowed": True, "note": "Reviewed public official notice."},
    )

    assert response.status_code == 200
    assert response.json()["external_processing_allowed"] is True
    documents = knowledge_client.get("/v1/policy/documents").json()["items"]
    assert documents[0]["external_processing_allowed"] is True
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeAuthorizationAudit)) == 1


def test_policy_document_review_updates_status_without_authorizing_external_processing(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    upload = knowledge_client.post(
        "/v1/policy/documents/upload",
        data={"title": "Reviewable policy", "document_layer": "official_policy"},
        files={"file": ("policy.txt", "official policy body", "text/plain")},
    ).json()

    response = knowledge_client.post(
        f"/v1/policy/documents/{upload['document_id']}/reviews",
        json={"review_status": "approved", "note": "Reviewed local policy provenance."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == upload["document_id"]
    assert payload["review_status"] == "approved"
    assert payload["note"] == "Reviewed local policy provenance."
    detail = knowledge_client.get(f"/v1/policy/documents/{upload['document_id']}")
    assert detail.json()["human_review_status"] == "approved"
    assert detail.json()["external_processing_allowed"] is False
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeDocumentReview)) == 1
        assert session.scalar(select(func.count()).select_from(KnowledgeAuthorizationAudit)) == 0


def test_policy_document_review_rejects_blank_note_and_missing_document(
    knowledge_client: TestClient,
) -> None:
    blank = knowledge_client.post(
        "/v1/policy/documents/missing/reviews",
        json={"review_status": "needs_revision", "note": "   "},
    )
    missing = knowledge_client.post(
        "/v1/policy/documents/missing/reviews",
        json={"review_status": "needs_revision", "note": "Missing document."},
    )

    assert blank.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "knowledge_document_not_found"


def test_policy_document_review_package_is_read_only(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    upload = knowledge_client.post(
        "/v1/policy/documents/upload",
        data={"title": "Review package policy", "document_layer": "official_policy"},
        files={
            "file": (
                "policy.txt",
                "official policy body for local operator review package",
                "text/plain",
            )
        },
    ).json()
    with db_session_factory() as session:
        before_counts = _knowledge_table_counts(session)

    response = knowledge_client.get(f"/v1/policy/documents/{upload['document_id']}/review-package")

    assert response.status_code == 200
    payload = response.json()
    assert payload["package_version"] == "policy_document_review_package_v1"
    assert payload["document"]["document_id"] == upload["document_id"]
    assert payload["document"]["document_layer"] == "official_policy"
    assert payload["document"]["raw_download_available"] is False
    assert payload["chunk_summary"] == {
        "total_count": 1,
        "embedded_count": 1,
        "embedding_coverage": 1.0,
        "displayed_chunk_count": 1,
    }
    assert payload["displayed_chunks"][0]["content_excerpt"] == (
        "official policy body for local operator review package"
    )
    assert payload["displayed_chunks"][0]["content_sha256"]
    assert payload["review_count"] == 0
    assert payload["reviews"] == []
    assert payload["external_processing_allowed"] is False
    assert payload["raw_payload_included"] is False
    assert payload["server_artifact_written"] is False
    assert payload["no_auto_trading"] is True
    assert payload["recommendation_chain_isolated"] is True
    assert payload["network_probe_performed"] is False
    assert payload["fetch_performed"] is False
    assert payload["external_model_call_performed"] is False
    assert "parsed_text" not in payload["document"]
    with db_session_factory() as session:
        assert _knowledge_table_counts(session) == before_counts


def test_policy_document_review_package_includes_reviews_and_authorization_state(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    upload = knowledge_client.post(
        "/v1/policy/documents/upload",
        data={"title": "Reviewed policy", "document_layer": "official_market_notice"},
        files={"file": ("notice.txt", "official notice body", "text/plain")},
    ).json()
    authorization = knowledge_client.post(
        f"/v1/policy/documents/{upload['document_id']}/external-processing-authorization",
        json={
            "external_processing_allowed": True,
            "note": "Reviewed public notice for external processing.",
        },
    )
    review = knowledge_client.post(
        f"/v1/policy/documents/{upload['document_id']}/reviews",
        json={"review_status": "approved", "note": "Reviewed document provenance."},
    )
    assert authorization.status_code == 200
    assert review.status_code == 200
    with db_session_factory() as session:
        before_counts = _knowledge_table_counts(session)

    response = knowledge_client.get(f"/v1/policy/documents/{upload['document_id']}/review-package")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document"]["human_review_status"] == "approved"
    assert payload["external_processing_allowed"] is True
    assert payload["external_processing_allowed_default"] is False
    assert payload["review_count"] == 1
    assert payload["reviews"][0]["review_status"] == "approved"
    assert payload["reviews"][0]["note"] == "Reviewed document provenance."
    assert payload["no_auto_trading"] is True
    assert payload["recommendation_chain_isolated"] is True
    with db_session_factory() as session:
        assert _knowledge_table_counts(session) == before_counts


def test_policy_document_review_package_missing_document_returns_error(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get("/v1/policy/documents/missing/review-package")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "knowledge_document_not_found"


def test_import_html_market_artifact_preserves_source_and_chunks(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_policy_html"
    source_url = "https://policy.example.invalid/hdhy/zlxz/policy.html"
    inline_text = "<html><body><h1>Official Policy</h1><p>market policy body</p></body></html>"
    with db_session_factory.begin() as session:
        _add_market_artifact(
            session,
            artifact_id=artifact_id,
            source_url=source_url,
            title="Official policy page",
            inline_text=inline_text,
            media_type="text/html",
        )

    response = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Official policy page"
    assert payload["document_layer"] == "official_policy"
    assert payload["trust_tier"] == "official"
    assert payload["source_name"] == (
        "Example Energy Regulator / Southern regulator public downloads"
    )
    assert payload["source_url"] == source_url
    assert payload["media_type"] == "text/html"
    assert payload["external_processing_allowed"] is False
    assert payload["data_mode"] == "public_observed"
    chunks = knowledge_client.get(f"/v1/policy/documents/{payload['document_id']}/chunks")
    assert chunks.status_code == 200
    assert "market policy body" in chunks.json()["items"][0]["content"]

    with db_session_factory() as session:
        document = session.get(KnowledgeDocument, payload["document_id"])
        assert document is not None
        assert document.captured_at == CAPTURED_AT.replace(tzinfo=None)
        version = session.scalar(
            select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.document_id == payload["document_id"]
            )
        )
        assert version is not None
        assert version.content_sha256 == sha256(inline_text.encode("utf-8")).hexdigest()
        raw_object = session.get(RawObject, version.raw_object_id)
        assert raw_object is not None
        assert raw_object.source_url == source_url
        assert raw_object.metadata_json["ingestion_bridge"] == "market_raw_artifact"
        assert raw_object.metadata_json["artifact_id"] == artifact_id
        assert raw_object.metadata_json["source_id"] == "southern_energy_regulator"
        assert raw_object.metadata_json["endpoint_id"] == "southern_regulator_downloads"
        imports = raw_object.metadata_json["market_artifact_imports"]
        assert isinstance(imports, list)
        assert imports[0]["artifact_id"] == artifact_id


def test_corpus_overview_document_detail_and_citations_preserve_artifact_provenance(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_policy_corpus"
    source_url = "https://policy.example.invalid/hdhy/zlxz/corpus-policy.html"
    inline_text = "<html><body><h1>Corpus Policy</h1><p>market policy body</p></body></html>"
    upload = knowledge_client.post(
        "/v1/policy/documents/upload",
        data={"title": "Local operator notes", "document_layer": "user_uploaded"},
        files={"file": ("notes.txt", "local operator notes", "text/plain")},
    )
    with db_session_factory.begin() as session:
        _add_market_artifact(
            session,
            artifact_id=artifact_id,
            source_url=source_url,
            title="Corpus policy page",
            inline_text=inline_text,
            media_type="text/html",
        )
    imported = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert upload.status_code == 200
    assert imported.status_code == 200
    document_id = imported.json()["document_id"]
    overview = knowledge_client.get("/v1/policy/corpus/overview").json()
    layers = {layer["document_layer"]: layer for layer in overview["layers"]}

    assert overview["status"] == "healthy"
    assert overview["document_count"] == 2
    assert overview["version_count"] == 2
    assert overview["chunk_count"] == 2
    assert overview["embedded_chunk_count"] == 2
    assert overview["artifact_provenance_count"] == 1
    assert layers["official_policy"]["document_count"] == 1
    assert layers["user_uploaded"]["document_count"] == 1

    detail = knowledge_client.get(f"/v1/policy/documents/{document_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert (
        detail_payload["latest_version"]["content_sha256"]
        == sha256(inline_text.encode("utf-8")).hexdigest()
    )
    assert (
        detail_payload["raw_object"]["content_sha256"]
        == detail_payload["latest_version"]["content_sha256"]
    )
    assert detail_payload["chunk_count"] == 1
    assert detail_payload["embedded_chunk_count"] == 1
    assert detail_payload["external_processing_allowed_default"] is False
    assert detail_payload["raw_download_available"] is False
    assert detail_payload["artifact_provenance"][0]["artifact_id"] == artifact_id
    assert detail_payload["artifact_provenance"][0]["source_id"] == "southern_energy_regulator"
    assert detail_payload["artifact_provenance"][0]["endpoint_id"] == (
        "southern_regulator_downloads"
    )

    search = knowledge_client.post(
        "/v1/intelligence/search",
        json={"query": "market policy body", "limit": 3},
    )
    assert search.status_code == 200
    citation = search.json()["items"][0]["citation"]
    assert citation["document_id"] == document_id
    assert citation["source_name"] == (
        "Example Energy Regulator / Southern regulator public downloads"
    )
    assert citation["data_mode"] == "public_observed"

    restricted = knowledge_client.post(
        "/v1/intelligence/questions",
        json={"question": "market policy body", "analysis_mode": "simple"},
    )
    assert restricted.status_code == 200
    assert restricted.json()["citations"] == []
    assert restricted.json()["excluded_restricted_chunks"] >= 1

    authorization = knowledge_client.post(
        f"/v1/policy/documents/{document_id}/external-processing-authorization",
        json={"external_processing_allowed": True, "note": "Reviewed public official notice."},
    )
    assert authorization.status_code == 200
    allowed = knowledge_client.post(
        "/v1/intelligence/questions",
        json={"question": "market policy body", "analysis_mode": "simple"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["citations"][0]["document_id"] == document_id
    assert allowed.json()["citations"][0]["source_name"] == citation["source_name"]


def test_import_text_market_artifact_as_public_research(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_research_txt"
    with db_session_factory.begin() as session:
        _add_market_artifact(
            session,
            artifact_id=artifact_id,
            source_id="example_electricity_council",
            endpoint_id="council_home",
            source_name="Example Electricity Council",
            endpoint_name="COUNCIL public website",
            source_url="https://council.example.invalid/report.txt",
            market_scope="national_industry_research",
            trust_tier="industry_association",
            endpoint_kind="public_frontend",
            data_granularity="industry_research",
            media_type="text/plain",
            inline_text="industry research body",
        )

    response = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_layer"] == "public_research"
    chunks = knowledge_client.get(f"/v1/policy/documents/{payload['document_id']}/chunks")
    assert chunks.json()["items"][0]["content"] == "industry research body"


def test_import_unknown_market_artifact_is_rejected(knowledge_client: TestClient) -> None:
    response = knowledge_client.post(
        "/v1/policy/documents/from-market-artifact/market_artifact_missing"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "market_raw_artifact_not_found"


def test_import_market_artifact_rejects_empty_content(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_empty"
    with db_session_factory.begin() as session:
        _add_market_artifact(session, artifact_id=artifact_id, inline_text=None)

    response = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "market_artifact_not_usable"


def test_import_market_artifact_rejects_unsupported_media_type(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_json"
    with db_session_factory.begin() as session:
        _add_market_artifact(
            session,
            artifact_id=artifact_id,
            media_type="application/json",
            inline_text='{"body":"not a policy document"}',
        )

    response = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "market_artifact_not_usable"


def test_import_market_artifact_reuses_duplicate_sha256_document(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_duplicate"
    with db_session_factory.begin() as session:
        _add_market_artifact(session, artifact_id=artifact_id)

    first = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")
    second = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["document_id"] == first.json()["document_id"]
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 1
        assert session.scalar(select(func.count()).select_from(KnowledgeDocumentVersion)) == 1
        assert session.scalar(select(func.count()).select_from(KnowledgeChunk)) == 1


def test_import_market_artifact_keeps_distinct_document_when_upload_has_same_sha256(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_same_as_upload"
    inline_text = "<html><body>same public body</body></html>"
    upload = knowledge_client.post(
        "/v1/policy/documents/upload",
        data={"title": "Local copy", "document_layer": "user_uploaded"},
        files={"file": ("same.html", inline_text, "text/html")},
    ).json()
    with db_session_factory.begin() as session:
        _add_market_artifact(
            session,
            artifact_id=artifact_id,
            title="Official preserved copy",
            inline_text=inline_text,
        )

    response = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] != upload["document_id"]
    assert payload["document_layer"] == "official_policy"
    assert payload["source_name"] == (
        "Example Energy Regulator / Southern regulator public downloads"
    )
    upload_detail = knowledge_client.get(f"/v1/policy/documents/{upload['document_id']}")
    artifact_detail = knowledge_client.get(f"/v1/policy/documents/{payload['document_id']}")
    assert upload_detail.status_code == 200
    assert artifact_detail.status_code == 200
    assert upload_detail.json()["artifact_provenance"] == []
    assert artifact_detail.json()["artifact_provenance"][0]["artifact_id"] == artifact_id
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 2
        assert session.scalar(select(func.count()).select_from(RawObject)) == 1
        raw_object = session.scalar(select(RawObject))
        assert raw_object is not None
        assert raw_object.metadata_json["filename"] == "same.html"
        imports = raw_object.metadata_json["market_artifact_imports"]
        assert isinstance(imports, list)
        assert imports[0]["artifact_id"] == artifact_id


def test_import_market_artifact_rejects_content_hash_mismatch(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_hash_mismatch"
    with db_session_factory.begin() as session:
        _add_market_artifact(
            session,
            artifact_id=artifact_id,
            inline_text="<html><body>changed body</body></html>",
            content_sha256="0" * 64,
        )

    response = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "market_artifact_not_usable"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 0


def test_import_market_artifact_rejects_bench_or_research_only_artifact(
    knowledge_client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    artifact_id = "market_artifact_bench"
    with db_session_factory.begin() as session:
        _add_market_artifact(
            session,
            artifact_id=artifact_id,
            source_id="bench_dispatch_research",
            endpoint_id="bench_dispatch_archive",
            source_name="BENCH",
            endpoint_name="BENCH dispatch archive",
            source_url="https://operator.benchmark.example.invalid/example.html",
            market_scope="bench_nem_dispatch_benchmark",
            endpoint_kind="research_benchmark",
            data_granularity="research_only",
            notes="research_only benchmark; not Example Province policy",
            inline_text="<html><body>BENCH benchmark</body></html>",
        )

    response = knowledge_client.post(f"/v1/policy/documents/from-market-artifact/{artifact_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "market_artifact_not_usable"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 0


def _add_market_artifact(
    session: Session,
    *,
    artifact_id: str,
    source_id: str = "southern_energy_regulator",
    endpoint_id: str = "southern_regulator_downloads",
    source_name: str = "Example Energy Regulator",
    endpoint_name: str = "Southern regulator public downloads",
    source_url: str = "https://policy.example.invalid/hdhy/zlxz/example.html",
    title: str | None = "Policy artifact",
    market_scope: str = "southern_regional_policy",
    trust_tier: str = "official",
    endpoint_kind: str = "html_listing",
    data_granularity: str = "policy_documents",
    notes: str = "Official policy candidate.",
    media_type: str = "text/html",
    inline_text: str | None = "<html><body>policy body</body></html>",
    data_mode: str = "public_observed",
    content_sha256: str | None = None,
) -> None:
    content = inline_text.encode("utf-8") if inline_text is not None else b""
    session.add(
        MarketDataSource(
            source_id=source_id,
            name=source_name,
            operator_name=source_name,
            official_url=source_url.rsplit("/", 1)[0] + "/",
            market_scope=market_scope,
            notes=notes,
            data_mode="public_derived",
            trust_tier=trust_tier,
            attribution_text=source_name,
            collection_permission_note="Preserve attribution and source URL.",
        )
    )
    session.add(
        MarketSourceEndpoint(
            endpoint_id=endpoint_id,
            source_id=source_id,
            name=endpoint_name,
            canonical_url=source_url,
            endpoint_kind=endpoint_kind,
            allowed_domains_json=[
                "policy.example.invalid",
                "council.example.invalid",
                "operator.benchmark.example.invalid",
            ],
            visibility_scope="internet_public",
            access_mode="anonymous_https",
            lifecycle_status="verified",
            content_formats_json=[media_type],
            data_granularity=data_granularity,
            adapter_key="registered_static_http:v1",
            parser_key=None,
            parser_version=None,
            health_check_enabled=False,
            manual_submission_enabled=True,
            collection_enabled=False,
            cadence=None,
            notes=notes,
        )
    )
    session.add(
        MarketRawArtifact(
            artifact_id=artifact_id,
            source_id=source_id,
            endpoint_id=endpoint_id,
            source_url=source_url,
            title=title,
            media_type=media_type,
            storage_backend="postgres_inline",
            inline_text=inline_text,
            object_key=None,
            content_sha256=content_sha256 or sha256(content).hexdigest(),
            byte_length=len(content),
            published_at=CAPTURED_AT,
            captured_at=CAPTURED_AT,
            ingestion_method="registered_collection",
            transport_security_status="tls_verified_source_url",
            human_review_status="pending_review",
            data_mode=data_mode,
        )
    )


def _knowledge_table_counts(session: Session) -> dict[str, int]:
    return {
        "documents": session.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0,
        "versions": session.scalar(select(func.count()).select_from(KnowledgeDocumentVersion)) or 0,
        "chunks": session.scalar(select(func.count()).select_from(KnowledgeChunk)) or 0,
        "reviews": session.scalar(select(func.count()).select_from(KnowledgeDocumentReview)) or 0,
        "authorization_audits": session.scalar(
            select(func.count()).select_from(KnowledgeAuthorizationAudit)
        )
        or 0,
    }
