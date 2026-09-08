from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest
import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.market import (
    MarketDataSource,
    MarketIngestionRun,
    MarketIngestionRunItem,
    MarketQualityIssue,
    MarketRawArtifact,
    MarketSourceEndpoint,
)
from backend.app.services.registered_source_collector import (
    REGISTERED_STATIC_HTTP_ADAPTER_KEY,
    USER_AGENT,
    RegisteredSourceCollectionError,
    collect_registered_source_endpoint,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeResponse:
    def __init__(
        self,
        *,
        content: bytes,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        encoding: str | None = "utf-8",
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.encoding = encoding
        self.closed = False

    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]:
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeHttpClient:
    def __init__(self, outcomes: list[FakeResponse | requests.RequestException]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        timeout: float,
        allow_redirects: bool,
        stream: bool,
        headers: Mapping[str, str],
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "timeout": timeout,
                "allow_redirects": allow_redirects,
                "stream": stream,
                "user_agent": headers.get("User-Agent"),
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


def _add_registered_endpoint(
    session: Session,
    *,
    endpoint_id: str = "verified_policy_home",
    canonical_url: str = "https://policy.example.test/research/",
    allowed_domains: list[str] | None = None,
    adapter_key: str | None = REGISTERED_STATIC_HTTP_ADAPTER_KEY,
    collection_enabled: bool = True,
    access_mode: str = "anonymous_https",
    lifecycle_status: str = "verified",
) -> None:
    source_id = f"source_{endpoint_id}"
    session.add(
        MarketDataSource(
            source_id=source_id,
            name=source_id,
            operator_name=source_id,
            official_url="https://policy.example.test/",
            market_scope="policy_research",
            notes="Test policy source.",
            data_mode="public_derived",
            trust_tier="official",
            attribution_text="Test policy source.",
            collection_permission_note="Test only.",
        )
    )
    session.add(
        MarketSourceEndpoint(
            endpoint_id=endpoint_id,
            source_id=source_id,
            name="Verified policy home",
            canonical_url=canonical_url,
            endpoint_kind="html_listing",
            allowed_domains_json=allowed_domains or ["policy.example.test"],
            visibility_scope="internet_public",
            access_mode=access_mode,
            lifecycle_status=lifecycle_status,
            content_formats_json=["text/html"],
            data_granularity="policy_documents",
            adapter_key=adapter_key,
            parser_key=None,
            parser_version=None,
            health_check_enabled=True,
            manual_submission_enabled=True,
            collection_enabled=collection_enabled,
            health_probe_not_before=None,
            cadence="every_6_hours",
            notes="Verified test endpoint.",
        )
    )


def _load_detached_endpoint(session: Session, endpoint_id: str) -> MarketSourceEndpoint:
    endpoint = session.get(MarketSourceEndpoint, endpoint_id)
    assert endpoint is not None
    session.expunge(endpoint)
    session.rollback()
    return endpoint


def test_registered_source_collector_preserves_html_and_audits_run(
    db_session_factory: sessionmaker[Session],
) -> None:
    html = b"<html><body>official policy page</body></html>"
    client = FakeHttpClient(
        [
            FakeResponse(content=b"User-agent: *\nAllow: /\nCrawl-delay: 2\n"),
            FakeResponse(content=html),
        ]
    )
    with db_session_factory.begin() as session:
        _add_registered_endpoint(session)
    with db_session_factory() as session:
        endpoint = _load_detached_endpoint(session, "verified_policy_home")
        result = collect_registered_source_endpoint(
            endpoint,
            session=session,
            client=client,
            now=datetime(2026, 6, 8, 9, 0, tzinfo=SHANGHAI),
            sleep=lambda _seconds: None,
        )

    assert result.status == "succeeded"
    assert result.item_status == "inserted"
    assert result.request_count == 2
    assert result.robots_status == "allowed"
    assert result.content_sha256 == sha256(html).hexdigest()
    assert [call["url"] for call in client.calls] == [
        "https://policy.example.test/robots.txt",
        "https://policy.example.test/research/",
    ]
    assert all(call["allow_redirects"] is False for call in client.calls)
    assert all(call["stream"] is True for call in client.calls)
    assert all(call["user_agent"] == USER_AGENT for call in client.calls)

    with db_session_factory() as session:
        artifact = session.scalar(select(MarketRawArtifact))
        run = session.scalar(select(MarketIngestionRun))
        item = session.scalar(select(MarketIngestionRunItem))
        issues = list(session.scalars(select(MarketQualityIssue)))

    assert artifact is not None
    assert artifact.inline_text == html.decode()
    assert artifact.storage_backend == "postgres_inline"
    assert artifact.object_key is None
    assert artifact.content_sha256 == sha256(html).hexdigest()
    assert artifact.transport_security_status == "tls_verified_source_url"
    assert artifact.ingestion_method == "registered_collection"
    assert run is not None
    assert run.status == "succeeded"
    assert run.items_inserted == 1
    assert run.adapter_key == REGISTERED_STATIC_HTTP_ADAPTER_KEY
    assert item is not None
    assert item.artifact_id == artifact.artifact_id
    assert item.item_status == "inserted"
    assert {issue.issue_code for issue in issues} == {"robots_rate_directives_recorded"}


def test_registered_source_collector_deduplicates_by_source_sha256(
    db_session_factory: sessionmaker[Session],
) -> None:
    html = b"<html><body>same official page</body></html>"
    with db_session_factory.begin() as session:
        _add_registered_endpoint(session)

    for _index in range(2):
        client = FakeHttpClient(
            [
                FakeResponse(content=b"", status_code=404),
                FakeResponse(content=html),
            ]
        )
        with db_session_factory() as session:
            endpoint = _load_detached_endpoint(session, "verified_policy_home")
            collect_registered_source_endpoint(
                endpoint,
                session=session,
                client=client,
                now=datetime(2026, 6, 8, 9, 0, tzinfo=SHANGHAI),
                sleep=lambda _seconds: None,
            )

    with db_session_factory() as session:
        artifact_count = session.scalar(select(func.count()).select_from(MarketRawArtifact))
        run_count = session.scalar(select(func.count()).select_from(MarketIngestionRun))
        duplicate_run = session.scalar(
            select(MarketIngestionRun).where(MarketIngestionRun.duplicate_items == 1).limit(1)
        )

    assert artifact_count == 1
    assert run_count == 2
    assert duplicate_run is not None
    assert duplicate_run.quality_status == "valid"


@pytest.mark.parametrize(
    ("canonical_url", "allowed_domains", "code"),
    [
        (
            "https://evil.example.test/research/",
            ["policy.example.test"],
            "registered_source_url_not_allowed",
        ),
        (
            "http://policy.example.test/research/",
            ["policy.example.test"],
            "registered_source_url_not_allowed",
        ),
        (
            "https://policy.example.test:8443/research/",
            ["policy.example.test"],
            "registered_source_url_not_allowed",
        ),
        (
            "https://user:pass@policy.example.test/research/",
            ["policy.example.test"],
            "registered_source_url_not_allowed",
        ),
    ],
)
def test_registered_source_collector_rejects_endpoint_before_network_access(
    db_session_factory: sessionmaker[Session],
    canonical_url: str,
    allowed_domains: list[str],
    code: str,
) -> None:
    client = FakeHttpClient([])
    with db_session_factory.begin() as session:
        _add_registered_endpoint(
            session,
            canonical_url=canonical_url,
            allowed_domains=allowed_domains,
        )
    with db_session_factory() as session:
        endpoint = _load_detached_endpoint(session, "verified_policy_home")
        with pytest.raises(RegisteredSourceCollectionError) as exc_info:
            collect_registered_source_endpoint(endpoint, session=session, client=client)

    assert exc_info.value.code == code
    assert exc_info.value.transient is False
    assert client.calls == []
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MarketIngestionRun)) == 0


def test_registered_source_collector_rejects_unreviewed_adapter_before_request(
    db_session_factory: sessionmaker[Session],
) -> None:
    client = FakeHttpClient([])
    with db_session_factory.begin() as session:
        _add_registered_endpoint(session, adapter_key=None)
    with db_session_factory() as session:
        endpoint = _load_detached_endpoint(session, "verified_policy_home")
        with pytest.raises(RegisteredSourceCollectionError) as exc_info:
            collect_registered_source_endpoint(endpoint, session=session, client=client)

    assert exc_info.value.code == "registered_source_adapter_not_reviewed"
    assert client.calls == []


def test_registered_source_collector_rejects_robots_disallowed_without_page_request(
    db_session_factory: sessionmaker[Session],
) -> None:
    client = FakeHttpClient(
        [
            FakeResponse(content=b"User-agent: *\nDisallow: /research/\n"),
        ]
    )
    with db_session_factory.begin() as session:
        _add_registered_endpoint(session)
    with db_session_factory() as session:
        endpoint = _load_detached_endpoint(session, "verified_policy_home")
        with pytest.raises(RegisteredSourceCollectionError) as exc_info:
            collect_registered_source_endpoint(
                endpoint,
                session=session,
                client=client,
                sleep=lambda _seconds: None,
            )

    assert exc_info.value.code == "registered_source_robots_disallowed"
    assert len(client.calls) == 1
    with db_session_factory() as session:
        run = session.scalar(select(MarketIngestionRun))
        issue = session.scalar(select(MarketQualityIssue))
    assert run is not None
    assert run.status == "failed"
    assert run.rejected_items == 1
    assert issue is not None
    assert issue.issue_code == "registered_source_robots_disallowed"


@pytest.mark.parametrize(
    ("outcome", "code", "transient"),
    [
        (requests.exceptions.Timeout("slow"), "registered_source_timeout", True),
        (requests.exceptions.SSLError("tls"), "registered_source_tls_failed", False),
    ],
)
def test_registered_source_collector_records_timeout_and_tls_failures(
    db_session_factory: sessionmaker[Session],
    outcome: requests.RequestException,
    code: str,
    transient: bool,
) -> None:
    client = FakeHttpClient(
        [
            FakeResponse(content=b"", status_code=404),
            outcome,
        ]
    )
    with db_session_factory.begin() as session:
        _add_registered_endpoint(session)
    with db_session_factory() as session:
        endpoint = _load_detached_endpoint(session, "verified_policy_home")
        with pytest.raises(RegisteredSourceCollectionError) as exc_info:
            collect_registered_source_endpoint(
                endpoint,
                session=session,
                client=client,
                max_retries=0,
                sleep=lambda _seconds: None,
            )

    assert exc_info.value.code == code
    assert exc_info.value.transient is transient
    with db_session_factory() as session:
        run = session.scalar(select(MarketIngestionRun))
        issue = session.scalar(select(MarketQualityIssue))
    assert run is not None
    assert run.error_code == code
    assert issue is not None
    assert issue.issue_code == code


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            FakeResponse(content=b"", status_code=302, headers={"Location": "https://other.test/"}),
            "registered_source_redirect_rejected",
        ),
        (
            FakeResponse(content=b"%PDF", headers={"Content-Type": "application/pdf"}),
            "registered_source_unsupported_media_type",
        ),
    ],
)
def test_registered_source_collector_rejects_redirect_and_unsupported_media(
    db_session_factory: sessionmaker[Session],
    response: FakeResponse,
    code: str,
) -> None:
    client = FakeHttpClient(
        [
            FakeResponse(content=b"", status_code=404),
            response,
        ]
    )
    with db_session_factory.begin() as session:
        _add_registered_endpoint(session)
    with db_session_factory() as session:
        endpoint = _load_detached_endpoint(session, "verified_policy_home")
        with pytest.raises(RegisteredSourceCollectionError) as exc_info:
            collect_registered_source_endpoint(
                endpoint,
                session=session,
                client=client,
                sleep=lambda _seconds: None,
            )

    assert exc_info.value.code == code
    with db_session_factory() as session:
        run = session.scalar(select(MarketIngestionRun))
    assert run is not None
    assert run.error_code == code


def test_registered_source_collector_rejects_oversized_response(
    db_session_factory: sessionmaker[Session],
) -> None:
    client = FakeHttpClient(
        [
            FakeResponse(content=b"", status_code=404),
            FakeResponse(content=b"four"),
        ]
    )
    with db_session_factory.begin() as session:
        _add_registered_endpoint(session)
    with db_session_factory() as session:
        endpoint = _load_detached_endpoint(session, "verified_policy_home")
        with pytest.raises(RegisteredSourceCollectionError) as exc_info:
            collect_registered_source_endpoint(
                endpoint,
                session=session,
                client=client,
                max_response_bytes=3,
                sleep=lambda _seconds: None,
            )

    assert exc_info.value.code == "registered_source_response_too_large"
    with db_session_factory() as session:
        run = session.scalar(select(MarketIngestionRun))
        item = session.scalar(select(MarketIngestionRunItem))
    assert run is not None
    assert run.rejected_items == 1
    assert item is not None
    assert item.item_status == "rejected"
