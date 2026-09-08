# Data Source Policy

This project currently has no verified internal company data. All company-side
inputs must be treated as public, derived, uploaded, or simulated.

## Data Modes

| Mode | Meaning | Example |
| --- | --- | --- |
| `public_observed` | Directly observed public data | Official policy page, public weather API |
| `public_derived` | Derived from public data with documented assumptions | Rainfall index from several stations |
| `scenario_simulated` | Synthetic scenario data for demos and stress tests | Simulated Demo Hydro A storage state |
| `user_uploaded` | Data explicitly provided by the user | Later CSV or Excel uploads |

## Source Priority

1. Official APIs or machine-readable public data.
2. Official pages, PDFs, notices, and reports.
3. Credible secondary sources that cite official data.
4. Scenario simulations with explicit assumptions.

## Weather Providers

Use Open-Meteo as the default no-key provider. Use QWeather for China-focused
weather, warning, rainfall, and typhoon features when the user provides a key.
Use Amap as a city-level fallback when configured.

Required weather fields:

- provider
- location id
- latitude and longitude when available
- issue time
- forecast time or observation time
- variable
- value
- unit
- raw payload reference
- quality flag

## Open-Meteo Ingestion

Open-Meteo forecast ingestion is manually triggered in the data-foundation
stage. The endpoint requires an explicit reference-point `location_id`,
latitude, longitude, and timezone. These coordinates are analysis inputs, not
verified hydropower-station sensor coordinates.

Each fetch preserves:

- full request URL and parameters
- provider and fetch timestamp
- raw response text and parsed JSON when valid
- raw payload content hash
- normalized hourly record hashes
- ingestion success or structured failure details

An unchanged normalized record is deduplicated by provider, reference location,
forecast time, variable, value, and unit. A changed forecast value is stored as
a new record so forecast revisions remain visible.

Open-Meteo does not provide a separate forecast issue timestamp in this
response. Store the retrieval start timestamp as the provider-specific
`issue_time` proxy and preserve the raw payload for later review.

## Weather Cleaning And Derived Features

Do not overwrite or silently discard Open-Meteo values during cleaning.
Preserve normalized values as `public_observed`, including local missing
values, and store quality findings separately as `public_derived`.

The initial quality checks cover:

- local missing values
- non-continuous hourly timestamps
- unexpected units
- conservative review ranges for temperature, precipitation, rain, weather
  code, cloud cover, and wind speed
- hourly rain values that exceed hourly total precipitation

Derived hydro-weather features are also `public_derived`. Each feature snapshot
must preserve its version, raw payload id, source record ids, formulas,
evidence, quality status, and missing-data warnings. Do not publish partial
window aggregates when required hourly inputs are incomplete or suspect.

## Weather Feature Review Gate

Weather features may be attached to a recommendation input snapshot only when:

- the feature snapshot is explicitly selected by id
- automated quality status is `valid`
- a human reviewer has explicitly approved the snapshot
- all required feature values are present
- the forecast window starts on the recommendation trade date

The attachment adds auditable public-derived context and structured evidence.
It does not automatically change hydro strategy actions or confidence scores.

## Demo Hydro A Scenario Data

Scenario data may use public information about Demo Hydro A hydropower
station and nearby hydrology. It must include:

- scenario id
- public assumptions used
- generation date
- variable names and units
- explicit `scenario_simulated` data mode
- warning that it is not verified internal company data

Suggested scenario families:

- wet season high-storage pressure
- normal storage and normal inflow
- dry season low-storage conservation
- flood-control pressure
- evening peak water-value preservation
- medium-long contract short exposure
- medium-long contract long exposure

## Recommendation Evidence

Every recommendation should cite structured evidence:

```json
{
  "source": "open_meteo",
  "source_type": "weather_api",
  "data_mode": "public_observed",
  "timestamp": "2026-06-01T08:00:00+08:00",
  "field": "precipitation_sum_72h_mm",
  "value": 48.5,
  "unit": "mm",
  "confidence": 0.85,
  "url": "https://open-meteo.com/"
}
```

Every persisted recommendation must also reference the exact input snapshot
used for generation. Human reviews are stored separately from the generated
draft so later analysis can distinguish model or rule output from operator
feedback.

Recommendation evidence audit and evidence export are read-only derived views.
They may summarize or package evidence counts, missing-data warnings, data
modes, review status, safety flags, checks, recommended actions, and structured
evidence, but they must not collect new data, call external models, alter
confidence, write audit events, approve drafts, or execute trades. A
recommendation remains operator-reviewed decision support only.

Audit-critical evidence boundaries:

- `no_auto_trading` must stay true.
- `human_check_required` must stay true.
- company-side scenario inputs must stay explicitly `scenario_simulated` unless
  the user later provides verified internal data.
- BENCH, `research_only`, and policy-watch observations must not appear in
  recommendation evidence.

Warnings, not blockers, include missing internal reservoir telemetry,
medium-long contract positions, Example Province 96-point spot curves, and unlinked
approved public-derived weather feature snapshots. These warnings guide human
review and do not automatically reject or approve a draft.

Recommendation decision feedback is manual `user_uploaded` operator context.
It can record whether an audited scenario draft was adopted, partially adopted,
not adopted, or deferred, and later record subjective follow-up outcomes. It is
not evidence generation, not a trading instruction, and not a signal to
automatically adjust confidence or future strategy. BENCH, `research_only`, and
policy-watch observations remain excluded from the recommendation evidence
chain even when an operator writes free-text feedback.

Recommendation feedback analytics is a read-only summary over that local
operator context. Counts, pending-observation lists, and critical-audit
not-adopted notes are for personal review only. Audit status counts and review
status counts are local workload indicators for pending reviews and warning or
critical audit pressure; they do not trigger collection, external model calls,
confidence updates, recommendation approval, or trading execution.

## Public Market Artifacts

Official market information must record both provenance and access boundary.
`data_mode` alone is insufficient: information available to the general public
is not equivalent to information disclosed only to market participants or
specific participants.

Use these endpoint fields:

| Field | Values |
| --- | --- |
| `visibility_scope` | `internet_public`, `market_participant_public`, `restricted`, `unknown` |
| `access_mode` | `anonymous_https`, `anonymous_http_only`, `member_login_required`, `manual_submission_only`, `unknown` |
| `lifecycle_status` | `discovered`, `candidate_unverified`, `verified`, `blocked_tls`, `disabled` |
| `health_check_enabled` | Allows manually triggered read-only health probes only |
| `manual_submission_enabled` | Allows caller-supplied textual artifact preservation only |
| `collection_enabled` | Future automated collection gate; remains `false` in this stage |

Initial registered endpoints:

| Endpoint id | URL | Initial state |
| --- | --- | --- |
| `example_province_portal_home` | <https://portal.market.example.invalid/portal/> | Anonymous frontend shell only; API unverified |
| `reports_market_research` | <http://reports.market.example.invalid/news/scyj/> | Public reports; automated collection blocked by TLS hostname validation |
| `reports_market_research_https_candidate` | <https://reports.market.example.invalid/news/scyj/> | Read-only TLS health-check candidate; automated collection disabled |
| `southern_spot_public_frontend` | <https://spot.market.example.invalid/uptspot/sr/pt/> | Anonymous frontend shell only; API unverified |

Do not label regional disclosure material as a Example Province 96-point spot-price
curve. Verify anonymous access, fields, granularity, and historical coverage
before adding an automated source adapter.

The manual preservation endpoint accepts textual public artifacts from
registered hosts. It stores submitted content and SHA-256 but does not fetch
caller-supplied URLs. Registered HTTP-only sources produce an explicit
`insecure_transport_source` warning. Textual preservation is
`public_observed`; quality findings and registry metadata are `public_derived`.

Binary archival, MinIO object storage, automated crawling, normalized price
records, and forecasting remain later-stage work.

Read-only endpoint health checks accept a registered endpoint id only. They
must use its fixed canonical URL, reject private or otherwise non-public
resolved addresses before connection, resolve DNS under a hard timeout, retain
default TLS validation, record the actual connected IP, perform HTTP `HEAD`
without following redirects, and persist both successful and failed results.
An endpoint-level persisted cooldown rejects repeated requests before DNS
resolution. Health checks never enable collection automatically.

## REPORTS Weekly Aggregate Observations

`reports_weekly_market_report:v1` may parse only preserved
`reports_market_research` HTML artifacts with an explicit human approval. It
normalizes:

- Southern-region and provincial observations
- day-ahead and real-time stages
- average traded energy in `100_million_kwh`
- weighted average price in `cny_per_mwh`
- generation-side preliminary flash-report status

These observations are `public_observed` values derived through deterministic
format parsing. Parser-version metadata and raw artifact references must remain
attached. Do not use weekly aggregate values as a substitute for an anonymous
official 96-point series, as a forecasting target, or as an automatic
recommendation input.

The latest anonymous official-entry research checkpoint is recorded in
[`anonymous_market_field_verification.md`](anonymous_market_field_verification.md).

## Crawler Reference Boundary

Crawler libraries may be studied for implementation patterns, but project
adapters must remain source-specific and registry-gated. The local Scrapling
research note is recorded in
[`scrapling_safety_research.md`](scrapling_safety_research.md).

Allowed patterns include injected fetch functions for testability, robots.txt
checks for crawlable web pages, per-domain delay, scheduler deduplication,
bounded retry, checkpoint metadata, and static fixture tests.

Rejected patterns include anti-bot bypass, browser stealth, TLS or browser
fingerprint impersonation, proxy rotation, login or captcha automation, cookie
replay, arbitrary URL tools, and AI browsing outside the fixed source registry.
These capabilities must not be connected to workstation jobs, policy
collection, market evidence, or Example Province recommendation generation.

Registered source collection uses project-native adapters rather than crawler
runtime dependencies. The first generic adapter key is
`registered_static_http:v1`: it may fetch only the canonical URL stored on a
verified `market_source_endpoints` row with `collection_enabled=true`,
`access_mode=anonymous_https`, a matching allowlisted host, and a reviewed
adapter key. It checks robots.txt, rejects redirects, non-standard ports,
credentials, unsupported media types, oversized responses, TLS failures, and
unregistered hosts, and records ingestion runs and quality issues without
falling back to stealth, proxy, login, captcha, or arbitrary URL behavior.

## Interval Forecasting Research Data

Public interval curves from another region or market may be used to validate
forecasting infrastructure only when they retain explicit source metadata,
market scope, price scope, timezone, currency, interval granularity, and data
mode. They must also use `usage_scope=research_only`.

`research_only` inputs and model runs must not be linked to Example Province
recommendations or used to increase recommendation confidence. A source-native
five-minute or hourly curve must be preserved before any explicit 15-minute
derivation. It must not be relabeled as a directly observed Example Province 96-point
curve.
Its adapter-design gate remains `blocked` until a trusted anonymous HTTPS
contract exposes reproducible Example Province price-field semantics, units,
timestamps, interval granularity, historical coverage, and revision behavior.

## BENCH Dispatch Research Benchmark

The BENCH DispatchIS archive adapter is a separate research benchmark source. It
fetches only official daily ZIP filenames from the fixed BENCH NEMWeb DispatchIS
archive directory. It does not accept arbitrary URLs, describe BENCH regions as
Example Province regions, or connect to recommendation generation.

The adapter preserves daily ZIP, nested five-minute ZIP, and CSV metadata with
SHA-256 hashes. It parses regional `RRP` while retaining source-native revision
fields. It then explicitly derives each 15-minute benchmark point from the
arithmetic mean of three consecutive five-minute values. Source-native rows are
`public_observed`; aggregated benchmark datasets are `public_derived` and
always `research_only`.
