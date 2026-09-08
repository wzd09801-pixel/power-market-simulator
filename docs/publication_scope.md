# Publication scope

This repository is a sanitized, synthetic demonstration snapshot. It does not
represent a real company, power station, exchange, market operator, or operating
record. Example market URLs use reserved `.invalid` domains and cannot supply
real market data. Historical-looking reports, dates, statuses, and protocol
examples are test fixtures, not retained evidence of real access or operations.

Hydro parameters are invented. Source-specific market collectors are retained
as protocol examples only and require new reviewed integration work before use.
Open-Meteo and optional model-service integrations are public technical
dependencies; they do not establish any company affiliation. Weather coordinates
are generic examples, not station locations. No original Git history, local
`.env`, credentials, database volumes, uploaded documents, model artifacts, or
private reports are included.

Use a fresh database for this snapshot. Identifier and fixture changes are not
an in-place migration path for any earlier private deployment. Default local
service passwords in `.env.example` are development examples, not real secrets.
Never use them for an internet-facing deployment. No automatic trading is provided.

Scheduled collection is off by default in Compose. The scheduler is under the
`schedules` profile; enable it only after configuring reviewed usable sources.

## Validation limits

The host-only backend tests use an in-memory database; browser smoke tests use
mocked API responses. They do not certify live upstream data, model accuracy,
PostgreSQL migrations, or the complete Compose deployment.

Docker was unavailable during snapshot preparation. Offline Alembic SQL
generation also stops at a JSON seed literal unsupported by the existing
migration renderer. Run the online migrations against a fresh local PostgreSQL
instance before relying on container startup; do not apply these renamed seed
identifiers to an existing private deployment.
