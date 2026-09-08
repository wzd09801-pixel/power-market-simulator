# Hydro Optimization Preview

This note documents the Demo Hydro A hydro constraint preview added for the
local research workstation. It is an auditable scenario preview, not a dispatch
instruction, trading recommendation, market order, or production optimizer.

## API

- `POST /v1/scenarios/demo_hydro/optimization-runs`
- `GET /v1/scenarios/demo_hydro/optimization-runs/recent?limit=5`
- `GET /v1/scenarios/demo_hydro/optimization-runs/{optimization_run_id}`

The POST request accepts a trade date and optional overrides for available
energy, minimum output, maximum output, and a 96-point price signal. If a price
signal is supplied, it must cover all 96 fifteen-minute intervals exactly once.
If no price signal is supplied, the service returns a constraint-only balanced
preview with a missing-data warning.

Responses include a derived `constraint_explanation` list. It summarizes the
algorithm boundary, energy floor and ceiling, whether a 96-point price signal
was used, binding interval counts, and the no-auto-trading review boundary.
The explanation is derived from the persisted request/result snapshot; this v2
slice does not add a new migration.

## Data Mode And Audit

Every saved preview is persisted in `hydro_optimization_runs` with:

- `data_mode="scenario_simulated"`
- `human_review_required=true`
- `no_auto_trading=true`
- request snapshot, constraints, result intervals, warnings, and structured
  evidence

When an operator supplies a local 96-point price curve, that curve is recorded
only as preview evidence with `data_mode="user_uploaded"`. It must not be
described as verified Example Province spot-market data unless a later source
verification workflow explicitly supports that claim.

The default Demo Hydro A constraints are synthetic scenario
assumptions. They must not be described as verified internal company reservoir,
dispatch, or contract-position data.

## Algorithm Boundary

The current algorithm is `deterministic_priority_v1`.

- It supports only 96 fifteen-minute intervals.
- It rejects energy budgets below the minimum-output energy floor or above the
  maximum-output energy ceiling.
- With a price signal, it ranks higher-price intervals first and allocates
  energy above minimum output within the output cap.
- Without a price signal, it distributes available energy evenly above the
  minimum output and warns that no market price curve was supplied.

This stage intentionally does not add PyPSA, Pyomo, PuLP, SciPy, commercial
solvers, stochastic optimization, or rolling production dispatch.

## Operator Flow

1. Open the React Cockpit Recommendation workspace.
2. Use the "水电约束预演" panel to enter trade date, energy budget, minimum
   output, and maximum output.
3. Optionally paste a 96-point price curve. The cockpit accepts either 96
   prices, 96 rows of `interval_index,price`, a JSON array of 96 prices, or a
   JSON array of `{ "interval_index": n, "price": value }` objects.
4. Run the preview and inspect summary intervals, warnings,
   `constraint_explanation`, `scenario_simulated`, `human_review_required`, and
   `no_auto_trading`.
5. Use the recent-run comparison table to compare energy budget, output bounds,
   price-signal usage, top intervals, and warning counts across local preview
   runs.
6. Keep recommendation review, decision, and feedback workflows separate. A
   hydro preview must not be copied into a recommendation run without a later
   explicit design change and human review.

## Validation

Relevant checks:

```powershell
pytest -q
ruff check .
mypy .
git diff --check
Set-Location webapp
npm run lint
npm test
npm run build
npx playwright test --list
```

When validating the migration, run it where PostgreSQL is reachable. In the
Compose environment, the `migrate` service can resolve the `db` hostname and
runs both migration consistency and `alembic upgrade head`.
