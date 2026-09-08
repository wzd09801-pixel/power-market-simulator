---
name: data-pipeline
description: Use when building crawlers, weather adapters, source registries, public data ingestion jobs, Prefect flows, parsers, deduplication, raw document storage, or data quality checks for this project.
---

# Data Pipeline

Every source adapter should follow:

1. Fetch.
2. Parse.
3. Normalize.
4. Validate.
5. Deduplicate.
6. Persist.
7. Emit logs and metrics.

## Adapter Requirements

- Use explicit timeout and retry settings.
- Preserve source URL, provider, fetch time, and raw payload or object key.
- Compute content hashes for documents and repeated observations.
- Never silently drop failed records.
- Return structured errors for network, parse, validation, and persistence
  failures.
- Keep source-specific parsing isolated from shared storage logic.

## Data Modes

Set `data_mode` explicitly:

- `public_observed`
- `public_derived`
- `scenario_simulated`
- `user_uploaded`

## Weather Provider Order

Prefer:

1. Open-Meteo for no-key forecast and historical weather.
2. QWeather for China-focused warning and fine-grained weather when configured.
3. Amap for city-level fallback when configured.

Store provider, location id, issue time, forecast time, variable, value, unit,
raw payload reference, and quality flag.

## Tests

Each adapter needs tests for:

- successful sample response
- empty response
- malformed response
- duplicate data
- timeout or HTTP error
