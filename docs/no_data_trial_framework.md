# No-Data Trial Framework

This checklist turns the current MVP into a data-ready local research
framework. It assumes the operator has no verified internal company data yet.
The goal is to make the first real data day boring: copy data into known
contracts, run fixed local commands, inspect review packages, and keep every
result human-reviewed.

For the operator-facing step-by-step procedure, read
`docs/first_data_day_operator_manual.md` first. This checklist remains the
framework validation reference.

## Safety Boundary

- This is a personal local research workstation, not production deployment.
- Company-side examples remain `scenario_simulated` or `user_uploaded` until
  verified internal data is provided.
- Do not add live trading submission, automatic order placement, trading
  platform login automation, unreviewed model promotion, or arbitrary URL
  crawling.
- External model use remains opt-in. Uploaded documents default to local-only
  processing and must not be sent outside the workstation by default.
- Forecast research datasets and model runs remain `research_only` and cannot
  enter recommendation evidence.

## Framework Readiness Gate

Before replacing any example with user data, run the static framework gate:

```powershell
.\scripts\validate_framework_readiness.ps1
```

This is the first dry-run check for the no-data framework. It reads local
documentation, import contracts, schemas, and safety-boundary implementation
markers only. It does not start Docker, write PostgreSQL or MinIO, contact
external networks, call external models, run Alembic, schedule training,
promote models, or execute trades.

The gate confirms that import contracts, forecast dataset manifests, RAG
document readiness, market and weather review readiness, baseline
training/backtest prerequisites, and recommendation safety boundaries are
present before a real file is copied into a template. Market artifacts remain
manual preserved evidence, weather review packages do not automatically change
recommendation generation, forecast research remains `research_only`, and
recommendations remain human-reviewed drafts with `no_auto_trading=true`.

## First-Data-Day Package Dry-Run

After the static framework gate passes, validate the local package directory
that will eventually hold future files. To create a no-data skeleton first:

```powershell
.\scripts\scaffold_first_data_day_package.ps1 --output-dir <local-first-data-day-folder> --json
```

Then run the dry-run:

```powershell
.\scripts\validate_first_data_day_package.ps1 --package-dir <local-first-data-day-folder> --json
```

If the directory is empty or the manifest is missing, the command returns a
stable `missing_required_inputs` report with `ok=false`, missing items, disabled
capabilities, simulated-only capabilities, and next actions. That is a valid
operator state while no data exists. The report includes per-workflow readiness
for RAG, forecast, backtest, market/weather, and recommendation. RAG answering
stays disabled, forecast training and backtests stay disabled, recommendation
mode remains
`scenario_simulated_only`, external model calls remain disabled, and
`no_auto_trading=true` is preserved.

When preparing for a real first data day, copy
`docs/import_contracts/first_data_day_package.example.json` to
`first_data_day_package.json` inside the local package folder, replace only
placeholder metadata that is known, and run the dry-run again. The validator
checks local paths, CSV headers for forecast curves, JSON forecast manifest
shape, weather reference JSON shape, recommendation review-context metadata,
and document metadata for PDF, DOCX, HTML, TXT, or Markdown RAG inputs. It does
not upload files, parse raw document content, write databases, start Docker,
fetch URLs, call external models, run migrations, promote models, or change
recommendation execution.

## Host-Only Trial Suite

After the package scaffold and dry-run behavior are in place, the closure gate
checks all three zero-data framework layers together:

```powershell
.\scripts\validate_zero_data_framework_closure.ps1
```

It verifies contract/template coverage, creates a temporary scaffolded package,
confirms its dry-run returns controlled missing inputs, and checks that existing
empty-state docs/tests keep RAG, training, backtests, and recommendation
execution disabled while no data exists.

Before starting Docker or replacing examples with user data, run the local
workstation gate:

```powershell
.\scripts\validate_no_data_workstation.ps1
```

This is the default no-data framework gate. It chains the backend/RAG/forecast
trial suite and the cockpit workspace smoke. It does not start Docker, read
credentials, write PostgreSQL or MinIO, contact external networks, call a real
external model, schedule training, promote models, or execute trades.

To run only the backend/RAG/forecast side:

```powershell
.\scripts\validate_no_data_trial_suite.ps1
```

That command chains the import contract validator, RAG local trial, and
forecast/training trial. It uses only host processes and in-memory test
databases.

For the browser cockpit smoke over the three main workspaces:

```powershell
Set-Location webapp
npm run test:e2e:no-data-workspaces
```

This Playwright target uses mocked API responses from the existing cockpit
spec. It covers Operations overview and review-package controls, Research
source status and forecast package download, and Recommendation simulated
data/no-trading boundaries. It does not require a live backend, Docker, real
data, external collection, external models, scheduled training, or trading
execution.

## Empty Database Baseline

1. Start services with `docker compose up --build`, or run the isolated
   validation script:

   ```powershell
   .\scripts\run_no_data_trial_validation.ps1
   ```

   The script allocates temporary host ports, uses a unique Compose project
   name, stops containers at the end, and keeps its PostgreSQL and MinIO
   volumes for inspection. It does not delete, reset, or repair historical
   volumes.
2. Open Operations or call `GET /v1/system/readiness`.
3. Expected empty-state behavior:
   - readiness returns `warning`, not an exception;
   - missing demo or data objects are listed explicitly;
   - recommendation isolation stays healthy;
   - responses preserve `no_auto_trading=true`;
   - no network probe, external model call, training job, or trade action is
     triggered by the readiness endpoint.
4. Run the fixed `demo_research_workspace_seed` job only when a deterministic
   local demo is needed. Demo data is not real operational data.

`run_no_data_trial_validation.ps1` queues that fixed seed job, waits for the
local worker to mark it `succeeded`, confirms missing demo items are cleared,
and checks the operations review package still reports local-only safety flags
such as `manual_job_keys_only=true`, `fetch_performed=false`, and
`network_probe_performed=false`.

## First Data Day Order

Use the templates in `docs/import_contracts/` and keep this order:

Before importing anything, run:

```powershell
.\scripts\validate_framework_readiness.ps1
.\scripts\scaffold_first_data_day_package.ps1 --output-dir <local-first-data-day-folder> --json
.\scripts\validate_first_data_day_package.ps1 --package-dir <local-first-data-day-folder> --json
.\scripts\validate_zero_data_framework_closure.ps1
.\scripts\validate_no_data_trial_suite.ps1
.\scripts\validate_import_contracts.ps1
```

These are host-only preflights. The framework gate checks readiness from local
contracts, docs, schemas, and safety markers. The scaffold command creates
only local directories, README, and manifest metadata. The package dry-run
validates the operator's local folder before any import. The suite then runs
the import, RAG, and forecast trial gates together; the contract command checks
only the repository's import examples. These commands do not start Docker,
write the database, call external services, answer without evidence, train,
backtest, or promote models.

1. Preserve source material first: policy documents and manually submitted
   public market artifacts.
2. Review provenance and quality packages before using parsed or derived
   outputs.
3. Build or ingest weather reference features, then approve a snapshot before
   linking it to recommendations.
4. Import 15-minute research curves only after their source, timezone, unit,
   and data mode are clear.
5. Run baseline backtests only on accepted `research_only` datasets with enough
   historical days.
6. Generate recommendation drafts only after required scenario inputs are
   labeled and review warnings are understood.

## RAG Trial Path

Before starting services or using real documents, run the host-only smoke:

```powershell
.\scripts\validate_rag_trial.ps1
```

It uses an in-memory database, memory blob store, deterministic local
embeddings, and a fake local model client. It does not start Docker, write
PostgreSQL or MinIO, read credentials, contact external networks, or call a
real external model.

1. Upload a local policy document through `POST /v1/policy/documents/upload`.
2. Confirm `external_processing_allowed=false` unless the operator explicitly
   changes the authorization.
3. Check corpus coverage with `GET /v1/policy/corpus/overview`.
4. Inspect `GET /v1/policy/documents/{document_id}/review-package`.
5. Use search, policy watch, or Q&A only with cited chunks. If embeddings are
   unavailable, the API may preserve chunks without vectors and retrieval may
   rely more on lexical matching.
6. Record human review with `POST /v1/policy/documents/{document_id}/reviews`.

## Forecast Trial Path

Before connecting real price files or running local services, run the host-only
forecast/training smoke:

```powershell
.\scripts\validate_forecast_training_trial.ps1
```

It uses in-memory SQLite and existing forecasting research endpoints to verify
manual 96-point imports, invalid curve diagnostics, baseline backtests,
candidate model runs, predictions, review packages, and recommendation-chain
isolation. It does not start Docker, write PostgreSQL, fetch sources, schedule
training, promote models, or execute trades.

1. Import a manual curve through `POST /v1/forecasting/research/datasets/manual`
   or the browser-local import workbench.
2. A valid trade date must have exactly 96 unique 15-minute points with
   timezone offsets.
3. Incomplete, duplicate, or timezone-naive intervals must stay visible as
   quality issues and must not publish normalized points for training.
4. Run `seasonal_naive` or `calendar_mean` backtests only after enough
   historical days exist for the requested evaluation window.
5. Candidate model runs must keep `registry_status=candidate`,
   `usage_scope=research_only`, and `no_auto_trading=true`.

## Acceptance Checklist

- Empty database readiness is warning-only and safe.
- The static framework readiness gate passes before user files replace the
  example contracts.
- The first-data-day package dry-run either passes for a complete local folder
  or returns a stable missing-input report for an empty folder.
- The first-data-day scaffold creates only local package metadata and empty
  directories, never synthetic data files.
- The zero-data closure gate passes across contract/template coverage,
  scaffold/dry-run behavior, and empty-state safety boundaries.
- The host-only no-data workstation gate passes before Docker or real data is
  used.
- The host-only no-data trial suite passes before Docker or real data is used.
- The host-only no-data workspace smoke passes for Operations, Research, and
  Recommendation.
- Demo seed produces the full local review loop without external fetches.
- The no-data validation script passes in Docker environments, or records a
  Docker/Docker Hub blocker while host-only tests remain green.
- Each provided data file has a matching contract template.
- RAG upload, chunking, embedding fallback, search, Q&A, and document review
  are tested with empty, demo, and uploaded data.
- Forecast import rejects malformed curves and persists candidate backtests
  without model promotion.
- Operations, Research, and Recommendation workspaces pass targeted smoke
  checks.
