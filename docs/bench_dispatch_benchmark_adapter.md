# BENCH Dispatch Benchmark Adapter

## Purpose

This adapter imports official Australian Energy Market Operator (BENCH)
National Electricity Market (NEM) DispatchIS files as a forecasting
infrastructure benchmark. It is not a Example Province market-data adapter.

Every imported BENCH dataset remains:

- `market_scope=bench_nem_dispatch_benchmark`
- `region_code=BENCH_NEM_<REGIONID>`
- `data_mode=public_derived`
- `usage_scope=research_only`

It is isolated from Example Province recommendations and cannot change recommendation
actions or confidence scores.

## Official Contract

[BENCH's Dispatch page](https://operator.benchmark.example.invalid/energy-systems/electricity/national-electricity-market-nem/data-nem/market-management-system-mms-data/dispatch)
states that DispatchIS files contain public five-minute dispatch data by
region, including regional reference price. The official
[`DISPATCHPRICE`](https://models.benchmark.example.invalid/bench/nemweb/mmsdatamodelreport/electricity/mms%20data%20model%20report_files/MMS_130.htm)
data-model page documents `RRP` as the regional reference price used to settle
the market and records revision fields such as `ROP`, `INTERVENTION`, `RUNNO`,
`DISPATCHINTERVAL`, and `LASTCHANGED`.

The adapter fetches only the fixed official HTTPS archive directory:

```text
https://archive.benchmark.example.invalid/Reports/ARCHIVE/DispatchIS_Reports/
```

Callers may submit only daily filenames matching:

```text
PUBLIC_DISPATCHIS_YYYYMMDD.zip
```

The API does not accept a URL and does not crawl directory listings.

## Fetch And Preservation

Fetches use an explicit timeout, bounded retries, exponential backoff, and
disabled redirect following. The parser enforces size and member-count limits
before unpacking nested ZIP files.

For each fetched daily ZIP, nested five-minute ZIP, and CSV, the adapter
preserves metadata including filenames, sizes, compression metadata, CRC32,
and SHA-256. Daily ZIP SHA-256 values form the stable deduplication basis for
the imported benchmark dataset. Retrieval timestamps, HTTP content type, and
HTTP last-modified metadata remain attached to the preserved source metadata.

The workstation handler stores the official daily ZIP body once in MinIO with
SHA-256 deduplication and records its object key in PostgreSQL. Nested ZIP and
CSV bodies are recoverable losslessly from that daily ZIP, so they retain full
metadata and SHA-256 values without duplicate object storage.

The scheduled handler computes the local `D-2` daily filename, downloads it
once, parses it once, and derives separate NSW1, QLD1, SA1, TAS1, and VIC1
`research_only` datasets. It does not accept a caller-supplied URL.

## RRP Parsing And Revisions

The parser normalizes only `DISPATCH,PRICE` rows and retains source-native
five-minute records before any aggregation. For each selected NEM region it
preserves:

- `SETTLEMENTDATE`
- `RRP`
- `ROP`
- `INTERVENTION`
- `RUNNO`
- `DISPATCHINTERVAL`
- `LASTCHANGED`
- `APCFLAG`
- `MARKETSUSPENDEDFLAG`
- `PRICE_STATUS`

BENCH market timestamps are treated as AEST using `Australia/Brisbane`.
`SETTLEMENTDATE` is the five-minute period end, so the adapter subtracts five
minutes to produce the source-native interval start. When multiple rows share
the same source key, the latest `LASTCHANGED` row is selected for aggregation
while all revision rows remain preserved. Ambiguous semantic variants are
rejected.

## Fifteen-Minute Derivation

The imported curve is explicitly derived:

1. Require three consecutive source-native five-minute RRP values.
2. Group them by fifteen-minute interval start.
3. Calculate their arithmetic mean.
4. Round to four decimal places with `ROUND_HALF_UP`.
5. Import the resulting complete 96-point trade date as `public_derived` and
   `research_only`.

Partial aggregation buckets are rejected. BENCH data is never relabeled as a
directly observed Example Province 96-point curve.

## API

```text
POST /v1/forecasting/research/benchmarks/bench-dispatch/archive
```

Example request:

```json
{
  "archive_filenames": ["PUBLIC_DISPATCHIS_20260531.zip"],
  "region_id": "NSW1"
}
```
