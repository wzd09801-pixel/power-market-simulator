# Reference Repository Architecture Study

Checked on 2026-06-01 against the repositories' default branches. These
projects are engineering references only. This repository does not copy their
source code or inherit their architecture wholesale.

## MVP Context

The 40-day MVP is a human-reviewed Example Province power-market intelligence and
hydro trading-advice system. Its current compact monolith already separates
FastAPI routes, services, repositories, SQLAlchemy models, schemas, and
source-specific adapters. Recent foundation work preserved that structure while
adding narrowly scoped worker orchestration, forecasting research, policy RAG,
market briefs, and hydro scenario optimization preview interfaces.

The MVP must continue to preserve public evidence, distinguish observed,
derived, simulated, and uploaded data, and prohibit live trading, automatic
order placement, trading-platform login automation, and unreviewed model
promotion.

## Reference Matrix

| Repository | Checked default branch | Reusable patterns | Deferred or rejected for the MVP |
| --- | --- | --- | --- |
| [`zhanymkanov/fastapi_production_template`](https://github.com/zhanymkanov/fastapi_production_template) | `main@8e82353` | Environment configuration, connection-pool health checks, JSON logging, non-root Docker images, and migration helper scripts. | Replacing the current FastAPI layout wholesale, or immediately adding Gunicorn and Sentry. |
| [`reinhud/async-fastapi-postgres-template`](https://github.com/reinhud/async-fastapi-postgres-template) | `master@c5d64f8` | `routes -> services -> repositories -> models` layering, dependency injection, and database test fixtures. | Migrating the current synchronous SQLAlchemy codebase to async during the 40-day MVP. |
| [`anna-geller/prefect-deployment-patterns`](https://github.com/anna-geller/prefect-deployment-patterns) | `main@19f68ba` | Small flow and task composition, explicit failure states, and separation between critical and non-critical tasks. | Prefect Cloud, Kubernetes, AWS or Azure blocks, and complex notification integrations. |
| [`jeslago/epftoolbox`](https://github.com/jeslago/epftoolbox) | `master@47d6e06` | Reproducible electricity-price experiments, day-by-interval matrices, MAE, RMSE, sMAPE, MASE, and baseline comparisons. | Copying AGPL-licensed code, TensorFlow DNN models, or applying foreign-market models directly to Example Province. |
| [`unit8co/darts`](https://github.com/unit8co/darts) | `master@b0ccd3a` | A consistent `fit()` and `predict()` model shape, seasonal-naive baselines, rolling historical forecasts, and covariate categories. | Adding the complete Darts dependency, deep-learning models, ensembles, and its full anomaly-detection stack. |
| [`PyPSA/PyPSA`](https://github.com/PyPSA/PyPSA) | `master@fbd3ed5` | Reservoir inter-temporal constraints, rolling horizon concepts, and separation of inputs, solving, and results. | Grid power flow, capacity expansion, stochastic planning, and the full solver dependency chain. |
| [`grid-parity-exchange/Egret`](https://github.com/grid-parity-exchange/Egret) | `main@28c324f` | Declarative input data and separation between model formulation and result handling. | Unit commitment, AC or DC optimal power flow, Pyomo, and commercial solver integrations. |
| [`simranjeet97/Learn_RAG_from_Scratch_LLM`](https://github.com/simranjeet97/Learn_RAG_from_Scratch_LLM) | `main@0fc329d` | The basic document parsing, chunking, vector retrieval, and evidence-backed answer flow. | Caller-supplied URL fetching, API-key entry in the UI, unsafe deserialization, and local FAISS as production storage. |
| [`LegendStack/Agentic-FastAPI-Template`](https://github.com/LegendStack/Agentic-FastAPI-Template) | `main@f447c84` | Pydantic structured output, allowlisted tool argument validation, and bounded retry after invalid LLM output. | LangGraph, multi-agent orchestration, Redis, Neo4j, cross-system connectors, and enterprise identity integrations. |
| [`vstorm-co/full-stack-ai-agent-template`](https://github.com/vstorm-co/full-stack-ai-agent-template) | `main@07a8cd4` | Isolated RAG services, retrieval abstractions, and server-side injection of allowed knowledge-base scope. | A Next.js rewrite, multi-tenancy, billing, channel bots, WebSocket chat, and multiple agent frameworks in parallel. |
| Scrapling local archive | `0.4.9`, archive SHA-256 recorded in [`scrapling_safety_research.md`](scrapling_safety_research.md) | Isolated parser tests, injected fetch functions, robots.txt cache, scheduler deduplication, per-domain delay, checkpoints, and crawler metrics. | Direct runtime dependency, arbitrary URL crawling, Cloudflare or anti-bot bypass, stealth browser execution, TLS/browser fingerprint impersonation, proxy rotation, login automation, captcha handling, and cookie replay. |

## Adapted Architecture

Keep the current compact monolith. Extend it through explicit module boundaries
instead of adopting a large framework:

```text
backend/app/
  adapters/          # Official data-source and third-party API adapters
  api/routes/        # Thin FastAPI routes with Pydantic request and response schemas
  services/          # Use cases, audit logic, and human-review gates
  repositories/      # SQLAlchemy queries and persistence
  models/            # PostgreSQL models
  schemas/           # API contracts and structured-output schemas
  forecasting/       # Dataset snapshots, baselines, backtests, metrics, model registry
  rag/               # Policy parsing, chunking, retrieval, and citations
  optimization/      # Hydro scenario constraints and optimization preview interfaces
workers/
  flows/             # Prefect orchestration that calls reusable services
  tasks/             # Thin task wrappers with explicit failure recording
```

### Architecture Decisions

1. Continue using synchronous SQLAlchemy. The existing audit path is stable,
   and an async rewrite has insufficient MVP value relative to its regression
   risk.
2. Keep PostgreSQL as the business audit source of truth. Prefect run state is
   supplementary and must not replace ingestion, parsing, or quality records.
3. Build a lightweight forecasting interface in this repository before adding
   Darts or EPFtoolbox dependencies.
4. Label provincial, regional, or foreign 96-point history used for engineering
   research as `research_only`. It must not feed Example Province recommendations or
   raise recommendation confidence.
5. Use PostgreSQL and pgvector for the first policy RAG implementation. Every
   answer must return document ids, chunk ids, source URLs, confidence, missing
   information, and whether human review is required.
6. Keep any Agent API as a read-only orchestration facade. It may call
   allowlisted policy retrieval, forecast snapshot, and recommendation-draft
   query functions. It must not accept arbitrary URLs, execute arbitrary tools,
   submit trades, or bypass review.
7. Keep hydro-scenario optimization as an auditable preview interface. Do not
   add PyPSA, Egret, Pyomo, or solver dependencies until the scenario
   requirements justify them.
8. Treat Scrapling as a crawler design reference, not as a workstation runtime.
   Source adapters should copy only the safe patterns documented in
   [`scrapling_safety_research.md`](scrapling_safety_research.md) and continue
   using project-native allowlists, timeout, retry, TLS validation, evidence
   preservation, and audit records.

## Implemented Foundation Checkpoints

The initial reference checkpoints have been implemented as bounded MVP slices:

### 1. Forecasting research foundation

- Stores manually prepared complete 15-minute curves with
  `usage_scope=research_only`.
- Imports the BENCH DispatchIS archive as a research benchmark, separate from
  Example Province recommendations.
- Runs seasonal-naive and calendar-mean backtests with auditable metrics and
  candidate model records.

### 2. Worker and operation foundation

- Adds fixed local jobs for weather refresh, policy research refresh, BENCH
  research import, daily brief generation, demo seed, and smoke validation.
- Keeps orchestration behind explicit API and worker boundaries rather than
  allowing arbitrary job execution.

### 3. Policy RAG foundation

- Stores policy documents, chunks, embeddings, retrieval results, citations,
  confidence, missing information, and external-processing authorization.
- Keeps unsupported rule answers and sensitive-data sharing gated by the
  human-review policy.

### 4. Lightweight market brief API

- Generates read-only market briefs from approved weather features, public
  market observations, research forecast snapshots, and policy evidence.
- Preserves structured evidence, human review, and `no_auto_trading=true`.

### 5. Hydro scenario optimization preview

- Stores Demo Hydro A scenario hydro constraint previews in
  `hydro_optimization_runs`.
- Supports optional local 96-point price signals, derived constraint
  explanations, and recent-run comparisons.
- Keeps previews isolated from recommendation runs, trading execution, and
  external solver dependencies.

## Current Next Gates

- The Example Province anonymous official 96-point price adapter remains blocked until
  a trusted anonymous HTTPS source exposes verified field semantics and
  historical coverage.
- Automated public-market collection should proceed only through reviewed,
  source-specific adapters that preserve raw evidence, use explicit timeouts
  and bounded retries, deduplicate content, and expose structured failures.
- Hydro optimization research should stay in `scenario_simulated` or
  `user_uploaded` mode until verified internal data or public constraints are
  supplied. External solvers remain deferred until inputs, constraints, and
  audit requirements justify them.
- Near-term follow-up work should favor operator-facing documentation,
  evidence export, review workflows, and reporting over new trading or
  recommendation automation.

## Guardrails

- The Example Province anonymous official 96-point price adapter remains blocked until
  a trusted anonymous HTTPS source exposes verified field semantics and
  historical coverage.
- Public research datasets may validate the forecasting pipeline but cannot
  establish Example Province predictive performance.
- LLM output remains explanation, extraction, and review support. Numerical
  recommendation actions require deterministic logic and human review.
- Source adapters must preserve raw evidence, use explicit timeouts and bounded
  retries, deduplicate content, and expose structured failures.
