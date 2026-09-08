# Public Market Artifact Foundation

## Purpose

This stage builds an auditable landing zone for official public market
artifacts. It intentionally does not create a Example Province spot-price series or
assume that an anonymous 96-point curve is currently available.

Official information disclosure rules distinguish:

- information available to the general public
- information disclosed to all market participants
- information disclosed only to specific market participants

`data_mode` describes provenance. `visibility_scope` and `access_mode`
separately describe who may access an endpoint and how.

## Registered Endpoints

| Endpoint id | URL | Boundary |
| --- | --- | --- |
| `example_province_portal_home` | <https://portal.market.example.invalid/portal/> | Anonymous HTTPS frontend shell verified. Structured API contract unverified. |
| `reports_market_research` | <http://reports.market.example.invalid/news/scyj/> | Public weekly and monthly regional reports. Trusted HTTPS currently fails hostname validation, so automated collection is disabled. |
| `reports_market_research_https_candidate` | <https://reports.market.example.invalid/news/scyj/> | Read-only TLS health-check candidate. Trusted HTTPS currently fails hostname validation. |
| `southern_spot_public_frontend` | <https://spot.market.example.invalid/uptspot/sr/pt/> | Anonymous frontend shell verified. Public API fields and market scope remain unverified. |

Do not relabel regional market material as a Example Province 96-point spot-price
curve. Do not automate login or collect market-participant-only information.

## Storage Layers

The foundation deliberately separates:

1. `market_data_sources`: stable operators and source identities.
2. `market_source_endpoints`: URLs, access classification, independent health
   check, manual submission, and future collection capabilities, cooldown
   lease state, and future adapter metadata.
3. `market_raw_artifacts`: immutable content with SHA-256, byte size, capture
   metadata, and a storage backend marker.
4. `market_ingestion_runs` and `market_ingestion_run_items`: batch and
   item-level outcomes.
5. `market_quality_issues`: derived issues at source, endpoint, run, or
   artifact scope.
6. `market_endpoint_health_checks`: structured results for manually triggered
   read-only DNS, TCP, TLS, and HTTP `HEAD` probes.

`market_raw_artifacts` currently uses `postgres_inline`. The schema reserves an
object key for a future MinIO-backed implementation without enabling binary
archival in this stage.

## Manual Preservation

`POST /v1/market/artifacts/manual` accepts caller-supplied textual public
content and metadata. It:

1. Requires a registered endpoint id.
2. Requires explicit `manual_submission_enabled` permission and allows only
   registered hosts without credentials or custom ports.
3. Preserves submitted text exactly and never fetches the submitted URL.
4. Deduplicates unchanged content within the same source using SHA-256.
5. Records a run, an item result, and derived quality findings.
6. Allows registered HTTP-only sources for manual review while emitting an
   `insecure_transport_source` warning.

Supported media types:

- `text/html`
- `text/plain`
- `text/csv`
- `text/xml`
- `application/json`
- `application/xml`

## Next Gate

The first source-specific parser may operate only on preserved, reviewed
artifacts. Before adding an automated adapter:

1. Confirm a trusted anonymous HTTPS endpoint.
2. Record whether it exposes day-ahead, real-time, aggregate, or 96-point data.
3. Verify units, timestamps, market scope, historical coverage, and revision
   behavior.
4. Add timeout, retry, deduplication, raw preservation, and parser tests.

The first parser is documented in
[`reports_weekly_market_parser.md`](reports_weekly_market_parser.md). It operates on
manually preserved and approved HTML artifacts while automated HTTP collection
remains disabled.

## Endpoint Health Checks

`POST /v1/market/endpoints/{endpoint_id}/health-checks` probes only a registered
endpoint's fixed `canonical_url`. The isolated client:

1. Rejects credentials, custom ports, unregistered hosts, and non-public
   resolved addresses before connecting.
2. Resolves DNS with a hard timeout, connects to a validated address, records
   the actual connected IP, performs default-validated TLS when required, and
   sends an HTTP `HEAD` request on the same connection.
3. Uses explicit timeout, bounded retry, capped response headers, no body
   download, no cookie storage, and no redirect following.
4. Persists successful and failed results with `public_derived` provenance.
5. Associates derived TLS, HTTP, redirect, and insecure-HTTP findings with the
   exact health-check record.
6. Atomically leases an endpoint cooldown before DNS resolution. Requests
   inside the configured minimum interval return `429` without external
   access.

`GET /v1/market/health/checks` exposes the audit history. A successful probe
does not change `lifecycle_status` or `collection_enabled`. Automated
collection remains a separate human-approved gate.

The read-only anonymous field research checkpoint is documented in
[`anonymous_market_field_verification.md`](anonymous_market_field_verification.md).
It keeps the adapter-design gate `blocked`: the reviewed REPORTS report is weekly
aggregate context, while the anonymous HTTPS frontend shells still lack a
verified Example Province price-field contract.
