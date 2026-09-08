> Synthetic protocol fixture documentation; not real-world research evidence.

# Anonymous Official Market Field Verification

## Decision

The adapter-design gate remains `blocked`.

As of 2026-06-01, no registered official endpoint has demonstrated a trusted
anonymous HTTPS contract with verified Example Province day-ahead or real-time field
semantics, units, interval timestamps, historical coverage, revision behavior,
and a confirmed 96-point curve.

The machine-readable evidence manifest is
[`evidence/anonymous_market_field_verification.json`](evidence/anonymous_market_field_verification.json).
Its JSON Schema is
[`evidence/anonymous_market_field_verification.schema.json`](evidence/anonymous_market_field_verification.schema.json).

## Verified Facts

| Endpoint | Verified observation | Adapter conclusion |
| --- | --- | --- |
| `example_province_portal_home` | Anonymous browser access reached `https://portal.market.example.invalid/portal/#/home`. The registered HTTPS shell and same-origin bundle were readable. | `blocked`: public bundle route fragments do not establish anonymous market-data fields or a 96-point contract. |
| `southern_spot_public_frontend` | Anonymous HTTPS access returned the Southern regional spot energy trading system shell. | `blocked`: the shell does not establish Example Province-specific fields, units, intervals, or history. |
| `reports_market_research` | The HTTP-only public column and sampled 2026-05-29 report were readable anonymously. | `blocked` for automated adapters: transport is not trusted HTTPS and values are weekly aggregates. |
| `reports_market_research_https_candidate` | System-default TLS verification failed with a certificate hostname mismatch. | `blocked`: TLS verification remains enabled. |

## REPORTS Aggregate Fields

The sampled REPORTS report provides auditable public context:

| Field | Unit | Time semantics | Qualification |
| --- | --- | --- | --- |
| `average_traded_energy` | `100_million_kwh` | Daily average over the weekly reporting period | Generation-side flash report |
| `weighted_average_price` | `cny_per_mwh` | Weighted average over the weekly reporting period | Generation-side flash report |

The report includes Southern-region totals and province-level values, including
Example Province, for day-ahead and real-time stages. It explicitly states that the
values are flash-report data rather than final settlement data.

These observations remain suitable only for reviewed manual preservation and
the existing weekly aggregate parser. They are not 96-point curves, forecast
training targets, or automatic recommendation inputs.

## Southern Public Bundle Follow-up

The Southern regional homepage directly exposes same-origin JavaScript bundles
for its public homepage and shared request client. Those bundles provide
discovery evidence:

- The homepage includes a `示例甲省省内市场化` quotation option.
- The request client uses `baseURL="/uptspot/ma/mp"`.
- The homepage calls the read-oriented
  `mpShowdataRecord/getXddsDataNew` path.
- The aggregate UI maps `otherData.energyPrice`, `otherData.marketShare`,
  `otherData.currentYearTotalEnergy`, and `otherData.currentYearOnYear`.

These fields are monthly or year-to-date aggregate UI mappings. They are not
day-ahead or real-time interval prices and do not establish a 96-point curve.

Anonymous read-only requests to the bundle's fixed menu and quotation paths
returned HTTP `404 GatewayRequestNotFound[4004]`. No alternate path was guessed
or probed. This leaves the deployed anonymous request contract unresolved.

A browser-side sanitized HAR can close that gap. Use
[`evidence/anonymous_market_har_collection_guide.md`](evidence/anonymous_market_har_collection_guide.md)
without logging in or sharing cookies, tokens, personal data, or company data.

## Research Boundary

This checkpoint inspected registered official public entry points and
same-origin static resources exposed by those pages. It did not disable TLS
verification, automate login, use market-participant credentials, implement a
crawler, schedule collection, or infer undocumented fields.

## Next Gate

Create `codex/example_province-spot-price-adapter` only after reproducible evidence
confirms:

1. An intended anonymous official HTTPS data endpoint.
2. Example Province market scope and day-ahead or real-time semantics.
3. Field names, units, timestamps, and interval granularity.
4. Historical coverage and revision behavior.
5. Whether an official 96-point curve is actually exposed.
