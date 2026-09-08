# Market Endpoint Health Foundation

## Purpose

This stage adds manually triggered, read-only health probes for registered
public market endpoints. It verifies transport reachability without enabling
automated collection or interpreting anonymous market fields.

## API

- `POST /v1/market/endpoints/{endpoint_id}/health-checks`
- `GET /v1/market/health/checks?endpoint_id={endpoint_id}&limit=100`

The POST endpoint accepts no request body and no caller-supplied URL. Missing
endpoints return `404`. Restricted, market-participant, login-required, and
health-check-disabled endpoints return `409` before any external access.
Each endpoint has independent `health_check_enabled`,
`manual_submission_enabled`, and `collection_enabled` capabilities. A
successful health check does not grant either submission or collection
permission.

## Probe Sequence

For a registered anonymous endpoint, `MarketEndpointHealthClient`:

1. Validates the fixed canonical URL and registered host allowlist.
2. Resolves A and AAAA records through the system DNS configuration with a hard
   lifetime, then rejects loopback, private, link-local, multicast, reserved,
   unspecified, or otherwise non-public addresses.
3. Opens TCP to a validated public address with an explicit timeout.
4. Uses system-default TLS verification for HTTPS endpoints.
5. Sends HTTP `HEAD` with a fixed `Host` header over the validated connection.
6. Reads capped response headers only, records every `3xx` response without
   following it, and stores no cookies.

Transient DNS, TCP, TLS transport, and HTTP transport errors use bounded retry
with exponential backoff. Certificate validation failures are preserved
without bypassing verification.

## Audit Storage

`market_endpoint_health_checks` records the probe URL, method, overall status,
stage statuses, all resolved public addresses, the actual connected address,
attempt count, duration, HTTP status, redirect location, structured failure,
and `public_derived` provenance. Derived quality findings reference the exact
check through `market_quality_issues.endpoint_health_check_id`.

Before external access, the service atomically advances
`market_source_endpoints.health_probe_not_before`. Repeated requests within
`MARKET_HEALTH_MIN_INTERVAL_SECONDS` return `429` with
`market_endpoint_probe_rate_limited` and perform no DNS lookup or connection.

The registry includes `reports_market_research_https_candidate` for explicit
TLS-failure audits while retaining `reports_market_research` HTTP artifacts for
manual preservation. Neither endpoint is enabled for automated collection.
