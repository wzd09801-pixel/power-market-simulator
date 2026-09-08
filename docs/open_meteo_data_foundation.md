# Open-Meteo Data Foundation

## Scope

This stage adds a reviewable public-weather ingestion foundation. It does not:

- schedule background collection
- derive reservoir hydrology or market features
- change recommendation generation
- submit trades or automate any trading-platform interaction

## Delivered Slice

- Open-Meteo forecast adapter with explicit timeout, bounded retry, parsing,
  normalization, and structured errors.
- Public reference-location registry with remapping protection.
- Raw payload preservation and content-hash deduplication.
- Normalized hourly weather records labeled `public_observed`.
- Success and failure ingestion-run audit rows.
- Manual ingestion and normalized-record query APIs.
- Adapter, persistence, deduplication, and failure-path tests.
- Derived quality issues for local missing values, timestamp continuity,
  expected units, conservative value ranges, and precipitation consistency.
- Versioned `hydro_weather_v1` feature snapshots with evidence and
  missing-data warnings.

Open-Meteo does not expose a separate forecast issue timestamp in this
response. The normalized record uses retrieval start time as an explicit
provider-specific `issue_time` proxy.

## Review Gates Before Forecast Features

1. Select documented public reference points for the relevant basin and nearby
   weather context.
2. Review hourly variables and aggregation windows for hydro use cases.
3. Run manual ingestion over representative forecast cycles.
4. Inspect raw payload retention, revision behavior, and data quality metrics.
5. Review the initial rainfall and temperature features stored as
   `public_derived`.
6. Connect approved features to a new recommendation snapshot version.

## API Notes

`POST /v1/weather/open-meteo/forecast` fetches a forecast for a caller-supplied
reference point. `GET /v1/weather/records` returns normalized rows and supports
filtering by `location_id` and `variable`.

`GET /v1/weather/quality/issues` exposes reviewable derived findings.
`GET /v1/weather/features/latest` exposes the latest versioned hydro-weather
feature snapshot for a reference location.
`POST /v1/weather/features/{feature_snapshot_id}/reviews` records an operator
review and updates the latest human-review status.

An approved snapshot may be explicitly attached to recommendation generation
when its forecast window starts on the recommendation trade date. The
attachment is auditable input context only; it does not automatically change
strategy actions.

The first persistence implementation keeps raw payload text and parsed JSON in
PostgreSQL. Larger document and payload storage can move to MinIO in a later
phase while PostgreSQL retains hashes, metadata, and object references.
