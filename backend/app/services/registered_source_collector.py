from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol, cast
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session

from backend.app.models.market import MarketSourceEndpoint
from backend.app.repositories.market import (
    add_market_ingestion_run,
    add_market_ingestion_run_item,
    add_market_quality_issue,
    add_market_raw_artifact,
    get_market_raw_artifact_by_source_hash,
)

logger = logging.getLogger(__name__)

REGISTERED_STATIC_HTTP_ADAPTER_KEY = "registered_static_http:v1"
REGISTERED_COLLECTION = "registered_collection"
PUBLIC_OBSERVED = "public_observed"
PUBLIC_DERIVED = "public_derived"
POSTGRES_INLINE = "postgres_inline"
TLS_VERIFIED_SOURCE_URL = "tls_verified_source_url"
MAX_REGISTERED_SOURCE_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5
USER_AGENT = "EEE-Research-Collector/1.0"
SUPPORTED_MEDIA_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "text/csv",
        "text/html",
        "text/plain",
        "text/xml",
    }
)
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class RegisteredSourceHttpResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]
    encoding: str | None

    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class RegisteredSourceHttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        timeout: float,
        allow_redirects: bool,
        stream: bool,
        headers: Mapping[str, str],
    ) -> RegisteredSourceHttpResponse: ...


@dataclass(frozen=True)
class RegisteredSourceCollectionResult:
    ingestion_run_id: str
    ingestion_run_item_id: str
    artifact_id: str | None
    endpoint_id: str
    source_id: str
    source_url: str
    status: str
    item_status: str
    content_sha256: str | None
    duplicate_artifact: bool
    quality_status: str
    quality_issue_count: int
    media_type: str | None
    byte_length: int
    request_count: int
    robots_status: str


@dataclass(frozen=True)
class _RobotsResult:
    status: str
    request_count: int
    crawl_delay_seconds: float | None
    request_rate: tuple[int, int] | None


@dataclass(frozen=True)
class _CollectionFailure:
    code: str
    message: str
    transient: bool
    request_count: int = 0
    item_status: str = "failed"
    quality_severity: str = "warning"
    robots_status: str = "not_checked"


class RegisteredSourceCollectionError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        transient: bool,
        endpoint_id: str,
        ingestion_run_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.transient = transient
        self.endpoint_id = endpoint_id
        self.ingestion_run_id = ingestion_run_id


class RequestsRegisteredSourceHttpClient:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.trust_env = False

    def get(
        self,
        url: str,
        *,
        timeout: float,
        allow_redirects: bool,
        stream: bool,
        headers: Mapping[str, str],
    ) -> RegisteredSourceHttpResponse:
        self._session.cookies.clear()
        response = self._session.get(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
            stream=stream,
            headers=dict(headers),
        )
        self._session.cookies.clear()
        return cast(RegisteredSourceHttpResponse, response)


def collect_registered_source_endpoint(
    endpoint: MarketSourceEndpoint,
    *,
    session: Session,
    client: RegisteredSourceHttpClient | None = None,
    now: datetime | None = None,
    adapter_key: str = REGISTERED_STATIC_HTTP_ADAPTER_KEY,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    max_response_bytes: int = MAX_REGISTERED_SOURCE_BYTES,
    sleep: Callable[[float], None] = time.sleep,
) -> RegisteredSourceCollectionResult:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")
    if not 0 <= max_retries <= 5:
        raise ValueError("max_retries must be between 0 and 5.")
    if retry_backoff_seconds < 0:
        raise ValueError("retry_backoff_seconds must not be negative.")
    if max_response_bytes <= 0:
        raise ValueError("max_response_bytes must be positive.")

    captured_at = now or _now()
    failure = _validate_endpoint(endpoint, adapter_key)
    if failure is not None:
        raise RegisteredSourceCollectionError(
            code=failure.code,
            message=failure.message,
            transient=failure.transient,
            endpoint_id=endpoint.endpoint_id,
        )

    resolved_client = client or RequestsRegisteredSourceHttpClient()
    robots_result = _check_robots(
        endpoint,
        client=resolved_client,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        sleep=sleep,
    )
    if isinstance(robots_result, _CollectionFailure):
        result = _persist_failed_collection(
            session=session,
            endpoint=endpoint,
            started_at=captured_at,
            completed_at=captured_at,
            failure=robots_result,
            adapter_key=adapter_key,
        )
        raise RegisteredSourceCollectionError(
            code=robots_result.code,
            message=robots_result.message,
            transient=robots_result.transient,
            endpoint_id=endpoint.endpoint_id,
            ingestion_run_id=result.ingestion_run_id,
        )

    fetch_result = _fetch_registered_url(
        endpoint.canonical_url,
        client=resolved_client,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        sleep=sleep,
        max_bytes=max_response_bytes,
    )
    request_count = robots_result.request_count + 1
    if isinstance(fetch_result, _CollectionFailure):
        failure = _CollectionFailure(
            code=fetch_result.code,
            message=fetch_result.message,
            transient=fetch_result.transient,
            request_count=request_count,
            item_status=fetch_result.item_status,
            quality_severity=fetch_result.quality_severity,
            robots_status=robots_result.status,
        )
        result = _persist_failed_collection(
            session=session,
            endpoint=endpoint,
            started_at=captured_at,
            completed_at=captured_at,
            failure=failure,
            adapter_key=adapter_key,
        )
        raise RegisteredSourceCollectionError(
            code=failure.code,
            message=failure.message,
            transient=failure.transient,
            endpoint_id=endpoint.endpoint_id,
            ingestion_run_id=result.ingestion_run_id,
        )
    if fetch_result is None:
        failure = _CollectionFailure(
            code="registered_source_empty_response",
            message="Registered source returned no content.",
            transient=False,
            request_count=request_count,
            item_status="rejected",
            quality_severity="warning",
            robots_status=robots_result.status,
        )
        result = _persist_failed_collection(
            session=session,
            endpoint=endpoint,
            started_at=captured_at,
            completed_at=captured_at,
            failure=failure,
            adapter_key=adapter_key,
        )
        raise RegisteredSourceCollectionError(
            code=failure.code,
            message=failure.message,
            transient=failure.transient,
            endpoint_id=endpoint.endpoint_id,
            ingestion_run_id=result.ingestion_run_id,
        )

    content, media_type, encoding = fetch_result
    if media_type not in SUPPORTED_MEDIA_TYPES:
        failure = _CollectionFailure(
            code="registered_source_unsupported_media_type",
            message=f"Registered source returned unsupported media type '{media_type}'.",
            transient=False,
            request_count=request_count,
            item_status="rejected",
            quality_severity="warning",
            robots_status=robots_result.status,
        )
        result = _persist_failed_collection(
            session=session,
            endpoint=endpoint,
            started_at=captured_at,
            completed_at=captured_at,
            failure=failure,
            adapter_key=adapter_key,
        )
        raise RegisteredSourceCollectionError(
            code=failure.code,
            message=failure.message,
            transient=failure.transient,
            endpoint_id=endpoint.endpoint_id,
            ingestion_run_id=result.ingestion_run_id,
        )

    text = content.decode(encoding or "utf-8", errors="replace")
    content_sha256 = sha256(content).hexdigest()
    with session.begin():
        artifact = get_market_raw_artifact_by_source_hash(
            session,
            source_id=endpoint.source_id,
            content_sha256=content_sha256,
        )
        duplicate_artifact = artifact is not None
        if artifact is None:
            artifact = add_market_raw_artifact(
                session,
                artifact_id=_new_id("market_artifact"),
                source_id=endpoint.source_id,
                endpoint_id=endpoint.endpoint_id,
                source_url=endpoint.canonical_url,
                title=endpoint.name,
                media_type=media_type,
                storage_backend=POSTGRES_INLINE,
                inline_text=text,
                object_key=None,
                content_sha256=content_sha256,
                byte_length=len(content),
                published_at=None,
                captured_at=captured_at,
                ingestion_method=REGISTERED_COLLECTION,
                transport_security_status=TLS_VERIFIED_SOURCE_URL,
                data_mode=PUBLIC_OBSERVED,
            )
        ingestion_run_id = _new_id("market_ingest")
        ingestion_run_item_id = _new_id("market_item")
        findings = _collection_findings(
            duplicate_artifact=duplicate_artifact,
            robots_result=robots_result,
        )
        quality_status = _quality_status(findings)
        add_market_ingestion_run(
            session,
            ingestion_run_id=ingestion_run_id,
            source_id=endpoint.source_id,
            endpoint_id=endpoint.endpoint_id,
            trigger_mode=REGISTERED_COLLECTION,
            adapter_key=adapter_key,
            adapter_version="1",
            started_at=captured_at,
            completed_at=captured_at,
            status="succeeded",
            items_received=1,
            items_inserted=0 if duplicate_artifact else 1,
            duplicate_items=1 if duplicate_artifact else 0,
            rejected_items=0,
            quality_status=quality_status,
            quality_issue_count=len(findings),
        )
        item = add_market_ingestion_run_item(
            session,
            ingestion_run_item_id=ingestion_run_item_id,
            ingestion_run_id=ingestion_run_id,
            artifact_id=artifact.artifact_id,
            source_url=endpoint.canonical_url,
            item_status="duplicate" if duplicate_artifact else "inserted",
        )
        _add_findings(
            session,
            endpoint=endpoint,
            ingestion_run_id=ingestion_run_id,
            ingestion_run_item_id=item.ingestion_run_item_id,
            artifact_id=artifact.artifact_id,
            findings=findings,
        )

    logger.info(
        "Collected registered source endpoint=%s duplicate=%s bytes=%s",
        endpoint.endpoint_id,
        duplicate_artifact,
        len(content),
    )
    return RegisteredSourceCollectionResult(
        ingestion_run_id=ingestion_run_id,
        ingestion_run_item_id=ingestion_run_item_id,
        artifact_id=artifact.artifact_id,
        endpoint_id=endpoint.endpoint_id,
        source_id=endpoint.source_id,
        source_url=endpoint.canonical_url,
        status="succeeded",
        item_status="duplicate" if duplicate_artifact else "inserted",
        content_sha256=content_sha256,
        duplicate_artifact=duplicate_artifact,
        quality_status=quality_status,
        quality_issue_count=len(findings),
        media_type=media_type,
        byte_length=len(content),
        request_count=request_count,
        robots_status=robots_result.status,
    )


def _validate_endpoint(
    endpoint: MarketSourceEndpoint, adapter_key: str
) -> _CollectionFailure | None:
    parsed = urlparse(endpoint.canonical_url)
    if endpoint.adapter_key != adapter_key:
        return _validation_failure(
            "registered_source_adapter_not_reviewed",
            f"Endpoint '{endpoint.endpoint_id}' does not use reviewed adapter '{adapter_key}'.",
        )
    if not endpoint.collection_enabled:
        return _validation_failure(
            "registered_source_collection_disabled",
            f"Endpoint '{endpoint.endpoint_id}' is not enabled for collection.",
        )
    if endpoint.access_mode != "anonymous_https":
        return _validation_failure(
            "registered_source_access_mode_not_allowed",
            f"Endpoint '{endpoint.endpoint_id}' is not anonymous HTTPS.",
        )
    if endpoint.lifecycle_status != "verified":
        return _validation_failure(
            "registered_source_lifecycle_not_verified",
            f"Endpoint '{endpoint.endpoint_id}' is not verified for collection.",
        )
    if parsed.username is not None or parsed.password is not None:
        return _validation_failure(
            "registered_source_url_not_allowed",
            "Registered source canonical URL must not include credentials.",
        )
    if parsed.scheme != "https":
        return _validation_failure(
            "registered_source_url_not_allowed",
            "Registered source collection requires HTTPS.",
        )
    if parsed.hostname is None:
        return _validation_failure(
            "registered_source_url_not_allowed",
            "Registered source canonical URL must include a hostname.",
        )
    try:
        port = parsed.port
    except ValueError:
        return _validation_failure(
            "registered_source_url_not_allowed",
            "Registered source canonical URL must use a valid port.",
        )
    if port not in {None, 443}:
        return _validation_failure(
            "registered_source_url_not_allowed",
            "Registered source canonical URL must not use a custom port.",
        )
    allowed_domains = {domain.lower() for domain in endpoint.allowed_domains_json}
    if parsed.hostname.lower() not in allowed_domains:
        return _validation_failure(
            "registered_source_url_not_allowed",
            "Registered source canonical URL host is not registered.",
        )
    if parsed.fragment:
        return _validation_failure(
            "registered_source_url_not_allowed",
            "Registered source canonical URL must not include fragments.",
        )
    return None


def _validation_failure(code: str, message: str) -> _CollectionFailure:
    return _CollectionFailure(code=code, message=message, transient=False)


def _check_robots(
    endpoint: MarketSourceEndpoint,
    *,
    client: RegisteredSourceHttpClient,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
    sleep: Callable[[float], None],
) -> _RobotsResult | _CollectionFailure:
    parsed = urlparse(endpoint.canonical_url)
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    fetch_result = _fetch_registered_url(
        robots_url,
        client=client,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        sleep=sleep,
        allow_missing=True,
        max_bytes=256_000,
    )
    if isinstance(fetch_result, _CollectionFailure):
        return _CollectionFailure(
            code="registered_source_robots_unavailable",
            message=f"Robots.txt could not be checked: {fetch_result.message}",
            transient=fetch_result.transient,
            request_count=1,
            quality_severity=fetch_result.quality_severity,
            robots_status="failed",
        )
    if fetch_result is None:
        return _RobotsResult(
            status="missing",
            request_count=1,
            crawl_delay_seconds=None,
            request_rate=None,
        )
    content, _media_type, encoding = fetch_result
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(content.decode(encoding or "utf-8", errors="replace").splitlines())
    if not parser.can_fetch(USER_AGENT, endpoint.canonical_url):
        return _CollectionFailure(
            code="registered_source_robots_disallowed",
            message=f"Robots.txt disallows collection of endpoint '{endpoint.endpoint_id}'.",
            transient=False,
            request_count=1,
            item_status="rejected",
            quality_severity="critical",
            robots_status="disallowed",
        )
    crawl_delay = parser.crawl_delay(USER_AGENT)
    request_rate = parser.request_rate(USER_AGENT)
    return _RobotsResult(
        status="allowed",
        request_count=1,
        crawl_delay_seconds=float(crawl_delay) if crawl_delay is not None else None,
        request_rate=(
            (request_rate.requests, request_rate.seconds) if request_rate is not None else None
        ),
    )


def _fetch_registered_url(
    url: str,
    *,
    client: RegisteredSourceHttpClient,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
    sleep: Callable[[float], None],
    allow_missing: bool = False,
    max_bytes: int = MAX_REGISTERED_SOURCE_BYTES,
) -> tuple[bytes, str, str | None] | _CollectionFailure | None:
    for attempt in range(max_retries + 1):
        try:
            response = client.get(
                url,
                timeout=timeout_seconds,
                allow_redirects=False,
                stream=True,
                headers={
                    "Accept": ", ".join(sorted(SUPPORTED_MEDIA_TYPES)),
                    "User-Agent": USER_AGENT,
                },
            )
        except requests.exceptions.Timeout as exc:
            if attempt < max_retries:
                _retry(attempt, "timeout", retry_backoff_seconds, sleep)
                continue
            return _CollectionFailure(
                code="registered_source_timeout",
                message=f"Registered source request timed out: {type(exc).__name__}.",
                transient=True,
                quality_severity="warning",
            )
        except requests.exceptions.SSLError as exc:
            return _CollectionFailure(
                code="registered_source_tls_failed",
                message=f"Registered source TLS validation failed: {type(exc).__name__}.",
                transient=False,
                quality_severity="critical",
            )
        except requests.RequestException as exc:
            if attempt < max_retries:
                _retry(attempt, type(exc).__name__, retry_backoff_seconds, sleep)
                continue
            return _CollectionFailure(
                code="registered_source_network_error",
                message=f"Registered source request failed: {type(exc).__name__}.",
                transient=True,
                quality_severity="warning",
            )
        try:
            if allow_missing and response.status_code == 404:
                return None
            if 300 <= response.status_code < 400:
                return _CollectionFailure(
                    code="registered_source_redirect_rejected",
                    message="Registered source redirected; redirects are not followed.",
                    transient=False,
                    item_status="rejected",
                    quality_severity="warning",
                )
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                _retry(attempt, f"http_{response.status_code}", retry_backoff_seconds, sleep)
                continue
            if response.status_code >= 400:
                return _CollectionFailure(
                    code="registered_source_http_error",
                    message=f"Registered source returned HTTP {response.status_code}.",
                    transient=response.status_code in RETRYABLE_STATUS_CODES,
                    quality_severity="warning",
                )
            try:
                content = _read_bounded_response(
                    response,
                    max_bytes=max_bytes,
                )
            except RegisteredSourceCollectionError as exc:
                return _CollectionFailure(
                    code=exc.code,
                    message=exc.message,
                    transient=False,
                    item_status="rejected",
                    quality_severity="warning",
                )
            media_type = _media_type(response.headers.get("Content-Type"))
            return content, media_type, response.encoding
        finally:
            response.close()
    raise AssertionError("Registered source retry loop exited unexpectedly.")


def _read_bounded_response(
    response: RegisteredSourceHttpResponse,
    *,
    max_bytes: int,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65_536):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise RegisteredSourceCollectionError(
                code="registered_source_response_too_large",
                message="Registered source response exceeds the configured size limit.",
                transient=False,
                endpoint_id="unknown",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _persist_failed_collection(
    *,
    session: Session,
    endpoint: MarketSourceEndpoint,
    started_at: datetime,
    completed_at: datetime,
    failure: _CollectionFailure,
    adapter_key: str,
) -> RegisteredSourceCollectionResult:
    ingestion_run_id = _new_id("market_ingest")
    ingestion_run_item_id = _new_id("market_item")
    with session.begin():
        add_market_ingestion_run(
            session,
            ingestion_run_id=ingestion_run_id,
            source_id=endpoint.source_id,
            endpoint_id=endpoint.endpoint_id,
            trigger_mode=REGISTERED_COLLECTION,
            adapter_key=adapter_key,
            adapter_version="1",
            started_at=started_at,
            completed_at=completed_at,
            status="failed",
            items_received=1,
            items_inserted=0,
            duplicate_items=0,
            rejected_items=1 if failure.item_status == "rejected" else 0,
            quality_status="failed",
            quality_issue_count=1,
            error_code=failure.code,
            error_message=failure.message,
        )
        item = add_market_ingestion_run_item(
            session,
            ingestion_run_item_id=ingestion_run_item_id,
            ingestion_run_id=ingestion_run_id,
            artifact_id=None,
            source_url=endpoint.canonical_url,
            item_status=failure.item_status,
            error_code=failure.code,
            error_message=failure.message,
        )
        add_market_quality_issue(
            session,
            quality_issue_id=_new_id("market_quality"),
            source_id=endpoint.source_id,
            endpoint_id=endpoint.endpoint_id,
            ingestion_run_id=ingestion_run_id,
            ingestion_run_item_id=item.ingestion_run_item_id,
            parsing_run_id=None,
            endpoint_health_check_id=None,
            artifact_id=None,
            issue_scope="endpoint",
            issue_code=failure.code,
            severity=failure.quality_severity,
            message=failure.message,
            details_json={"request_count": failure.request_count},
            data_mode=PUBLIC_DERIVED,
        )
    logger.warning(
        "Registered source collection failed endpoint=%s code=%s",
        endpoint.endpoint_id,
        failure.code,
    )
    return RegisteredSourceCollectionResult(
        ingestion_run_id=ingestion_run_id,
        ingestion_run_item_id=ingestion_run_item_id,
        artifact_id=None,
        endpoint_id=endpoint.endpoint_id,
        source_id=endpoint.source_id,
        source_url=endpoint.canonical_url,
        status="failed",
        item_status=failure.item_status,
        content_sha256=None,
        duplicate_artifact=False,
        quality_status="failed",
        quality_issue_count=1,
        media_type=None,
        byte_length=0,
        request_count=failure.request_count,
        robots_status=failure.robots_status,
    )


def _collection_findings(
    *,
    duplicate_artifact: bool,
    robots_result: _RobotsResult,
) -> list[tuple[str, str, str, str, dict[str, object]]]:
    findings: list[tuple[str, str, str, str, dict[str, object]]] = []
    if duplicate_artifact:
        findings.append(
            (
                "artifact",
                "duplicate_artifact",
                "info",
                "The same registered source content was already preserved.",
                {},
            )
        )
    if robots_result.status == "missing":
        findings.append(
            (
                "endpoint",
                "robots_txt_missing",
                "info",
                "Robots.txt was not present; collection proceeded without bypassing controls.",
                {},
            )
        )
    if robots_result.crawl_delay_seconds is not None or robots_result.request_rate is not None:
        findings.append(
            (
                "endpoint",
                "robots_rate_directives_recorded",
                "info",
                "Robots.txt rate directives were recorded for audit.",
                {
                    "crawl_delay_seconds": robots_result.crawl_delay_seconds,
                    "request_rate": robots_result.request_rate,
                },
            )
        )
    return findings


def _add_findings(
    session: Session,
    *,
    endpoint: MarketSourceEndpoint,
    ingestion_run_id: str,
    ingestion_run_item_id: str,
    artifact_id: str,
    findings: list[tuple[str, str, str, str, dict[str, object]]],
) -> None:
    for issue_scope, issue_code, severity, message, details in findings:
        add_market_quality_issue(
            session,
            quality_issue_id=_new_id("market_quality"),
            source_id=endpoint.source_id,
            endpoint_id=endpoint.endpoint_id,
            ingestion_run_id=ingestion_run_id,
            ingestion_run_item_id=ingestion_run_item_id,
            parsing_run_id=None,
            endpoint_health_check_id=None,
            artifact_id=artifact_id,
            issue_scope=issue_scope,
            issue_code=issue_code,
            severity=severity,
            message=message,
            details_json=details,
            data_mode=PUBLIC_DERIVED,
        )


def _quality_status(findings: list[tuple[str, str, str, str, dict[str, object]]]) -> str:
    if any(finding[2] in {"warning", "critical"} for finding in findings):
        return "warning"
    return "valid"


def _retry(
    attempt: int,
    reason: str,
    retry_backoff_seconds: float,
    sleep: Callable[[float], None],
) -> None:
    delay = retry_backoff_seconds * (2**attempt)
    logger.warning("Retrying registered source request after %s; delay=%s", reason, delay)
    sleep(delay)


def _media_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def _now() -> datetime:
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
