# AGENTS.md

## Project Goal

Build a Example Province power-market intelligence and hydro trading-advice system.

The MVP is a human-in-the-loop decision support system, not an autonomous
trading robot. It should collect public data, preserve evidence, generate
market briefs and scenario-based advice, and record human review and feedback.

## MVP Boundaries

Allowed:

- Public data collection and cleaning.
- Policy and market document parsing.
- Evidence-backed RAG and rule impact analysis.
- Weather-driven and public-data-driven feature engineering.
- Price trend forecasting and backtesting.
- Scenario-based hydro recommendation drafts.
- Human review, feedback, and audit trails.

Not allowed in MVP:

- Live trading submission.
- Automatic market order placement.
- Login automation for trading platforms.
- Unreviewed model promotion.
- Sending sensitive internal company data to external models by default.
- Claims that simulated company data is real operational data.

## Current Data Reality

The user does not currently have internal company data. Treat all company-side
inputs as one of:

- `public_observed`: public official or public market data.
- `public_derived`: derived from public data with documented assumptions.
- `scenario_simulated`: synthetic scenario data for demos and stress tests.
- `user_uploaded`: data explicitly provided by the user later.

All bundled company-side scenarios use invented parameters and fictional assets.
Do not add real company names, operating records, or secrets to this public demo.

## Tech Stack

- Python 3.12
- FastAPI
- Streamlit
- PostgreSQL, TimescaleDB, pgvector
- MinIO
- Prefect
- SQLAlchemy, Alembic
- Pydantic
- pandas, scikit-learn, LightGBM or XGBoost
- pytest, ruff, mypy

## Working Rules

- Prefer small, reviewable patches.
- Keep public-source adapters isolated and testable.
- Every API endpoint must use Pydantic request and response schemas.
- Every database schema change must include an Alembic migration.
- Every recommendation object must include structured evidence.
- Every crawler must use timeout, retry, deduplication, logging, and source
  preservation.
- Never hardcode API keys, cookies, accounts, tokens, or credentials.
- Preserve raw data and source metadata whenever possible.
- Add tests for new modules and update docs when behavior changes.

## Collaboration Workflow

- Work autonomously when the requested change is clear, reviewable, and within
  the MVP boundaries. Inspect the relevant code, make a brief plan, implement,
  validate, and summarize the result.
- Continue on the current branch for small fixes, tests, documentation,
  linting, and follow-up work related to the current feature.
- Use a new `codex/<short-feature-name>` branch for an independent feature.
  Use an isolated `codex/experiment-<short-name>` branch for high-risk or
  uncertain experiments.
- Recommend a focused new conversation when starting an unrelated module,
  when parallel work would become confusing, or when the existing context is
  too long to preserve reliable decisions.
- Recommend a separate repository or project when a request belongs to a
  different product, deployment target, or business domain.
- Ask for human confirmation before irreversible file, migration, or data
  deletion; major architecture changes; production deployment changes;
  credential, permission, or sensitive-data handling changes; external sharing
  of private data; or business-critical changes to recommendation assumptions.
- The prohibited MVP capabilities above remain prohibited even with human
  confirmation. Do not implement live trading, automatic order placement,
  trading-platform login automation, or unreviewed model promotion.
- At the end of a coding task, report the branch strategy, changed files,
  validation performed, any remaining risks or human decisions, and a
  suggested commit message.

## Recommendation Safety

Every recommendation must include:

- input snapshot id or feature snapshot reference
- data mode: public, derived, simulated, or uploaded
- evidence entries with source, timestamp, field, value, and confidence
- missing data warnings
- risk level
- confidence score
- human review status
- clear statement that no automatic trading execution is performed

## Data Source Priority

Use this order when practical:

1. Official machine-readable APIs.
2. Official web pages, PDFs, reports, and announcements.
3. Credible secondary sources that cite official data.
4. Scenario simulation with explicit assumptions.

Weather defaults:

- Open-Meteo as the default no-key weather provider.
- QWeather as China-focused enhancement when a key is available.
- Amap as a city-level fallback when a key is available.

## Testing Rules

Before considering a coding task complete, run the narrowest relevant checks.
For broad changes, run:

```powershell
pytest
ruff check .
mypy .
```

If database models or migrations changed, also run:

```powershell
alembic upgrade head
```

## Security Rules

Never commit:

- API keys
- cookies
- credentials
- private company trading data
- live account information
- generated secrets

Use `.env` and `.env.example` for configuration. Keep `.env` out of git.
