# Interval Forecasting Research Foundation

## Purpose

This stage establishes a reviewable 96-point forecasting research path before a
trusted Example Province spot-price adapter exists. It is an engineering foundation,
not a claim that Example Province day-ahead or real-time 96-point prices are publicly
available.

Every imported dataset is fixed to:

- `interval_minutes=15`
- `usage_scope=research_only`
- an explicit region, market stage, price scope, timezone, currency, price
  unit, source name, source URL, and data mode

Research datasets and model runs are isolated from recommendation generation.
They cannot alter recommendation actions or confidence scores.

## Public Benchmark Adapter

[BENCH's official Dispatch page](https://operator.benchmark.example.invalid/energy-systems/electricity/national-electricity-market-nem/data-nem/market-management-system-mms-data/dispatch)
documents public five-minute regional dispatch files, including regional
reference price and demand. The official
[`DISPATCHPRICE`](https://models.benchmark.example.invalid/bench/nemweb/mmsdatamodelreport/electricity/mms%20data%20model%20report_files/MMS_130.htm)
data-model page marks the table as public and documents five-minute updates,
regional identifiers, revisions, and the `RRP` settlement-price field.

BENCH is used to exercise the research pipeline because its source semantics
are documented. It is not a Example Province source and it is not directly a
15-minute series. The source-specific adapter accepts only fixed official
daily archive filenames, preserves ZIP and CSV metadata with SHA-256 hashes,
retains source-native revision fields, and explicitly averages each three
consecutive five-minute `RRP` values into one 15-minute `public_derived`
research point. See
[`bench_dispatch_benchmark_adapter.md`](bench_dispatch_benchmark_adapter.md).

## Storage Model

1. `forecast_research_datasets` preserves immutable metadata, canonicalized
   structured submissions, content hashes, quality status, and
   `research_only` usage scope.
2. `forecast_research_dataset_import_runs` records accepted, duplicate, and
   rejected submissions.
3. `forecast_research_price_points` stores normalized 15-minute points only
   after a submission passes quality checks.
4. `forecast_research_quality_issues` keeps semantic failures visible without
   silently publishing partial curves.
5. `forecast_research_model_runs` registers successful baseline backtests as
   `candidate` runs.
6. `forecast_research_predictions` preserves each predicted and actual
   interval pair for audit and later analysis.

## Quality Contract

The manual import endpoint never fetches the submitted URL. The URL is evidence
metadata only.

Each accepted trade date must contain exactly 96 unique points aligned to exact
15-minute boundaries. Invalid submissions retain their canonicalized request
payload and quality issues, but publish no normalized price points and cannot be
backtested.

The manual contract intentionally rejects source-native five-minute or hourly
curves. The BENCH source-specific adapter preserves its native format and
normalizes only explicit derived 15-minute points through a separate endpoint.

## Baseline Backtests

The first research models are intentionally simple:

- `seasonal_naive`: use the same interval from a configurable number of days
  earlier, defaulting to seven days.
- `calendar_mean`: use the average for the same interval across available prior
  days inside a configurable lookback window, defaulting to seven days.

Both models run rolling historical evaluation and record:

- MAE
- RMSE
- sMAPE
- peak-period MAE
- valley-period MAE
- direction accuracy
- high-price-window recall
- peak-valley spread MAE
- prediction count

No model is automatically promoted. Every run is stored with
`registry_status=candidate`, `usage_scope=research_only`, and
`data_mode=public_derived`.

## Host-Only Training Trial Smoke

Run the local preflight before using real price files:

```powershell
.\scripts\validate_forecast_training_trial.ps1
```

The smoke creates an in-memory API test app, imports a valid simulated
96-point research dataset, imports an invalid incomplete curve, runs
`seasonal_naive` and `calendar_mean` backtests, checks predictions and review
packages, and confirms no recommendation objects are created. It does not
start Docker, write persistent databases, fetch source URLs, schedule
training, promote models, or execute trades.

## API

```text
POST /v1/forecasting/research/datasets/manual
POST /v1/forecasting/research/benchmarks/bench-dispatch/archive
GET  /v1/forecasting/research/overview
GET  /v1/forecasting/research/datasets
GET  /v1/forecasting/research/import-runs
GET  /v1/forecasting/research/datasets/{dataset_id}/points
GET  /v1/forecasting/research/datasets/{dataset_id}/review-package
GET  /v1/forecasting/research/quality/issues
POST /v1/forecasting/research/datasets/{dataset_id}/backtests
GET  /v1/forecasting/research/model-runs
GET  /v1/forecasting/research/model-runs/{model_run_id}/predictions
```

`GET /v1/forecasting/research/overview` is a local-only observability aggregate.
It summarizes dataset quality, recent import runs, recent quality issues,
candidate model runs, and BENCH five-region research coverage without fetching
external sources. The React research workspace uses the same API plus the
existing list/detail endpoints to show candidate metrics and prediction curves
only after an operator selects a dataset/model run or manually triggers one of
the fixed baseline backtests.

`GET /v1/forecasting/research/datasets/{dataset_id}/review-package` is a
dataset-level operator review snapshot. It returns the selected dataset
metadata, recent import runs, quality issue details, aggregated issue counts by
severity and issue code, candidate model runs, and explicit no-trading and
recommendation-isolation flags. It is read-only, does not fetch source URLs,
does not write server-side report artifacts, and does not include the complete
raw payload or full price-point series.

The React workspace also provides a local import workbench for manually prepared
CSV or JSON curves. CSV files must contain `interval_start` and `price` columns;
JSON files may be a point array or an object with a `points` array and optional
dataset metadata. The preview reports point count, date coverage, duplicate
intervals, incomplete 96-point dates, timezone-offset errors, invalid prices,
ignored CSV columns, and sample rows before calling the manual import endpoint.
The browser parser does not fetch `source_url`; that field remains provenance
metadata, and the backend remains the final authority for 96-point quality
checks and SHA-256 deduplication.

The dashboard is not a model registry promotion workflow. It cannot mark a run
as production, start scheduled training, execute arbitrary model code, modify
Example Province recommendation evidence, or trigger trading. Its review package
download is generated in the browser from the read-only API response and remains
operator review material, not recommendation evidence.

## Next Gate

The Example Province adapter remains a separate gate. It requires trusted anonymous
HTTPS evidence, verified Example Province field semantics, historical coverage, and a
confirmed 96-point curve.
