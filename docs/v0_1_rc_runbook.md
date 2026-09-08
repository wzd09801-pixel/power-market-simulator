# v0.1 Research Workstation RC Runbook

This runbook describes the local release-candidate demonstration path for the
personal research workstation. It is not a production deployment guide and it
does not add collection, model, or trading capabilities.

## Safety Boundary

- No live trading submission.
- No trading-platform login automation.
- No arbitrary URL fetching.
- No external model call from the demo seed.
- No automatic model training schedule or promotion.
- No BENCH, `research_only`, or policy-watch evidence in recommendation drafts.
- No deletion, rebuild, or automatic repair of existing PostgreSQL or MinIO
  volumes.

## Start Locally

Run migrations and services through Compose:

```powershell
docker compose up --build
```

For a smoke run that uses isolated ports and keeps volumes for inspection:

```powershell
.\scripts\run_compose_smoke.ps1
```

For the default host-only no-data workstation gate:

```powershell
.\scripts\validate_no_data_workstation.ps1
```

This runs the backend/RAG/forecast trial suite and the cockpit workspace
smoke. It does not start Docker, write PostgreSQL or MinIO, read credentials,
contact external networks, call a real external model, schedule training,
promote models, or execute trades.

For the static framework readiness gate that should run before replacing
examples with user files:

```powershell
.\scripts\validate_framework_readiness.ps1
```

This gate reads local docs, schemas, import contracts, and safety-boundary
markers only. It checks import contracts, forecast dataset manifests, RAG
document readiness, market/weather review readiness, training and backtest
prerequisites, and recommendation safety boundaries without starting services,
writing persistent stores, calling external models, promoting models, or
executing trades.

For the local first-data-day package dry-run:

```powershell
.\scripts\scaffold_first_data_day_package.ps1 --output-dir <local-first-data-day-folder> --json
.\scripts\validate_first_data_day_package.ps1 --package-dir <local-first-data-day-folder> --json
```

Use `docs/first_data_day_operator_manual.md` as the detailed operator SOP for
filling the package, reading dry-run failures, and handing files to manual
import or RAG review APIs.

The scaffold command creates only local package metadata and empty directories.
An empty or newly scaffolded directory is a controlled validation failure with
`status=missing_required_inputs`. It keeps RAG answering, forecast training,
backtests, external model calls, production promotion, and automatic trading
disabled while listing workflow readiness plus the files and metadata the
operator must provide next.

For only the backend/RAG/forecast suite:

```powershell
.\scripts\validate_no_data_trial_suite.ps1
```

This chains the import contract validator, RAG local trial, and
forecast/training trial.

For the combined zero-data closure gate:

```powershell
.\scripts\validate_zero_data_framework_closure.ps1
```

This checks contract/template coverage, temporary scaffold plus dry-run
behavior, and existing empty-state safety tests without Docker, external
network, database writes, model calls, model promotion, or recommendation
execution changes.

For the host-only cockpit smoke across Operations, Research, and
Recommendation:

```powershell
Set-Location webapp
npm run test:e2e:no-data-workspaces
```

This runs targeted Playwright tests with mocked API responses. It verifies the
main workspace navigation, review-package controls, source status, and
simulated recommendation safety text without a live backend, Docker, external
collection, external model calls, scheduled training, model promotion, or
trading execution.

For the Docker no-data validation path, run:

```powershell
.\scripts\run_no_data_trial_validation.ps1
```

This starts an isolated Compose project with dynamic ports, checks empty
readiness, queues `demo_research_workspace_seed`, waits for the local operation
worker to complete it, and verifies readiness plus the operations review
package safety flags. It stops containers at the end and keeps its PostgreSQL
and MinIO volumes for inspection.

Before replacing the no-data examples with user-provided files, validate the
current import contracts:

```powershell
.\scripts\validate_framework_readiness.ps1
.\scripts\validate_first_data_day_package.ps1 --manifest docs\import_contracts\first_data_day_package.example.json --json
.\scripts\validate_import_contracts.ps1
```

These commands are host-only and read-only. The framework gate checks the
future dry-run path across docs, schemas, templates, and safety markers. The
first-data-day command checks the bundled package manifest template. The
contract validator checks JSON examples against the current request schemas,
checks the 96-point forecast CSV fixture, and confirms the local-only MVP
safety wording.

For a host-only RAG trial that exercises local upload, chunking, review
packages, cited search, Q&A authorization boundaries, and document review:

```powershell
.\scripts\validate_rag_trial.ps1
```

This smoke uses in-memory SQLite, `MemoryBlobStore`, deterministic test
embeddings, and a fake local model client. It does not start Docker, write
PostgreSQL or MinIO, read credentials, contact external networks, or call a
real external model.

For a host-only forecast/training preflight that exercises manual research
curve import, invalid curve quality diagnostics, baseline backtests, candidate
model runs, predictions, review packages, and recommendation isolation:

```powershell
.\scripts\validate_forecast_training_trial.ps1
```

This smoke uses in-memory SQLite and existing forecasting research endpoints.
It does not start Docker, write PostgreSQL, fetch source URLs, schedule
training, promote models, or execute trades.

If Docker Hub or local Docker is unavailable, run the API and cockpit directly:

```powershell
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
Set-Location webapp
npm run dev
```

## Readiness Check

Open the cockpit Operations page and inspect **RC Checklist**, or call:

```powershell
curl http://localhost:8000/v1/system/readiness
```

Expected behavior on an empty database:

- The endpoint returns `warning`, not an exception.
- Missing demo objects are listed.
- Recommendation isolation remains `healthy`.
- The response keeps `no_auto_trading=true`.

Critical status should be reserved for hard safety failures such as
recommendation evidence containing BENCH, `research_only`, or policy-watch
markers.

## UTF-8 Copy Check

The React cockpit and this runbook are UTF-8. The expected visible Chinese
copy includes `?????????`, `????`, `?????`, and
`??????`.

If Chinese copy appears unreadable in a browser or terminal, verify that the
static server response declares UTF-8 and that the viewer is using UTF-8. The
Docker cockpit Nginx config sets UTF-8 for the static HTML, CSS, JavaScript,
JSON, and text assets.

## Seed Local Demo Data

Queue the fixed local seed job:

```powershell
curl -X POST http://localhost:8000/v1/operations/jobs/demo_research_workspace_seed/run
```

The operation worker executes the job. The seed writes deterministic local
fixtures with fixed identifiers and is idempotent:

- weather feature snapshot: `public_derived`
- market artifact: `user_uploaded`
- policy knowledge document: `user_uploaded`
- daily brief and policy-watch citation: local deterministic facts
- recommendation draft: `scenario_simulated`, `no_auto_trading=true`
- recommendation decision feedback: `user_uploaded`
- forecast research dataset: `scenario_simulated`, `research_only`
- baseline model run: `seasonal_naive`, `candidate`, `research_only`

Run readiness again after the worker completes. Demo coverage should be
complete, while operator review todos may still keep the overall status at
`warning`.

## Demonstration Path

1. Operations: check RC readiness, Action Center, source health, and fixed job
   run status.
2. Research: inspect policy corpus provenance and forecast research dataset
   health. The Forecast Research card should show the selected dataset's
   read-only review package, including provenance, quality issue summary,
   candidate model count, `no_auto_trading=true`, and recommendation-chain
   isolation.
3. Brief: open the seeded daily brief, inspect policy watch citations, and add
   a human review.
4. Recommendation: inspect evidence audit, confirm scenario-simulated inputs,
   run an optional hydro constraint preview, record a human decision, then add
   feedback.
5. Forecasting: import a local CSV/JSON research curve if desired and run a
   fixed `seasonal_naive` or `calendar_mean` backtest.

## Hydro Constraint Preview

The Recommendation workspace includes a "??????" panel for local
Demo Hydro A constraint research. It writes `hydro_optimization_runs` only.
It does not create recommendation runs, change recommendation confidence,
execute trades, submit market orders, or log in to trading platforms.

The preview always keeps `scenario_simulated`, `human_review_required=true`,
and `no_auto_trading=true`. If no 96-point price signal is supplied, it returns
a constraint-only preview and a missing-data warning.

Minimal API check:

```powershell
curl -X POST http://localhost:8000/v1/scenarios/demo_hydro/optimization-runs `
  -H "Content-Type: application/json" `
  -d "{\"trade_date\":\"2026-06-16\",\"available_energy_mwh\":4200,\"firm_output_mw\":120,\"installed_capacity_mw\":600}"
```

Recent runs:

```powershell
curl http://localhost:8000/v1/scenarios/demo_hydro/optimization-runs/recent
```

## Validation Commands

```powershell
pytest -q
ruff check .
mypy .
git diff --check
Set-Location webapp
npm run lint
npm test -- --run
npm run build
npm run test:e2e:no-data-workspaces
npm run test:e2e:research
npm run test:e2e:compose
.\scripts\run_no_data_trial_validation.ps1
.\scripts\validate_framework_readiness.ps1
.\scripts\scaffold_first_data_day_package.ps1 --output-dir <local-first-data-day-folder> --json
.\scripts\validate_first_data_day_package.ps1 --manifest docs\import_contracts\first_data_day_package.example.json --json
.\scripts\validate_zero_data_framework_closure.ps1
.\scripts\validate_no_data_workstation.ps1
.\scripts\validate_no_data_trial_suite.ps1
.\scripts\validate_import_contracts.ps1
.\scripts\validate_rag_trial.ps1
.\scripts\validate_forecast_training_trial.ps1
```

`npm run test:e2e:research` is a host-only targeted Playwright check. It mocks
the API routes needed by the Research workspace and verifies source status,
BENCH region isolation, baseline backtest payloads, and the forecast review
package download button. It does not need the Docker stack and does not fetch
external sources.

If database migrations changed, also run:

```powershell
alembic upgrade head
```

For host-only Alembic checks, make sure `DATABASE_URL` points to a reachable
PostgreSQL host. The Compose service hostname `db` resolves inside Compose but
not from a plain host shell. Prefer the Compose `migrate` service when checking
the full local stack.

## Known Limits

- Demo data is not real Example Province operational data.
- Hydro optimization previews are scenario-simulated research records, not
  dispatch instructions or trading recommendations.
- Forecast baselines are candidates for research inspection only.
- Source collection remains disabled unless a fixed registered endpoint is
  reviewed, verified, and enabled.
- The RC checklist is an operator aid. It does not approve recommendations,
  change confidence, call external models, or execute trades.
