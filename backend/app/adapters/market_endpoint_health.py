from __future__ import annotations

import ipaddress
import logging
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import ParseResult, urlparse

import dns.exception
import dns.resolver

logger = logging.getLogger(__name__)

MAX_RESPONSE_HEADER_BYTES = 32_768
PROBE_METHOD = "HEAD"
PUBLIC_DERIVED = "public_derived"


class SocketLike(Protocol):
    def sendall(self, data: bytes) -> None: ...

    def recv(self, bufsize: int) -> bytes: ...

    def close(self) -> None: ...


Resolver = Callable[[str, float], list[str]]
Connector = Callable[[str, int, float], SocketLike]
TlsWrapper = Callable[[SocketLike, str], SocketLike]


@dataclass(frozen=True)
class MarketEndpointProbeTarget:
    endpoint_id: str
    canonical_url: str
    allowed_domains: tuple[str, ...]


@dataclass(frozen=True)
class MarketEndpointProbeResult:
    endpoint_id: str
    probe_url: str
    probe_method: str
    health_status: str
    dns_status: str
    tcp_status: str
    tls_status: str
    http_status: str
    status_code: int | None
    resolved_addresses: tuple[str, ...]
    connected_address: str | None
    attempt_count: int
    duration_ms: int
    redirect_location: str | None
    error_code: str | None
    error_message: str | None
    data_mode: str = PUBLIC_DERIVED


@dataclass(frozen=True)
class _AttemptResult:
    health_status: str = "failed"
    dns_status: str = "skipped"
    tcp_status: str = "skipped"
    tls_status: str = "skipped"
    http_status: str = "skipped"
    status_code: int | None = None
    resolved_addresses: tuple[str, ...] = ()
    connected_address: str | None = None
    redirect_location: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False


class MarketEndpointHealthClient:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
        resolver: Resolver | None = None,
        connector: Connector | None = None,
        tls_wrapper: TlsWrapper | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._resolver = resolver or _resolve_addresses
        self._connector = connector or _connect
        self._tls_wrapper = tls_wrapper or _wrap_tls
        self._sleep = sleep
        self._monotonic = monotonic

    def probe(self, target: MarketEndpointProbeTarget) -> MarketEndpointProbeResult:
        started_at = self._monotonic()
        parsed, validation_error = _validate_target(target)
        if validation_error is not None:
            return self._to_result(
                target,
                validation_error,
                attempt_count=1,
                started_at=started_at,
            )
        assert parsed is not None

        for attempt in range(self._max_retries + 1):
            result = self._probe_once(parsed)
            if not result.retryable or attempt >= self._max_retries:
                return self._to_result(
                    target,
                    result,
                    attempt_count=attempt + 1,
                    started_at=started_at,
                )
            delay = self._retry_backoff_seconds * (2**attempt)
            logger.warning(
                "Retrying market endpoint health probe endpoint=%s code=%s delay=%s",
                target.endpoint_id,
                result.error_code,
                delay,
            )
            self._sleep(delay)

        raise AssertionError("Market endpoint probe retry loop exited unexpectedly.")

    def _probe_once(self, parsed: ParseResult) -> _AttemptResult:
        assert parsed.hostname is not None
        hostname = parsed.hostname
        port = _port_for(parsed)
        try:
            addresses = tuple(self._resolver(hostname, self._timeout_seconds))
        except dns.exception.Timeout as exc:
            return _failure(
                dns_status="failed",
                error_code="market_endpoint_dns_timeout",
                error_message=f"DNS resolution timed out: {type(exc).__name__}.",
                retryable=True,
            )
        except (dns.exception.DNSException, OSError) as exc:
            return _failure(
                dns_status="failed",
                error_code="market_endpoint_dns_failed",
                error_message=f"DNS resolution failed: {type(exc).__name__}.",
                retryable=True,
            )
        if not addresses:
            return _failure(
                dns_status="failed",
                error_code="market_endpoint_dns_failed",
                error_message="DNS resolution returned no addresses.",
                retryable=True,
            )
        if invalid_address := _first_disallowed_address(addresses):
            return _failure(
                dns_status="succeeded",
                resolved_addresses=addresses,
                error_code="market_endpoint_address_not_public",
                error_message=f"Resolved address '{invalid_address}' is not public.",
            )

        connection: SocketLike | None = None
        connected_address: str | None = None
        tcp_errors: list[str] = []
        for address in addresses:
            try:
                connection = self._connector(address, port, self._timeout_seconds)
                connected_address = address
                break
            except OSError as exc:
                tcp_errors.append(type(exc).__name__)
        if connection is None:
            return _failure(
                dns_status="succeeded",
                tcp_status="failed",
                resolved_addresses=addresses,
                error_code="market_endpoint_tcp_failed",
                error_message=f"TCP connection failed: {', '.join(tcp_errors)}.",
                retryable=True,
            )

        transport = connection
        tls_status = "not_applicable"
        try:
            if parsed.scheme == "https":
                try:
                    transport = self._tls_wrapper(connection, hostname)
                except ssl.SSLCertVerificationError as exc:
                    return _failure(
                        dns_status="succeeded",
                        tcp_status="succeeded",
                        tls_status="failed",
                        resolved_addresses=addresses,
                        connected_address=connected_address,
                        error_code="market_endpoint_tls_validation_failed",
                        error_message=f"TLS certificate validation failed: {exc}.",
                    )
                except (OSError, ssl.SSLError) as exc:
                    return _failure(
                        dns_status="succeeded",
                        tcp_status="succeeded",
                        tls_status="failed",
                        resolved_addresses=addresses,
                        connected_address=connected_address,
                        error_code="market_endpoint_tls_failed",
                        error_message=f"TLS handshake failed: {type(exc).__name__}.",
                        retryable=True,
                    )
                tls_status = "succeeded"

            try:
                status_code, redirect_location = _send_head_request(
                    transport,
                    parsed=parsed,
                    hostname=hostname,
                )
            except OSError as exc:
                return _failure(
                    dns_status="succeeded",
                    tcp_status="succeeded",
                    tls_status=tls_status,
                    http_status="failed",
                    resolved_addresses=addresses,
                    connected_address=connected_address,
                    error_code="market_endpoint_http_failed",
                    error_message=f"HTTP HEAD request failed: {type(exc).__name__}.",
                    retryable=True,
                )
            except ValueError as exc:
                return _failure(
                    dns_status="succeeded",
                    tcp_status="succeeded",
                    tls_status=tls_status,
                    http_status="failed",
                    resolved_addresses=addresses,
                    connected_address=connected_address,
                    error_code="market_endpoint_http_invalid_response",
                    error_message=f"HTTP HEAD response was invalid: {exc}.",
                )

            if parsed.scheme == "http":
                health_status = "warning"
            elif status_code >= 300:
                health_status = "warning"
            else:
                health_status = "healthy"
            return _AttemptResult(
                health_status=health_status,
                dns_status="succeeded",
                tcp_status="succeeded",
                tls_status=tls_status,
                http_status="succeeded",
                status_code=status_code,
                resolved_addresses=addresses,
                connected_address=connected_address,
                redirect_location=redirect_location,
            )
        finally:
            transport.close()
            if transport is not connection:
                connection.close()

    def _to_result(
        self,
        target: MarketEndpointProbeTarget,
        attempt: _AttemptResult,
        *,
        attempt_count: int,
        started_at: float,
    ) -> MarketEndpointProbeResult:
        return MarketEndpointProbeResult(
            endpoint_id=target.endpoint_id,
            probe_url=target.canonical_url,
            probe_method=PROBE_METHOD,
            health_status=attempt.health_status,
            dns_status=attempt.dns_status,
            tcp_status=attempt.tcp_status,
            tls_status=attempt.tls_status,
            http_status=attempt.http_status,
            status_code=attempt.status_code,
            resolved_addresses=attempt.resolved_addresses,
            connected_address=attempt.connected_address,
            attempt_count=attempt_count,
            duration_ms=max(0, round((self._monotonic() - started_at) * 1000)),
            redirect_location=attempt.redirect_location,
            error_code=attempt.error_code,
            error_message=attempt.error_message,
        )


def _failure(
    *,
    dns_status: str = "skipped",
    tcp_status: str = "skipped",
    tls_status: str = "skipped",
    http_status: str = "skipped",
    resolved_addresses: tuple[str, ...] = (),
    connected_address: str | None = None,
    error_code: str,
    error_message: str,
    retryable: bool = False,
) -> _AttemptResult:
    return _AttemptResult(
        dns_status=dns_status,
        tcp_status=tcp_status,
        tls_status=tls_status,
        http_status=http_status,
        resolved_addresses=resolved_addresses,
        connected_address=connected_address,
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
    )


def _validate_target(
    target: MarketEndpointProbeTarget,
) -> tuple[ParseResult | None, _AttemptResult | None]:
    parsed = urlparse(target.canonical_url)
    if parsed.username is not None or parsed.password is not None:
        return None, _target_rejected("Market endpoint URLs must not include credentials.")
    if parsed.scheme not in {"http", "https"}:
        return None, _target_rejected("Market endpoint URLs must use HTTP or HTTPS.")
    if parsed.hostname is None:
        return None, _target_rejected("Market endpoint URLs must include a hostname.")
    try:
        port = parsed.port
    except ValueError:
        return None, _target_rejected("Market endpoint URLs must use a valid standard port.")
    if port not in {None, 80, 443}:
        return None, _target_rejected("Market endpoint URLs must not use custom ports.")
    if parsed.scheme == "http" and port not in {None, 80}:
        return None, _target_rejected("HTTP market endpoint URLs must use port 80.")
    if parsed.scheme == "https" and port not in {None, 443}:
        return None, _target_rejected("HTTPS market endpoint URLs must use port 443.")
    allowed_domains = {domain.lower() for domain in target.allowed_domains}
    if parsed.hostname.lower() not in allowed_domains:
        return None, _target_rejected("Market endpoint hostname is not registered.")
    if parsed.fragment:
        return None, _target_rejected("Market endpoint URLs must not include fragments.")
    return parsed, None


def _target_rejected(message: str) -> _AttemptResult:
    return _failure(
        error_code="market_endpoint_target_not_allowed",
        error_message=message,
    )


def _port_for(parsed: ParseResult) -> int:
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def _first_disallowed_address(addresses: tuple[str, ...]) -> str | None:
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return address
        if (
            parsed.is_loopback
            or parsed.is_private
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
            or not parsed.is_global
        ):
            return address
    return None


def _send_head_request(
    connection: SocketLike,
    *,
    parsed: ParseResult,
    hostname: str,
) -> tuple[int, str | None]:
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    request = (
        f"{PROBE_METHOD} {path} HTTP/1.1\r\n"
        f"Host: {hostname}\r\n"
        "Accept: */*\r\n"
        "Connection: close\r\n"
        "User-Agent: Example ProvincePowerTradingAI-MarketHealth/1.0\r\n"
        "\r\n"
    )
    connection.sendall(request.encode("ascii"))
    headers = _read_response_headers(connection)
    lines = headers.split("\r\n")
    status_parts = lines[0].split(" ", maxsplit=2)
    if len(status_parts) < 2 or not status_parts[0].startswith("HTTP/"):
        raise ValueError("missing HTTP status line")
    try:
        status_code = int(status_parts[1])
    except ValueError as exc:
        raise ValueError("invalid HTTP status code") from exc
    if not 100 <= status_code <= 599:
        raise ValueError("HTTP status code is out of range")
    redirect_location = None
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", maxsplit=1)
        if name.lower() == "location":
            redirect_location = value.strip()
            break
    return status_code, redirect_location


def _read_response_headers(connection: SocketLike) -> str:
    raw_headers = bytearray()
    while b"\r\n\r\n" not in raw_headers:
        remaining = MAX_RESPONSE_HEADER_BYTES - len(raw_headers)
        if remaining <= 0:
            raise ValueError("response headers exceed the configured limit")
        chunk = connection.recv(min(4096, remaining))
        if not chunk:
            raise ValueError("connection closed before response headers completed")
        raw_headers.extend(chunk)
    return bytes(raw_headers).split(b"\r\n\r\n", maxsplit=1)[0].decode("iso-8859-1")


def _resolve_addresses(hostname: str, timeout_seconds: float) -> list[str]:
    answers = dns.resolver.Resolver().resolve_name(hostname, lifetime=timeout_seconds)
    return sorted(set(answers.addresses()))


def _connect(address: str, port: int, timeout_seconds: float) -> SocketLike:
    return socket.create_connection((address, port), timeout=timeout_seconds)


def _wrap_tls(connection: SocketLike, hostname: str) -> SocketLike:
    context = ssl.create_default_context()
    return cast(
        SocketLike,
        context.wrap_socket(cast(socket.socket, connection), server_hostname=hostname),
    )
