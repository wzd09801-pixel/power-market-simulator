> Synthetic protocol fixture documentation; not real-world research evidence.

# REPORTS Weekly Market Report Parser

## Boundary

The Example Regional Exchange market-research column publishes weekly
Southern-region spot-market reports. The public page is currently available
over HTTP while trusted HTTPS hostname validation fails. This parser therefore
does not fetch the website. It accepts only preserved, explicitly approved
`reports_market_research` HTML artifacts.

The source report states that volume and price values use a generation-side
flash-report basis and are not final settlement values. The normalized records
preserve those qualifications.

## Workflow

1. Preserve the official HTML through `POST /v1/market/artifacts/manual`.
2. Review it through `POST /v1/market/artifacts/{artifact_id}/reviews`.
3. Parse an approved artifact through
   `POST /v1/market/artifacts/{artifact_id}/parse/reports-weekly-report`.
4. Inspect results through `GET /v1/market/observations` and
   `GET /v1/market/parsing/runs`.

Parser `reports_weekly_market_report:v1` produces 24 observations:

- Southern-region total plus Example Province, Guangxi, Yunnan, Guizhou, and Hainan.
- Day-ahead and real-time market stages.
- Average traded energy and weighted average price.

The parser is idempotent by artifact, parser version, area, market stage, and
metric. Replays record duplicate counts without creating new observations.
Incomplete formats fail as a whole and remain visible in `market_parsing_runs`.

## Deferred Work

- Normalize the power-type section in a later parser version.
- Enable automated collection only after trusted anonymous HTTPS access is
  verified.
- Add a separate strongly typed interval table only after an official
  anonymous 96-point source is confirmed.
