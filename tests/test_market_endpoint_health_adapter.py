from __future__ import annotations

import ssl
from collections.abc import Callable

import dns.exception
import dns.resolver

from backend.app.adapters.market_endpoint_health import (
    MarketEndpointHealthClient,
    MarketEndpointProbeTarget,
    SocketLike,
)

PUBLIC_ADDRESS = "93.184.216.34"


class FakeSocket:
    def __init__(self, response: bytes = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n") -> None:
        self.response = response
        self.sent: list[bytes] = []
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, _bufsize: int) -> bytes:
        response = self.response
        self.response = b""
        return response

    def close(self) -> None:
        self.closed = True


class RecordingConnector:
    def __init__(self, outcomes: list[SocketLike | OSError]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, int, float]] = []

    def __call__(self, address: str, port: int, timeout_seconds: float) -> SocketLike:
        self.calls.append((address, port, timeout_seconds))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, OSError):
            raise outcome
        return outcome


def target(
    canonical_url: str = "https://example.com/public/",
    *,
    allowed_domains: tuple[str, ...] = ("example.com",),
) -> MarketEndpointProbeTarget:
    return MarketEndpointProbeTarget(
        endpoint_id="public_example",
        canonical_url=canonical_url,
        allowed_domains=allowed_domains,
    )


def build_client(
    connector: RecordingConnector,
    *,
    resolver: Callable[[str, float], list[str]] = lambda _hostname, _timeout: [PUBLIC_ADDRESS],
    tls_wrapper: Callable[[SocketLike, str], SocketLike] = lambda connection, _hostname: connection,
    max_retries: int = 0,
    sleep: Callable[[float], None] = lambda _delay: None,
) -> MarketEndpointHealthClient:
    return MarketEndpointHealthClient(
        timeout_seconds=3,
        max_retries=max_retries,
        retry_backoff_seconds=0.25,
        resolver=resolver,
        connector=connector,
        tls_wrapper=tls_wrapper,
        sleep=sleep,
    )


def test_https_probe_reuses_validated_connection_for_head_request() -> None:
    connection = FakeSocket()
    connector = RecordingConnector([connection])

    result = build_client(connector).probe(target())

    assert result.health_status == "healthy"
    assert result.dns_status == "succeeded"
    assert result.tcp_status == "succeeded"
    assert result.tls_status == "succeeded"
    assert result.http_status == "succeeded"
    assert result.status_code == 200
    assert result.resolved_addresses == (PUBLIC_ADDRESS,)
    assert result.connected_address == PUBLIC_ADDRESS
    assert connector.calls == [(PUBLIC_ADDRESS, 443, 3)]
    assert connection.sent == [
        (
            b"HEAD /public/ HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Accept: */*\r\n"
            b"Connection: close\r\n"
            b"User-Agent: Example ProvincePowerTradingAI-MarketHealth/1.0\r\n"
            b"\r\n"
        )
    ]
    assert connection.closed is True


def test_http_only_probe_is_reachable_with_warning_without_tls() -> None:
    connector = RecordingConnector([FakeSocket()])

    result = build_client(connector).probe(target("http://example.com/public/"))

    assert result.health_status == "warning"
    assert result.tls_status == "not_applicable"
    assert result.status_code == 200
    assert result.connected_address == PUBLIC_ADDRESS
    assert connector.calls == [(PUBLIC_ADDRESS, 80, 3)]


def test_tls_hostname_mismatch_returns_structured_failure() -> None:
    connector = RecordingConnector([FakeSocket()])

    def reject_tls(_connection: SocketLike, _hostname: str) -> SocketLike:
        raise ssl.SSLCertVerificationError(1, "hostname mismatch")

    result = build_client(connector, tls_wrapper=reject_tls).probe(target())

    assert result.health_status == "failed"
    assert result.dns_status == "succeeded"
    assert result.tcp_status == "succeeded"
    assert result.tls_status == "failed"
    assert result.http_status == "skipped"
    assert result.error_code == "market_endpoint_tls_validation_failed"
    assert result.connected_address == PUBLIC_ADDRESS


def test_dns_failure_returns_structured_failure() -> None:
    connector = RecordingConnector([])

    def reject_dns(_hostname: str, _timeout_seconds: float) -> list[str]:
        raise dns.resolver.NXDOMAIN

    result = build_client(connector, resolver=reject_dns).probe(target())

    assert result.dns_status == "failed"
    assert result.tcp_status == "skipped"
    assert result.error_code == "market_endpoint_dns_failed"
    assert connector.calls == []


def test_dns_timeout_is_retried_with_hard_lifetime() -> None:
    connector = RecordingConnector([FakeSocket()])
    resolver_calls: list[tuple[str, float]] = []
    delays: list[float] = []

    def resolve_after_timeout(hostname: str, timeout_seconds: float) -> list[str]:
        resolver_calls.append((hostname, timeout_seconds))
        if len(resolver_calls) == 1:
            raise dns.exception.Timeout
        return [PUBLIC_ADDRESS]

    result = build_client(
        connector,
        resolver=resolve_after_timeout,
        max_retries=1,
        sleep=delays.append,
    ).probe(target())

    assert result.health_status == "healthy"
    assert result.attempt_count == 2
    assert resolver_calls == [("example.com", 3), ("example.com", 3)]
    assert delays == [0.25]


def test_tcp_failure_returns_structured_failure() -> None:
    connector = RecordingConnector([TimeoutError("timed out")])

    result = build_client(connector).probe(target())

    assert result.dns_status == "succeeded"
    assert result.tcp_status == "failed"
    assert result.error_code == "market_endpoint_tcp_failed"


def test_transient_tcp_failure_is_retried_with_exponential_backoff() -> None:
    connector = RecordingConnector([TimeoutError("timed out"), FakeSocket()])
    delays: list[float] = []

    result = build_client(connector, max_retries=1, sleep=delays.append).probe(target())

    assert result.health_status == "healthy"
    assert result.attempt_count == 2
    assert len(connector.calls) == 2
    assert delays == [0.25]


def test_private_address_is_rejected_before_connecting() -> None:
    connector = RecordingConnector([])

    result = build_client(
        connector,
        resolver=lambda _hostname, _timeout: ["127.0.0.1"],
    ).probe(target())

    assert result.dns_status == "succeeded"
    assert result.tcp_status == "skipped"
    assert result.error_code == "market_endpoint_address_not_public"
    assert connector.calls == []


def test_unregistered_domain_is_rejected_before_dns_resolution() -> None:
    connector = RecordingConnector([])
    resolver_calls: list[tuple[str, float]] = []

    def resolver(hostname: str, timeout_seconds: float) -> list[str]:
        resolver_calls.append((hostname, timeout_seconds))
        return [PUBLIC_ADDRESS]

    result = build_client(connector, resolver=resolver).probe(
        target(allowed_domains=("official.example",))
    )

    assert result.error_code == "market_endpoint_target_not_allowed"
    assert resolver_calls == []
    assert connector.calls == []


def test_custom_port_is_rejected_before_dns_resolution() -> None:
    connector = RecordingConnector([])
    resolver_calls: list[tuple[str, float]] = []

    def resolver(hostname: str, timeout_seconds: float) -> list[str]:
        resolver_calls.append((hostname, timeout_seconds))
        return [PUBLIC_ADDRESS]

    result = build_client(connector, resolver=resolver).probe(target("https://example.com:8443/"))

    assert result.error_code == "market_endpoint_target_not_allowed"
    assert resolver_calls == []
    assert connector.calls == []


def test_http_error_status_is_preserved_as_reachable_warning() -> None:
    connection = FakeSocket(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n")
    connector = RecordingConnector([connection])

    result = build_client(connector).probe(target())

    assert result.health_status == "warning"
    assert result.http_status == "succeeded"
    assert result.status_code == 503


def test_tcp_fallback_persists_actual_connected_address() -> None:
    alternate_address = "93.184.216.35"
    connector = RecordingConnector([TimeoutError("timed out"), FakeSocket()])

    result = build_client(
        connector,
        resolver=lambda _hostname, _timeout: [PUBLIC_ADDRESS, alternate_address],
    ).probe(target())

    assert result.health_status == "healthy"
    assert result.resolved_addresses == (PUBLIC_ADDRESS, alternate_address)
    assert result.connected_address == alternate_address
    assert connector.calls == [
        (PUBLIC_ADDRESS, 443, 3),
        (alternate_address, 443, 3),
    ]


def test_redirect_is_recorded_without_following_location() -> None:
    connection = FakeSocket(
        b"HTTP/1.1 302 Found\r\nLocation: https://example.com/next\r\nContent-Length: 0\r\n\r\n"
    )
    connector = RecordingConnector([connection])

    result = build_client(connector).probe(target())

    assert result.health_status == "warning"
    assert result.status_code == 302
    assert result.redirect_location == "https://example.com/next"
    assert len(connector.calls) == 1
    assert len(connection.sent) == 1


def test_redirect_without_location_is_still_a_warning() -> None:
    connection = FakeSocket(b"HTTP/1.1 304 Not Modified\r\nContent-Length: 0\r\n\r\n")
    connector = RecordingConnector([connection])

    result = build_client(connector).probe(target())

    assert result.health_status == "warning"
    assert result.status_code == 304
    assert result.redirect_location is None
