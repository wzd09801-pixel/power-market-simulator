# Import Contracts For No-Data Trial Runs

These files are operator-facing examples for the first day real data becomes
available. They do not add new APIs and they do not enable collection,
external model calls, model promotion, or trading execution.

Before copying or editing a template, read the operator SOP in
`docs/first_data_day_operator_manual.md`. It explains the local package
structure, metadata fields, dry-run statuses, and review handoff.

Run the local contract gate before editing these templates or using a copied
data file:

```powershell
.\scripts\validate_framework_readiness.ps1
.\scripts\validate_first_data_day_package.ps1 --manifest docs\import_contracts\first_data_day_package.example.json
.\scripts\validate_zero_data_framework_closure.ps1
.\scripts\validate_no_data_trial_suite.ps1
.\scripts\validate_import_contracts.ps1
```

The framework gate first checks local documentation, schemas, contracts, and
safety markers for first-data-day readiness. The suite runs import, RAG, and
forecast/training local gates together. The contract command validates the JSON
examples against existing Pydantic request schemas, checks the 96-point
forecast CSV shape, and confirms local-only MVP safety wording. These commands
do not start services, read credentials, write the database, or contact external
networks.

The zero-data closure gate ties the three framework layers together: templates,
package dry-run, and empty-state safety boundaries.

For a future local data folder, copy
`first_data_day_package.example.json` to `first_data_day_package.json` inside
that folder, or create the skeleton with:

```powershell
.\scripts\scaffold_first_data_day_package.ps1 --output-dir <local-first-data-day-folder> --json
```

Then run:

```powershell
.\scripts\validate_first_data_day_package.ps1 --package-dir <local-first-data-day-folder> --json
```

An empty or newly scaffolded directory is a controlled validation failure. It
reports missing inputs, workflow readiness, disabled capabilities,
simulated-only capabilities, and next actions instead of importing, training,
answering RAG questions, or inventing evidence.

## Templates

- `first_data_day_package.example.json`: package-level manifest for future
  CSV, JSON, PDF, DOCX, HTML, weather reference JSON, and recommendation
  review-context JSON files. It keeps RAG local-only by default, forecast and
  backtest artifacts `research_only`, recommendations
  `scenario_simulated_only`, and `no_auto_trading=true`.
- `policy_document_upload.example.json`: form and file metadata for
  `POST /v1/policy/documents/upload`.
- `market_artifact_manual_submission.example.json`: request body for
  `POST /v1/market/artifacts/manual`.
- `weather_open_meteo_reference_request.example.json`: request body for
  `POST /v1/weather/open-meteo/forecast`.
- `forecast_research_curve.example.csv`: one complete 96-point 15-minute
  research curve for browser-local preview.
- `forecast_research_dataset.example.json`: request body for
  `POST /v1/forecasting/research/datasets/manual`.
- `forecast_backtest_request.example.json`: request body for baseline candidate
  backtests after enough accepted history exists.
- `hydro_optimization_request.example.json`: request body for
  `POST /v1/scenarios/demo_hydro/optimization-runs`.
- `recommendation_request.example.json`: request body for a human-reviewed
  scenario recommendation draft.

## Required Operator Checks

- Keep `no_auto_trading=true` wherever the response exposes that flag.
- Keep company-side values `scenario_simulated` unless verified internal data
  is later provided.
- Keep local uploads `user_uploaded`.
- Treat `source_url` values as provenance unless the endpoint explicitly
  belongs to a fixed registered adapter.
- Do not paste credentials, cookies, account ids, private company data, or
  trading-platform exports into these templates.
