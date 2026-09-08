# Architecture

The first MVP skeleton uses a Docker-started vertical slice:

- FastAPI for typed backend APIs.
- React for the primary operator-facing intelligence cockpit.
- PostgreSQL for core audit and recommendation tables.
- Alembic for all database schema changes.
- MinIO for SHA-256-deduplicated raw binary objects and local document storage.

The first recommendation flow is intentionally scenario-based. It uses public
Demo Hydro A assumptions and marks every company-side input as
`scenario_simulated`.

Each recommendation run persists:

1. A `feature_snapshots` row containing the exact simulated scenario input and
   evidence used for generation.
2. A `recommendation_runs` draft with its latest review status.
3. An `audit_events` entry for generation.

Human review is append-only in `recommendation_reviews`. The draft keeps the
latest status for efficient display while review rows preserve the full
approved, rejected, or needs-revision history.

`GET /v1/recommendations/{recommendation_id}/audit` is a read-only operator
diagnostic over the stored draft. It derives evidence counts, missing-data
counts, data-mode summaries, safety checks, and recommended follow-up actions
from the existing strategy JSON, evidence, and review status. The audit marks
missing internal reservoir data, medium-long positions, Example Province 96-point spot
curves, and unlinked approved weather context as warnings for human review. It
marks disabled safety flags or BENCH, `research_only`, or policy-watch evidence
inside the recommendation chain as critical. It does not mutate recommendation
content, change confidence, call external models, start collection, or execute
trades.

`GET /v1/recommendations/{recommendation_id}/evidence-export` packages the
stored draft metadata, input snapshot id, current review and audit status,
missing-data warnings, checks, recommended actions, and evidence into a
copyable JSON review package. It is read-only and does not create audit rows,
change recommendation state, call external models, start collection, or execute
trades.

Recommendation decisions and decision feedback are append-only local operator
records. `recommendation_decisions` stores the human decision, selected windows,
safety-boundary acknowledgement, no-auto-trading flag, and the current audit
snapshot. `recommendation_decision_feedback` stores later subjective outcome
notes as `user_uploaded` records. Critical audit snapshots block adopted or
partially adopted decisions, but still allow not-adopted or deferred notes so
unsafe drafts can be explained. These tables do not mutate the recommendation
draft, strategy JSON, confidence, or review status.

`GET /v1/recommendations/feedback/overview` derives a read-only operator
analytics view from the same local decision and feedback tables. It aggregates
decision statuses, outcome statuses, pending observations, critical-audit
not-adopted notes, audit status counts, review status counts, and follow-up
actions. The status counts are local workload indicators for pending reviews
and warning or critical audit pressure. The endpoint does not run collectors,
call external models, change recommendation state, or represent executed trades
or real trading performance.

## v0.1 RC Readiness And Demo Seed

`GET /v1/system/readiness` is a read-only release-candidate checklist. It
summarizes database migration visibility, key table counts, local demo fixture
presence, Action Center todo pressure, policy corpus coverage, brief review,
recommendation feedback, forecast research coverage, and hard recommendation
evidence isolation. It does not run network probes, fetch pages, call external
models, train or promote forecasting models, mutate recommendations, or execute
trading actions.

`demo_research_workspace_seed` is a fixed workstation job for local
demonstration only. It writes deterministic records for a weather feature
snapshot, preserved market artifact, policy knowledge document, daily brief,
scenario recommendation, decision feedback, forecast research dataset, and a
candidate seasonal-naive backtest. It uses fixed identifiers, so repeated runs
reuse existing demo records instead of creating unbounded duplicates.

The seed keeps the MVP safety boundary explicit:

1. Weather and model-run derived values are marked `public_derived`.
2. Policy artifacts, policy documents, decisions, and feedback are
   `user_uploaded` local fixtures.
3. Recommendation inputs are `scenario_simulated` and keep
   `no_auto_trading=true`.
4. Forecast research fixtures remain `research_only` and `candidate`.
5. BENCH, `research_only`, and policy-watch evidence remain outside the
   Example Province recommendation evidence chain.

## Open-Meteo Data Foundation

The weather slice is intentionally isolated from recommendation generation
until its reference locations and feature definitions have been reviewed.

Manual ingestion follows:

1. Validate the caller-supplied public reference location and requested hourly
   variables.
2. Fetch `https://api.open-meteo.com/v1/forecast` with an explicit timeout and
   bounded exponential retry.
3. Preserve the raw response content, request URL, parameters, provider, fetch
   time, quality flag, and content hash in `weather_raw_payloads`.
4. Normalize each hourly variable into `weather_records`.
5. Deduplicate unchanged raw payloads and normalized records by content hash.
6. Record each success or failure in `weather_ingestion_runs`.

`weather_locations` prevents a known `location_id` from being silently remapped
to different coordinates or a different timezone. Location metadata is
`public_derived`; Open-Meteo forecast values are `public_observed`.

The scheduled workstation collector enables `demo_hydro_a_reference` at
`30.0, 110.0` as an `unverified_analysis_input`. It is a public analysis
reference point, not a verified station sensor or internal operational input.

Open-Meteo does not expose a separate forecast issue timestamp in this
response. `weather_records.issue_time` therefore stores the retrieval start
time as an explicit provider-specific proxy.

This stage stores raw payloads in PostgreSQL so the first weather integration is
self-contained and testable. A later ingestion stage can move larger raw
artifacts to MinIO while retaining their object keys and hashes in PostgreSQL.

## Weather Quality And Features

The cleaning layer keeps observed values separate from derived judgments:

1. `weather_records` preserves normalized Open-Meteo values as
   `public_observed`, including local `null` values.
2. `weather_quality_issues` stores `public_derived` findings for missing values,
   unexpected hourly intervals, unexpected units, conservative range checks,
   and inconsistent precipitation components.
3. `weather_feature_snapshots` stores versioned `public_derived` aggregates with
   source record ids, raw payload references, evidence, and missing-data
   warnings.

The first feature version, `hydro_weather_v1`, calculates complete-window
precipitation and rain sums for 24 and 72 hours plus 24-hour temperature mean,
minimum, and maximum. A missing or suspect source value keeps the affected
feature empty rather than publishing a partial aggregate.

## Weather Feature Review And Recommendation Linking

Every generated weather feature snapshot starts with
`human_review_status=pending_review`. Reviews are append-only in
`weather_feature_reviews`; the snapshot stores the latest status for efficient
queries.

Approval is blocked unless:

1. The automated quality status is `valid`.
2. Every derived feature value is present.
3. The forecast window start is recorded.

Recommendation generation accepts an optional explicit
`weather_feature_snapshot_id`. The linked snapshot must be approved and its
forecast window must start on the requested trade date. Approved weather
features are copied into the immutable recommendation input snapshot and added
as structured evidence. They do not alter strategy actions or confidence
scores in this stage.

`GET /v1/weather/features/{feature_snapshot_id}/review-package` is the
operator-facing inspection package for one feature snapshot. It combines the
snapshot, related quality issues for the same raw payload, historical reviews,
approval blockers, and safety flags. It is read-only, does not invoke the
Open-Meteo adapter, does not write server-side report artifacts, does not
approve or reject the snapshot, and does not mutate recommendation evidence.

Feature snapshots created before the review migration may not have a forecast
window start. Regenerate them through weather ingestion before approval.

## Public Market Artifact Foundation

The public-market slice separates provenance from access policy. A source can
be official while a specific endpoint remains unverified, HTTP-only, limited
to market participants, or disabled.

1. `market_data_sources` stores stable operators and source identities.
2. `market_source_endpoints` stores concrete URLs, allowed hosts, visibility,
   access mode, lifecycle state, independent health-check, manual-submission,
   and future collection capabilities, persisted cooldown state, and future
   adapter metadata.
3. `market_raw_artifacts` stores immutable content, hashes, byte sizes, capture
   metadata, and either inline text or a future object key.
4. `market_ingestion_runs` and `market_ingestion_run_items` preserve batch and
   item-level success, duplicate, rejection, and failure outcomes.
5. `market_quality_issues` stores derived findings at source, endpoint, run, or
   artifact scope. Artifact references are optional so TLS failures can be
   represented before content exists.
6. `market_endpoint_health_checks` stores manually triggered DNS, TCP, TLS, and
   HTTP `HEAD` probe results. `market_quality_issues` may reference a specific
   check so transport and address-safety failures remain auditable.

Deduplication uses source id and SHA-256, so identical text from separate
official sources retains separate provenance. The manual endpoint validates a
submitted URL but never fetches it. Registered HTTP-only sources may be
preserved manually with a warning; they cannot be collected automatically.

This stage does not add spot-price records, infer 96-point curves, alter
recommendations, automate login, disable TLS validation, or archive binary
files to MinIO. A later parser may normalize reviewed artifacts before trusted
anonymous HTTPS crawling is available.

`GET /v1/market/artifacts/{artifact_id}/review-package` is the operator-facing
inspection package for one preserved public artifact. It combines source and
endpoint metadata, artifact hash and storage metadata, artifact-scoped quality
issues, review history, parser run history, and safety flags. The package omits
the full inline body and is downloaded in the browser. It is read-only: it does
not fetch the source URL, run endpoint probes, parse the artifact, approve or
reject the artifact, write a server-side report, or mutate recommendation
evidence.

Endpoint health probes are isolated from collection. They accept an endpoint
id only, use the registered canonical URL, reject non-public resolved
addresses, apply a hard DNS lifetime, connect to and record the validated IP,
preserve the hostname for TLS and `Host`, cap response headers, and never
follow redirects or download bodies. A persisted cooldown lease rejects rapid
repeats before external access. Probe results do not mutate endpoint lifecycle
or collection settings.

## REPORTS Weekly Market Report Parser

The first source-specific parser operates only on manually preserved and
explicitly approved `reports_market_research` HTML artifacts:

1. `market_artifact_reviews` stores append-only approval, rejection, and
   needs-revision decisions. Each artifact keeps the latest status for efficient
   gating.
2. `market_parsing_runs` records parser key, version, status, counts, and
   structured format failures.
3. `market_observations` stores normalized long-form metrics with period, area,
   market stage, participant side, unit, settlement status, artifact evidence,
   and parser provenance.

Parser `reports_weekly_market_report:v1` extracts the Southern-region total and
five provincial rows for both day-ahead and real-time markets. Each stage
produces average traded energy and weighted average price, for 24 observations
per weekly report. The parser rejects incomplete reports rather than publishing
partial rows.

The source states that these values use a generation-side flash-report basis
and are not final settlement data. The parser preserves that distinction as
`participant_side=generation` and `settlement_status=preliminary_flash`.
Power-type metrics remain in the immutable artifact and emit an informational
quality issue until a later parser version normalizes them.

## Interval Forecasting Research Foundation

The first forecasting slice is isolated from Example Province recommendation
generation. It accepts manually prepared, complete 15-minute research curves
without fetching caller-supplied URLs. The BENCH benchmark adapter adds a
separate fixed-source path: it accepts only allowlisted official daily archive
filenames, preserves layered ZIP and CSV metadata with SHA-256, retains
source-native revision fields, and explicitly derives 15-minute averages from
three consecutive five-minute RRP values. The workstation handler stores each
official daily ZIP body once in MinIO, parses it once, and derives isolated
NSW1, QLD1, SA1, TAS1, and VIC1 research datasets.

1. `forecast_research_datasets` stores immutable source metadata, a
   canonicalized structured submission, SHA-256, explicit data mode, quality
   status, and fixed `research_only` usage scope.
2. `forecast_research_dataset_import_runs` records accepted, duplicate, and
   rejected submissions.
3. `forecast_research_price_points` publishes normalized points only when every
   trade date has exactly 96 unique 15-minute intervals.
4. `forecast_research_quality_issues` preserves semantic failures.
5. `forecast_research_model_runs` and `forecast_research_predictions` store
   auditable seasonal-naive and calendar-mean rolling backtests.

Every model run remains `candidate`, `research_only`, and `public_derived`.
Research results do not alter recommendations or confidence scores. See
[`interval_forecasting_research_foundation.md`](interval_forecasting_research_foundation.md)
and [`bench_dispatch_benchmark_adapter.md`](bench_dispatch_benchmark_adapter.md).

`GET /v1/forecasting/research/overview` and the React Forecast Research
dashboard are read-only observability over those same tables. Operators can
inspect dataset quality, BENCH five-region research coverage, import runs,
quality issues, candidate baseline metrics, and actual-vs-predicted curves.
The write actions in this view are intentionally narrow: a local CSV/JSON
manual import that calls `POST /v1/forecasting/research/datasets/manual`, and
the existing fixed baseline backtest for `seasonal_naive` or `calendar_mean`.
The import preview is browser-local, `source_url` is stored only as provenance
metadata, and neither action runs dynamic model code, schedules automatic
training, promotes a model, fetches source URLs, or feeds forecast research
into recommendation evidence.

## Local Workstation Orchestration

The personal research workstation runs pgvector PostgreSQL, MinIO, and a
self-hosted Prefect server with a local process worker. PostgreSQL stores
business audit records; Prefect stores supplementary flow state. Binary source
objects use a shared MinIO abstraction with SHA-256 deduplication and
PostgreSQL metadata.

Scheduled and manually queued work uses a fixed job registry. The API does not
accept arbitrary commands or URLs. The mainland workday helper applies normal
weekday behavior plus persisted official holiday overrides and future manual
exceptions.

Registered source collection is implemented as a project-native guardrail
adapter, not as a general crawler runtime. The generic static HTTP adapter
accepts only reviewed `market_source_endpoints` rows, uses ordinary HTTPS with
default TLS validation, checks robots.txt, rejects redirects and unsupported
media, preserves textual raw artifacts with SHA-256 in the existing market
ingestion audit tables, and never accepts caller-supplied URLs, stealth
settings, proxies, cookies, login, or captcha automation.

`workers.consume` claims PostgreSQL records with leases and
`FOR UPDATE SKIP LOCKED`, then executes only registered local handlers. Workflow
states are `queued`, `running`, `succeeded`, `skipped`, `retry_wait`, and
`failed`. Adapter-level bounded retries remain in place; the workflow layer
delays and retries transient network or storage failures at most once.
Prefect planned start times provide schedule-slot idempotency. Consumers renew
active leases and rotate an internal token during recovery so stale workers
cannot overwrite the current owner. A second expired lease ends in
`workflow_lease_exhausted`.

The one-shot Compose `migrate` service checks Alembic markers against expected
tables and columns before upgrading. Inconsistent historical volumes are
reported for manual backup and repair without automatic reset or deletion.

`GET /v1/operations/overview` provides the operator observability view for the
React cockpit. It aggregates only existing database state: workflow counts,
recent failed or retry-wait runs, stale-lease risk, weather and brief
freshness, isolated BENCH `research_only` benchmark freshness, local policy
library counts, registered-source counts, and previously recorded endpoint
health checks. The endpoint does not perform live network probes, fetch
arbitrary URLs, instantiate collection adapters, mutate source lifecycle
state, or feed BENCH data into Example Province recommendation evidence.

`GET /v1/operations/action-center` derives a read-only operator todo list from
the same stored state plus brief review, recommendation review, and decision
feedback records. Todo items may reference fixed registered job keys for manual
reruns, but the endpoint does not accept URLs, commands, dynamic handler names,
or trading instructions. It does not call external models, mutate review
states, or execute trades. For operator convenience, review-related todos can
include local navigation targets to existing brief or recommendation detail
views; those links are not execution commands and do not create new evidence.
Action Center can also surface local review todos for weather feature
snapshots, preserved market artifacts, and policy documents. These todos expose
only fixed review target types, allowed review statuses, and a default note for
the cockpit quick-review UI. Submitting a quick review calls the corresponding
local review API; it does not run collection, call a model, authorize external
processing, modify recommendation evidence, or represent a trading action.

`GET /v1/operations/review-package` is the operator-facing export snapshot for
the same local state. It includes the operations overview, Action Center,
system readiness, recent workflow runs, fixed job keys, and safety flags such
as `no_auto_trading=true`, `manual_job_keys_only=true`,
`network_probe_performed=false`, and `fetch_performed=false`. The React cockpit
downloads the JSON in the browser; no server-side artifact is written and no
task, probe, review, model call, or recommendation update is triggered.

## Policy Knowledge Base

The local policy knowledge base separates documents, immutable versions,
chunks, and per-document external-processing authorizations. MinIO preserves
raw files while PostgreSQL stores provenance, SHA-256 hashes, parsed text,
pgvector embeddings, and authorization audits.

Documents retain an explicit trust layer: official policy, official market
notice, public research, or user upload. User uploads default to local-only
processing. A separate local BGE service keeps model weights outside the API
process. Registered source candidates remain disabled until fixed public
entrypoints pass adapter review.

Preserved market artifacts can enter the knowledge base only through
`POST /v1/policy/documents/from-market-artifact/{artifact_id}`. The bridge
loads an existing `market_raw_artifacts` row, verifies that its registered
source and endpoint still exist, preserves source URL, source id, endpoint id,
capture time, media type, and SHA-256 metadata, and reuses an existing
knowledge document only for the same artifact/source identity plus content
hash. Raw objects still deduplicate by SHA-256 and append artifact provenance
metadata when the same bytes arrive through another reviewed source path. It
does not accept URL parameters or perform a fetch. BENCH and `research_only`
artifacts are rejected so research benchmarks remain isolated from Example Province
policy knowledge and recommendation evidence.

`GET /v1/policy/corpus/overview` and `GET /v1/policy/documents/{document_id}`
are read-only corpus observability endpoints. They derive document counts,
layer summaries, chunk and embedding coverage, latest version hashes, raw
object references, and artifact provenance from existing PostgreSQL rows. They
do not expose raw file downloads, run live probes, fetch webpages, mutate
source lifecycle state, or feed BENCH benchmarks into Example Province recommendation
evidence.

`GET /v1/policy/documents/{document_id}/review-package` is the operator-facing
review aggregate for one policy document. It combines existing document
metadata, version and raw-object summaries, chunk coverage, bounded chunk
excerpts, review history, and safety flags into a JSON package that the
Operations Action Center can display and download locally in the browser. The
endpoint does not include the full raw payload, write a server artifact, fetch
sources, call external models, authorize external processing, or change
recommendation evidence.

Policy document reviews are stored in the append-only
`knowledge_document_reviews` table through `POST
/v1/policy/documents/{document_id}/reviews`. The review updates only the
document's current human review status and leaves external-processing
authorization unchanged, so approving a document for local corpus use cannot
implicitly send its text to an external model.

## Intelligence Briefs And Q&A

The brief API first assembles deterministic facts from local audit tables. An
optional DeepSeek adapter may explain those facts with strict JSON output,
timeout, and bounded retry. Invalid or unavailable model output falls back to
a deterministic review draft.

`GET /v1/intelligence/policy-watch` is a read-only local knowledge-base
aggregate. It runs fixed retrieval queries over existing chunks, prefers
`official_policy` and `official_market_notice`, labels `public_research` as
supplemental, and excludes BENCH or `research_only` material. Daily brief
generation stores the same observations in `deterministic_facts.policy_watch`,
brief citations, and deterministic fallback narrative. Unauthorized chunks can
appear as local titles, sources, and short excerpts for operator review, but
their body text is not included in external model prompts. The endpoint does
not probe the network, fetch webpages, accept URLs, mutate source state, or
change recommendation evidence.

Brief history and detail endpoints expose generated brief snapshots and the
append-only `intelligence_brief_reviews` audit trail. Operators can mark a
brief approved or needs-revision; that updates the brief's latest
`human_review_status` and preserves the review note. This review loop is local
state only: it does not run collectors, send extra evidence to external
models, alter recommendations, or perform trading actions.

Local policy search combines BGE embeddings, lexical matching, and BGE
reranking. Search remains local. Q&A applies a document authorization filter
before any external model prompt is constructed, stores cited chunk ids, and
never persists model reasoning chains. Every brief and Q&A response requires
human review; no result triggers trading execution.
