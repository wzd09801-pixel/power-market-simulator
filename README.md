# Power Market Simulator

> 通用电力市场与水电研究演示框架。所有业务主体、市场地址及水电场景均为虚构示例。
> 市场连接器为协议演示，不能直接获取真实市场数据。详见 [发布范围](docs/publication_scope.md)。

示例甲省电力市场情报与水电交易建议 MVP。第一阶段交付一个 Docker 起步的纵向闭环：
FastAPI 后端、React 智能工作台、PostgreSQL、Alembic 迁移、示例水电站 A场景模拟与建议卡片。

## Safety Boundary

This project is a human-in-the-loop decision support system. It does not submit
trades, automate trading-platform login, or claim simulated company data is real
operational data.

## Local Setup

Install development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run tests and checks:

```powershell
pytest
ruff check .
mypy .
```

Runtime dependencies are mirrored in `requirements-runtime.txt` so Docker can
cache dependency installation independently from source changes. Keep that file
in sync when changing `[project].dependencies` in `pyproject.toml`.

Run the API locally:

```powershell
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Run the React cockpit locally:

```powershell
Set-Location webapp
npm install
npm run dev
```

Run cockpit checks:

```powershell
Set-Location webapp
npm run lint
npm test
npm run build
npm run test:e2e:research
npm run test:e2e:compose
```

`npm run test:e2e:research` is the host-only targeted RC check for the
Research workspace. It uses Playwright route mocks to verify source status,
BENCH research isolation, candidate backtest controls, and the browser-local
forecast review package download without requiring a live backend.

The Compose smoke script uses the isolated `eee-smoke` project name and
dedicated host ports. It stops the services after Playwright completes and
deliberately keeps its PostgreSQL and MinIO volumes for inspection. It never
deletes or resets historical volumes.

## Docker

Copy the environment template first:

```powershell
Copy-Item .env.example .env
```

Start services:

```powershell
docker compose up --build
```

The one-shot `migrate` service performs a read-only schema consistency check
before running Alembic. If a historical volume is stamped with an incompatible
schema, startup stops with a backup and manual-repair message. It never resets
or deletes an existing volume.

Expected service URLs:

- API: <http://localhost:8000/healthz>
- API docs: <http://localhost:8000/docs>
- React intelligence cockpit: <http://localhost:3000>
- MinIO console: <http://localhost:9001>
- Prefect UI: <http://localhost:4200>

## Workstation Orchestration

Scheduled collection is disabled by default in this snapshot (Compose `schedules` profile).
Example market endpoints cannot fetch real data.

The local workstation runtime uses pgvector PostgreSQL, MinIO, and a
self-hosted Prefect server with a process worker and a static schedule runner.
PostgreSQL remains the business audit source of truth; Prefect state is
supplementary orchestration metadata.

Raw binary objects are stored in MinIO with SHA-256 deduplication. The API
preserves object metadata in PostgreSQL. Scheduled collectors and manual job
requests use fixed registered job keys:

- `weather_refresh`: `07:00` and `16:00` Asia/Shanghai
- `policy_research_refresh`: every six hours
- `bench_dispatch_research`: `09:30` Asia/Shanghai, always `research_only`
- `daily_intelligence_brief`: workdays at `08:30` Asia/Shanghai

Operation endpoints:

- `GET /v1/operations/jobs`
- `GET /v1/operations/action-center`
- `GET /v1/operations/overview`
- `GET /v1/operations/review-package`
- `GET /v1/operations/runs`
- `GET /v1/operations/runs/{workflow_run_id}`
- `POST /v1/operations/jobs/{job_key}/run`

The manual endpoint queues only known jobs. It never accepts a caller-supplied
URL or command.

## v0.1 RC Readiness

The release-candidate operator loop adds a local demo seed and readiness check
for end-to-end verification:

- `GET /v1/system/readiness` is a read-only aggregate over existing tables,
  Action Center state, demo fixture presence, recommendation boundaries, and
  forecast research coverage.
- `demo_research_workspace_seed` is a fixed manual job that writes only local,
  deterministic demo fixtures. It does not fetch URLs, call external models,
  train models automatically, promote models, mutate recommendation confidence,
  or execute trades.
- Seeded company-side values are labeled `scenario_simulated` or
  `user_uploaded`; seeded forecast research stays `research_only`; the demo
  recommendation keeps `no_auto_trading=true`.

Use it after migrations when a fresh local environment needs a complete
demonstration path:

```powershell
curl http://localhost:8000/v1/system/readiness
curl -X POST http://localhost:8000/v1/operations/jobs/demo_research_workspace_seed/run
```

The worker executes the queued seed job and records the run in
`workflow_runs`. Existing PostgreSQL and MinIO volumes are not deleted,
rebuilt, or reset.

For no-data trial readiness, use
[`docs/no_data_trial_framework.md`](docs/no_data_trial_framework.md) and the
versioned examples in
[`docs/import_contracts/`](docs/import_contracts/). They define the first-day
upload/import contracts for policy documents, manual market artifacts,
Open-Meteo reference weather, forecast research curves, hydro scenario
previews, and recommendation drafts without adding new collectors or trading
capabilities.

Registered source collection is fixed-entrypoint only. The generic
`registered_static_http:v1` adapter may fetch only a reviewed registry endpoint
whose canonical URL, HTTPS host, adapter key, lifecycle status, and
`collection_enabled=true` flag are already stored in PostgreSQL. It checks
robots.txt, rejects redirects and unsupported media, preserves textual raw
artifacts with SHA-256, and never uses stealth, proxy rotation, login,
captcha, cookie replay, or caller-supplied URLs.

`GET /v1/operations/overview` is a read-only operator dashboard aggregate. It
summarizes workflow counts, recent incidents, stale-lease risk, data freshness,
registered source health records, and fixed manual action buttons. It does not
run endpoint probes, fetch webpages, accept arbitrary URLs, or change the
recommendation pipeline.

`GET /v1/operations/action-center` is a read-only todo aggregate for local
operators. It summarizes failed or retry-wait workflows, brief and
recommendation review needs, decision feedback still pending observation, and
freshness warnings. It only references fixed job keys for manual reruns and
does not run probes, call external models, mutate recommendations, or execute
trades. Items may also expose local navigation targets for existing brief or
recommendation detail pages; opening those targets is UI navigation only and
does not create new data or change review state. The same view can surface
local review todos for weather feature snapshots, preserved market artifacts,
and policy documents. Those quick actions call fixed local review APIs only;
they do not fetch sources, invoke models, authorize external processing, alter
recommendation evidence, or represent a trading instruction.

`GET /v1/operations/review-package` combines the operations overview, Action
Center, RC readiness, recent workflow runs, fixed job keys, and explicit safety
flags into one local operator review snapshot. The React Operations workspace
can download this snapshot as browser-generated JSON. The endpoint is read-only:
it does not queue jobs, run network probes, fetch webpages, approve reviews,
call external models, or alter recommendation evidence.

`workers.scheduled` registers the fixed cron schedules with Prefect and writes
auditable queued workflow records. `workers.consume` leases queued jobs from
PostgreSQL, executes only fixed registered handlers, and retries transient
infrastructure failures at most once. The daily brief runner checks the
persisted mainland workday calendar, including official adjusted-workday
overrides. Source-specific handlers remain isolated from the schedule registry
and enforce their own approved-entrypoint rules.

Scheduled records use the Prefect planned start time as an idempotency key, so
repeated delivery for the same job slot returns the existing audit record.
Workers renew leases while fixed handlers run. A lease can be recovered once;
a second expiry ends the workflow as `workflow_lease_exhausted`.

The enabled Open-Meteo schedule uses `demo_hydro_a_reference` at `30.0,
110.0` as an `unverified_analysis_input`. It is a public reference-point input,
not a verified station sensor or internal operational coordinate.

## Policy Knowledge Foundation

The personal research knowledge base preserves uploaded PDF, DOCX, HTML, TXT,
and Markdown documents in MinIO before parsing them into reviewable chunks.
Each raw body is deduplicated with SHA-256. Documents are labeled as one of:

- `official_policy`
- `official_market_notice`
- `public_research`
- `user_uploaded`

Uploaded documents default to local-only processing. External model processing
requires an explicit per-document operator authorization, and each change is
audited. Registered research-source candidates remain disabled until their
fixed public entrypoints are reviewed; the system does not crawl arbitrary
URLs or bypass TLS and anti-automation failures.

Policy knowledge endpoints:

- `POST /v1/policy/documents/upload`
- `POST /v1/policy/documents/from-market-artifact/{artifact_id}`
- `GET /v1/policy/corpus/overview`
- `GET /v1/policy/documents`
- `GET /v1/policy/documents/{document_id}`
- `GET /v1/policy/documents/{document_id}/review-package`
- `GET /v1/policy/documents/{document_id}/chunks`
- `POST /v1/policy/documents/{document_id}/reviews`
- `POST /v1/policy/documents/{document_id}/external-processing-authorization`

The market-artifact bridge imports only existing `market_raw_artifacts` by
artifact id. It preserves the registered source id, endpoint id, source URL,
capture time, media type, and SHA-256 metadata. It returns an existing
knowledge document only when the same artifact/source identity and content hash
have already been imported; raw objects still deduplicate by SHA-256 so the
same bytes are stored once. The bridge never accepts a URL or triggers a new
fetch. BENCH and `research_only` artifacts are rejected so research benchmarks
cannot become Example Province policy evidence.

`GET /v1/policy/corpus/overview` and `GET /v1/policy/documents/{document_id}`
are read-only corpus inspection endpoints. They aggregate existing local
documents, chunks, embedding coverage, raw-object metadata, and artifact
provenance. They do not download raw files, run network probes, fetch webpages,
or change recommendation evidence.

`GET /v1/policy/documents/{document_id}/review-package` returns a local,
read-only operator review package for one policy knowledge document. It
combines document provenance, version and raw-object summaries, chunk coverage,
bounded chunk excerpts, review history, and safety flags. It does not include
the full raw payload, write a server artifact, authorize external processing,
call external models, fetch sources, or enter the recommendation evidence
chain. The Operations Action Center can display this package and download the
JSON in the browser only.

Policy document review is append-only. `POST
/v1/policy/documents/{document_id}/reviews` records an operator note and one
of `approved`, `rejected`, or `needs_revision`, then updates only the
document's current human review status. It does not change the external
processing authorization; that remains a separate explicit operator action.

The default local embedding service uses `BAAI/bge-m3`. It runs separately from
the API so model weights do not increase API process memory usage.

## Intelligent Brief And Cited Q&A

The intelligence API keeps deterministic local facts separate from optional
DeepSeek explanations. Brief generation remains available when DeepSeek is
not configured or returns invalid JSON: the API falls back to a deterministic
review draft.

`GET /v1/intelligence/policy-watch` builds a local-only policy watch from the
existing knowledge base. It uses fixed retrieval queries, returns cited
official policy, official market notice, and supplemental public-research
items, and records how many chunks were excluded from external model prompts
because they lack explicit authorization. The endpoint does not run network
probes, fetch webpages, accept URLs, or alter recommendation evidence. Daily
brief generation embeds the same policy watch into deterministic facts,
citations, and fallback narrative; only explicitly authorized chunk bodies may
enter a DeepSeek prompt.

Brief review is an operator audit loop. `GET /v1/intelligence/briefs` lists
recent generated briefs, `GET /v1/intelligence/briefs/{brief_id}` returns the
full local evidence snapshot and review history, and
`POST /v1/intelligence/briefs/{brief_id}/reviews` appends an approval or
needs-revision note. Reviewing a brief does not run collection, send additional
content to external models, change recommendations, or trigger trading.

Q&A uses local BGE embeddings, lexical matching, and BGE reranking. Local
search may show restricted documents to the operator, but external DeepSeek
requests include only chunks whose document has an explicit
`external_processing_allowed=true` authorization. Reasoning chains are never
persisted.

Intelligence endpoints:

- `POST /v1/intelligence/search`
- `GET /v1/intelligence/policy-watch`
- `POST /v1/intelligence/questions`
- `GET /v1/intelligence/briefs`
- `POST /v1/intelligence/briefs/generate`
- `GET /v1/intelligence/briefs/latest`
- `GET /v1/intelligence/briefs/{brief_id}`
- `POST /v1/intelligence/briefs/{brief_id}/reviews`

DeepSeek defaults to `deepseek-v4-flash` for normal explanation and
`deepseek-v4-pro` only for operator-requested deep analysis. Both model ids are
environment settings so vendor lifecycle changes do not require code edits.

## React Intelligence Cockpit

The primary target UI is the Vite, React, TypeScript, Ant Design, and ECharts
cockpit at <http://localhost:3000>. It provides:

- a daily changes-and-risk brief dashboard
- a running-status dashboard for workflow, freshness, source-health, and fixed
  manual job actions
- layered policy documents with audited external-processing toggles
- cited simple and deep evidence Q&A
- an isolated BENCH research benchmark chart
- a separate human-reviewed scenario recommendation and audit area
- a hydro constraint preview panel with 96-point price-signal paste, constraint
  explanations, and recent-run comparison

The React cockpit is the default workstation interface. The previous
Streamlit prototype source remains in the repository as migration history but
is no longer part of the default runtime or Python dependency set.

## First MVP Endpoints

- `GET /healthz`
- `GET /v1/system/status`
- `GET /v1/scenarios/demo_hydro/default`
- `POST /v1/scenarios/demo_hydro/optimization-runs`
- `POST /v1/recommendations/run`

Example recommendation request:

```json
{
  "trade_date": "2026-06-01",
  "weather_feature_snapshot_id": "optional_explicitly_approved_snapshot_id"
}
```

The response is scenario-based and must include `scenario_simulated`,
structured `evidence`, `human_check_required: true`, and
`no_auto_trading: true`.

Hydro constraint preview endpoints:

- `POST /v1/scenarios/demo_hydro/optimization-runs`
- `GET /v1/scenarios/demo_hydro/optimization-runs/recent?limit=5`
- `GET /v1/scenarios/demo_hydro/optimization-runs/{optimization_run_id}`

The hydro preview is a local research and audit record for Demo Hydro A
scenario constraints. It stores `hydro_optimization_runs` with
`scenario_simulated`, `human_review_required=true`, and
`no_auto_trading=true`. It may use a 96-point price signal to rank intervals,
or run a constraint-only preview when price data is missing. It does not create
a recommendation run, change recommendation confidence, call an external solver,
submit trades, or log in to a trading platform. See
[`docs/hydro_optimization_preview.md`](docs/hydro_optimization_preview.md).
Operator-supplied price curves are recorded as `user_uploaded` preview
evidence only; they are not treated as verified Example Province spot-market data.

Each generated recommendation is persisted as an immutable draft with an input
snapshot reference and a `pending_review` status. Human review is recorded
separately so the full review history remains auditable.

Additional recommendation endpoints:

- `GET /v1/recommendations/recent?limit=20`
- `GET /v1/recommendations/feedback/overview?limit=10`
- `GET /v1/recommendations/{recommendation_id}`
- `GET /v1/recommendations/{recommendation_id}/audit`
- `GET /v1/recommendations/{recommendation_id}/evidence-export`
- `GET /v1/recommendations/{recommendation_id}/decisions`
- `POST /v1/recommendations/{recommendation_id}/decisions`
- `POST /v1/recommendations/decisions/{decision_id}/feedback`
- `POST /v1/recommendations/{recommendation_id}/reviews`

The recommendation audit endpoint is a read-only derived check over the stored
draft, strategy JSON, structured evidence, missing-data warnings, and review
status. It verifies evidence completeness, `scenario_simulated` labeling,
`human_check_required`, `no_auto_trading`, approved-weather linkage, and
isolation from BENCH, `research_only`, and policy-watch evidence. It does not
run collectors, call external models, alter confidence, approve a draft, or
trigger trading.

`GET /v1/recommendations/{recommendation_id}/evidence-export` returns the same
operator review package as read-only JSON: recommendation metadata, input
snapshot reference, safety flags, audit status, warnings, checks, recommended
actions, and structured evidence. Exporting this package does not write an
audit event, change review status, collect new data, call external models, or
trigger trading.

Recommendation decision feedback is a local human journal. Operators can record
whether a reviewed draft was adopted, partially adopted, rejected, or deferred,
then append subjective follow-up observations. The saved audit snapshot shows
what was known at decision time. Critical audits cannot be marked adopted or
partially adopted. These records are not market orders, do not log in to trading
platforms, do not collect new data, and do not change recommendation generation.

`GET /v1/recommendations/feedback/overview` is a read-only local aggregation of
those decision and feedback rows. It reports decision/outcome counts, pending
observations, critical-audit not-adopted notes, `audit_status_counts`,
`review_status_counts`, and recommended operator follow-up. Those status counts
show local pending-review and warning or critical audit pressure only. The
overview does not collect data, call external models, alter recommendation
confidence or review status, or represent real trading performance.

Open-Meteo data-foundation endpoints:

- `POST /v1/weather/open-meteo/forecast`
- `GET /v1/weather/records?location_id=demo_hydro_a_reference&variable=precipitation`
- `GET /v1/weather/quality/issues?location_id=demo_hydro_a_reference`
- `GET /v1/weather/features/latest?location_id=demo_hydro_a_reference`
- `GET /v1/weather/features/{feature_snapshot_id}/review-package`
- `POST /v1/weather/features/{feature_snapshot_id}/reviews`

The weather ingestion endpoint is manually triggered in this stage. Callers
must provide an explicit public reference-point location; it must not be
described as a verified station sensor or internal operational data source.

Example weather ingestion request:

```json
{
  "location_id": "demo_hydro_a_reference",
  "location_name": "Demo Hydro A public reference point",
  "latitude": 30.0,
  "longitude": 110.0,
  "timezone": "Asia/Shanghai",
  "forecast_days": 3,
  "hourly_variables": ["temperature_2m", "precipitation", "rain"]
}
```

The coordinates above are an API-shape example only. Select and document a
public reference point before using it for analysis.

Each successful ingestion preserves observed hourly values, records derived
quality issues, and creates a reviewable hydro-weather feature snapshot.
Incomplete or suspect inputs do not produce partial aggregates. This stage
does not automatically change recommendation generation.

Weather feature snapshots start as `pending_review`. An operator may explicitly
approve a snapshot only when its derived features are complete and its quality
status is `valid`. Recommendation generation may optionally link an approved
snapshot whose forecast window starts on the requested trade date. The linked
weather context is persisted as evidence and input snapshot data; it does not
silently change strategy actions or confidence scores.

`GET /v1/weather/features/{feature_snapshot_id}/review-package` is a read-only
operator snapshot for one weather feature row. It returns feature provenance,
quality issue counts and displayed issues, prior human reviews, approval
blockers, and explicit safety flags. The Operations Action Center can download
the package as browser-generated JSON; the endpoint does not call Open-Meteo,
write report artifacts, approve the snapshot, or change recommendation inputs.

Example review request:

```json
{
  "review_status": "needs_revision",
  "note": "Please add verified weather inputs before the next review."
}
```

## Public Market Artifact Foundation

The public-market landing zone preserves reviewable official artifacts before
adding source-specific parsers or price forecasting. It keeps source identity,
endpoint access policy, immutable content, ingestion outcomes, and quality
findings separate. It does not claim that an anonymous Example Province 96-point
spot-price curve is currently available.

Market artifact endpoints:

- `GET /v1/market/sources`
- `GET /v1/market/endpoints`
- `POST /v1/market/artifacts/manual`
- `GET /v1/market/artifacts?source_id=example_province_power_trading_portal`
- `GET /v1/market/artifacts/{artifact_id}/review-package`
- `GET /v1/market/ingestion/runs`
- `GET /v1/market/quality/issues?endpoint_id=reports_market_research`
- `POST /v1/market/endpoints/{endpoint_id}/health-checks`
- `GET /v1/market/health/checks?endpoint_id=reports_market_research_https_candidate`

The manual preservation endpoint accepts textual public artifacts only. It
validates the registered endpoint and host, stores submitted content with a
SHA-256 hash, deduplicates unchanged content within a source, and emits
reviewable quality findings. It never fetches a caller-supplied URL.

Registered HTTP-only sources may be manually preserved for review, but each
artifact receives an `insecure_transport_source` warning. Automated collection
remains disabled until trusted anonymous HTTPS access and field semantics are
verified. Binary archival and MinIO storage remain later-stage work.

`GET /v1/market/artifacts/{artifact_id}/review-package` is a read-only
operator snapshot for one preserved artifact. It returns source and endpoint
metadata, artifact hash and storage metadata without the full inline body,
quality issue counts and displayed issues, review history, parser run history,
and explicit no-trading/no-probe/no-fetch/no-parse flags. The Operations Action
Center can download it as browser-generated JSON. The endpoint does not parse
the artifact, run endpoint health checks, fetch source URLs, write a report
artifact, approve reviews, or change recommendation evidence.

Market endpoint health checks are also manually triggered. They operate only
on registered canonical URLs and perform bounded DNS, TCP, TLS, and HTTP
`HEAD` probes. They reject credentials, custom ports, unregistered hosts, and
non-public resolved addresses before making a connection. DNS resolution has
a hard timeout, the actual connected IP is audited, and an endpoint-level
cooldown rejects rapid repeats before external access. Redirects are recorded
but never followed, response bodies are not downloaded, and probe results do
not automatically enable manual submission, collection, or endpoint lifecycle
changes.

Example manual preservation request:

```json
{
  "endpoint_id": "example_province_portal_home",
  "source_url": "https://portal.market.example.invalid/portal/disclosures/example",
  "title": "Public artifact example",
  "media_type": "text/html",
  "inline_text": "<html><body>public artifact content</body></html>",
  "published_at": "2026-05-30T08:00:00+08:00"
}
```

## REPORTS Weekly Market Report Parser

Reviewed Example Regional Exchange weekly HTML reports can be normalized
into auditable regional and provincial observations. The parser is manually
triggered and does not crawl the HTTP-only source:

- `POST /v1/market/artifacts/{artifact_id}/reviews`
- `POST /v1/market/artifacts/{artifact_id}/parse/reports-weekly-report`
- `GET /v1/market/parsing/runs?artifact_id={artifact_id}`
- `GET /v1/market/observations?area_code=GD&market_stage=real_time`

Parser `reports_weekly_market_report:v1` stores weekly generation-side
day-ahead and real-time average traded energy and weighted average prices for
the Southern region and five provinces. Each observation retains its raw
artifact and parser-version reference. The source labels these values as flash
reports rather than final settlement data.

The raw power-type section remains preserved but is not normalized in parser
v1. Weekly aggregate observations are reviewable public context only: they are
not 96-point curves, forecast training targets, or recommendation inputs.

## Anonymous Market Field Verification

The current anonymous official-entry research checkpoint is documented in
[`docs/anonymous_market_field_verification.md`](docs/anonymous_market_field_verification.md).
The adapter-design gate remains `blocked`: no registered official endpoint has
yet demonstrated a trusted anonymous HTTPS contract with verified Example Province
day-ahead or real-time field semantics and a confirmed 96-point curve.

## Interval Forecasting Research Foundation

The research forecasting API accepts manually prepared complete 15-minute
curves and stores them with `usage_scope=research_only`. It does not fetch a
caller-supplied URL, infer Example Province prices, or modify recommendation actions
or confidence scores.

Research forecasting endpoints:

- `POST /v1/forecasting/research/datasets/manual`
- `POST /v1/forecasting/research/benchmarks/bench-dispatch/archive`
- `GET /v1/forecasting/research/overview`
- `GET /v1/forecasting/research/datasets`
- `GET /v1/forecasting/research/import-runs`
- `GET /v1/forecasting/research/datasets/{dataset_id}/points`
- `GET /v1/forecasting/research/datasets/{dataset_id}/review-package`
- `GET /v1/forecasting/research/quality/issues`
- `POST /v1/forecasting/research/datasets/{dataset_id}/backtests`
- `GET /v1/forecasting/research/model-runs`
- `GET /v1/forecasting/research/model-runs/{model_run_id}/predictions`

The first backtests are `seasonal_naive` and `calendar_mean`. Every successful
run is registered as a `candidate`, remains `research_only`, and preserves
interval-level predictions and evaluation metrics for audit. See
[`docs/interval_forecasting_research_foundation.md`](docs/interval_forecasting_research_foundation.md).

The React research workspace includes a Forecast Research dashboard over these
local tables. It shows dataset quality, import runs, quality issues, BENCH
research coverage, candidate model metrics, and actual-vs-predicted curves
after an operator selects a model run or manually triggers a fixed baseline
backtest. The dashboard does not fetch source URLs, schedule training, promote
models, alter recommendation confidence, or execute trades.

For each selected research dataset, the same dashboard loads a read-only review
package that combines provenance metadata, recent import runs, quality issue
counts, displayed issue details, candidate model runs, and explicit isolation
flags. Operators can download that package as a browser-generated JSON file; no
server-side report artifact is written, no external network request is made, and
the package is not recommendation evidence.

The same workspace includes a local Forecast Data Import card. It parses CSV or
JSON files in the browser, previews point counts, date coverage, duplicate or
incomplete intervals, timezone-offset errors, invalid prices, and sample rows,
then submits the confirmed payload to the existing manual dataset endpoint.
`source_url` remains provenance metadata only; the import card never fetches
that URL, accepts no arbitrary crawler input, and always submits
`usage_scope=research_only`.

The BENCH Dispatch benchmark endpoint accepts only fixed official daily archive
filenames such as `PUBLIC_DISPATCHIS_20260531.zip` and an BENCH NEM region id.
It preserves layered ZIP and CSV hashes, retains source-native revision fields,
and derives each 15-minute point from three consecutive five-minute regional
`RRP` values. BENCH benchmarks remain `public_derived`, `research_only`, and
separate from Example Province recommendation generation. See
[`docs/bench_dispatch_benchmark_adapter.md`](docs/bench_dispatch_benchmark_adapter.md).

The scheduled BENCH job uses the local `D-2` filename, stores the official daily
ZIP body once in MinIO by SHA-256, parses it once, and imports separate NSW1,
QLD1, SA1, TAS1, and VIC1 research datasets.
