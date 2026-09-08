from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.api.routes.knowledge import get_blob_store  # noqa: E402
from backend.app.core.config import get_settings  # noqa: E402
from backend.app.db.base import Base  # noqa: E402
from backend.app.db.session import get_db_session, get_engine, get_session_factory  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.models import forecasting as _forecasting  # noqa: F401, E402
from backend.app.models import intelligence as _intelligence  # noqa: F401, E402
from backend.app.models import knowledge as _knowledge  # noqa: F401, E402
from backend.app.models import market as _market  # noqa: F401, E402
from backend.app.models import operations as _operations  # noqa: F401, E402
from backend.app.models import recommendation as _recommendation  # noqa: F401, E402
from backend.app.models import scenario as _scenario  # noqa: F401, E402
from backend.app.models import weather as _weather  # noqa: F401, E402
from backend.app.services.deepseek import get_deepseek_client  # noqa: E402
from backend.app.services.embeddings import HashEmbeddingClient, get_embedding_client  # noqa: E402
from backend.app.storage.blob_store import MemoryBlobStore  # noqa: E402


TRIAL_TEXT = (
    "Local RAG trial policy note for Example Province hydro market research. "
    "The note discusses hydro risk adjustment, settlement review, and operator "
    "evidence checks. It is user uploaded local text and is not automatic "
    "trading evidence."
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


class FakeDeepSeekClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, *, prompt: str, deep_analysis: bool) -> tuple[dict[str, object], str]:
        self.prompts.append(prompt)
        model = "local-fake-deepseek-deep" if deep_analysis else "local-fake-deepseek-simple"
        return {"answer": "Authorized local evidence supports a human-reviewed answer."}, model


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a host-only RAG trial smoke without external network or persistent DB access."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON results.")
    args = parser.parse_args()

    results = run_trial()
    ok = all(result.ok for result in results)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "checks": [result.__dict__ for result in results],
                    "host_only": True,
                    "external_network_access": False,
                    "persistent_database_access": False,
                    "external_model_call": False,
                    "no_auto_trading": True,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
    else:
        for result in results:
            status = "ok" if result.ok else "fail"
            print(f"[{status}] {result.name}: {result.message}")
    return 0 if ok else 1


def run_trial() -> list[CheckResult]:
    fake_deepseek = FakeDeepSeekClient()
    results: list[CheckResult] = []
    with _trial_client(fake_deepseek) as client:
        if not _record(results, "empty corpus", lambda: _check_empty_corpus(client)):
            return results
        upload_result: tuple[str, str] | None = None
        try:
            upload_result = _check_local_upload(client)
            results.append(CheckResult(name="local upload", ok=True, message=upload_result[0]))
        except (AssertionError, KeyError, IndexError, RuntimeError) as exc:
            results.append(CheckResult(name="local upload", ok=False, message=str(exc)))
            return results
        document_id = upload_result[1]
        checks: tuple[tuple[str, Callable[[], str]], ...] = (
            (
                "chunks detail review package",
                lambda: _check_chunks_detail_review_package(client, document_id),
            ),
            ("search", lambda: _check_search(client, document_id)),
            ("unauthorized Q&A", lambda: _check_unauthorized_question(client)),
            (
                "authorized fake Q&A",
                lambda: _check_authorized_question(client, document_id, fake_deepseek),
            ),
            ("document review", lambda: _check_document_review(client, document_id)),
        )
        for name, check in checks:
            if not _record(results, name, check):
                break
    return results


def _record(results: list[CheckResult], name: str, check: Callable[[], str]) -> bool:
    try:
        message = check()
    except (AssertionError, KeyError, IndexError, RuntimeError) as exc:
        results.append(CheckResult(name=name, ok=False, message=str(exc)))
        return False
    results.append(CheckResult(name=name, ok=True, message=message))
    return True


@contextmanager
def _trial_client(fake_deepseek: FakeDeepSeekClient) -> Iterator[TestClient]:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_blob_store] = lambda: MemoryBlobStore()
    app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    app.dependency_overrides[get_deepseek_client] = lambda: fake_deepseek
    try:
        with TestClient(app) as client:
            yield client
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def _check_empty_corpus(client: TestClient) -> str:
    response = client.get("/v1/policy/corpus/overview")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["document_count"] == 0
    assert payload["chunk_count"] == 0
    assert payload["no_auto_trading"] is True
    assert payload["fetch_performed"] is False
    assert payload["network_probe_performed"] is False
    return "empty corpus returns warning with safe local-only flags"


def _check_local_upload(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/v1/policy/documents/upload",
        data={
            "title": "Local RAG trial policy note",
            "document_layer": "user_uploaded",
            "source_name": "Local trial upload",
        },
        files={"file": ("rag-trial.txt", TRIAL_TEXT, "text/plain")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["data_mode"] == "user_uploaded"
    assert payload["external_processing_allowed"] is False
    assert payload["human_review_status"] == "pending_review"
    return "local txt upload is chunked with external processing disabled", payload["document_id"]


def _check_chunks_detail_review_package(client: TestClient, document_id: str) -> str:
    chunks = client.get(f"/v1/policy/documents/{document_id}/chunks")
    assert chunks.status_code == 200, chunks.text
    assert TRIAL_TEXT in chunks.json()["items"][0]["content"]
    overview = client.get("/v1/policy/corpus/overview")
    assert overview.status_code == 200, overview.text
    overview_payload = overview.json()
    assert overview_payload["status"] == "healthy"
    assert overview_payload["document_count"] == 1
    assert overview_payload["embedded_chunk_count"] == overview_payload["chunk_count"]
    detail = client.get(f"/v1/policy/documents/{document_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["external_processing_allowed_default"] is False
    package = client.get(f"/v1/policy/documents/{document_id}/review-package")
    assert package.status_code == 200, package.text
    package_payload = package.json()
    assert package_payload["chunk_summary"]["total_count"] >= 1
    assert package_payload["server_artifact_written"] is False
    assert package_payload["raw_payload_included"] is False
    assert package_payload["external_model_call_performed"] is False
    assert package_payload["fetch_performed"] is False
    assert package_payload["network_probe_performed"] is False
    assert package_payload["no_auto_trading"] is True
    return "chunks, detail, and review package are available with safe flags"


def _check_search(client: TestClient, document_id: str) -> str:
    response = client.post(
        "/v1/intelligence/search",
        json={"query": "hydro risk adjustment", "limit": 3},
    )
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["citation"]["document_id"] == document_id
    assert item["citation"]["data_mode"] == "user_uploaded"
    assert item["external_processing_allowed"] is False
    assert "hydro risk adjustment" in item["excerpt"]
    return "search returns cited local evidence without authorizing external processing"


def _check_unauthorized_question(client: TestClient) -> str:
    response = client.post(
        "/v1/intelligence/questions",
        json={"question": "hydro risk adjustment", "analysis_mode": "simple"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["citations"] == []
    assert payload["excluded_restricted_chunks"] >= 1
    assert payload["llm_used"] is False
    assert payload["human_review_required"] is True
    return "Q&A excludes unauthorized chunks and does not use an LLM"


def _check_authorized_question(
    client: TestClient, document_id: str, fake_deepseek: FakeDeepSeekClient
) -> str:
    authorization = client.post(
        f"/v1/policy/documents/{document_id}/external-processing-authorization",
        json={
            "external_processing_allowed": True,
            "note": "Reviewed local trial evidence for fake local model smoke.",
        },
    )
    assert authorization.status_code == 200, authorization.text
    response = client.post(
        "/v1/intelligence/questions",
        json={"question": "hydro risk adjustment", "analysis_mode": "deep"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["llm_used"] is True
    assert payload["llm_model"] == "local-fake-deepseek-deep"
    assert payload["citations"][0]["document_id"] == document_id
    assert payload["excluded_restricted_chunks"] == 0
    assert fake_deepseek.prompts
    assert "hydro risk adjustment" in fake_deepseek.prompts[-1]
    return "authorized Q&A uses fake local model with cited evidence only"


def _check_document_review(client: TestClient, document_id: str) -> str:
    response = client.post(
        f"/v1/policy/documents/{document_id}/reviews",
        json={"review_status": "approved", "note": "Host-only RAG trial reviewed."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "approved"
    detail = client.get(f"/v1/policy/documents/{document_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["human_review_status"] == "approved"
    package = client.get(f"/v1/policy/documents/{document_id}/review-package")
    assert package.status_code == 200, package.text
    assert package.json()["review_count"] == 1
    return "document review is recorded and visible in the review package"


if __name__ == "__main__":
    raise SystemExit(main())
