> Synthetic protocol fixture documentation; not real-world research evidence.

# Anonymous Market HAR Collection Guide

## Purpose

The Southern regional public frontend exposes static bundle references to
aggregate market-quotation read paths, but direct anonymous requests currently
return gateway `404`. A sanitized browser HAR can show whether the live public
page uses a different official gateway prefix or whether the deployed bundle
is stale.

Collect only anonymous public-page traffic. Do not log in and do not include
market-participant, company, or personal data.

## Capture Steps

1. Open a private browser window.
2. Open Developer Tools and select the Network tab.
3. Enable `Preserve log` and disable the browser cache.
4. Visit <https://spot.market.example.invalid/uptspot/sr/pt/>.
5. Wait for the homepage to finish loading. Do not enter credentials.
6. If the page exposes a public Example Province selector, select it without logging
   in and wait for the public chart to refresh.
7. Export the Network log as HAR with content.

## Required Redaction

Before sharing the HAR:

1. Remove all `Cookie`, `Set-Cookie`, `Authorization`, `Proxy-Authorization`,
   `X-Token`, `Token`, and session headers.
2. Remove query parameters or JSON fields containing account ids, phone
   numbers, names, organization ids, tokens, captcha values, or device ids.
3. Remove request and response bodies unrelated to anonymous market quotation
   reads.
4. Keep the official request URL, HTTP method, status code, timestamp, and
   anonymous market response field names needed to verify semantics.
5. Inspect the final file manually and share only the sanitized copy.

## Useful Evidence

The sanitized HAR is useful if it shows:

- The actual official request URL used by the public homepage.
- Whether the request succeeds anonymously.
- Example Province or Southern-region market scope.
- Returned field names, units, timestamp meaning, and granularity.
- Whether any day-ahead, real-time, or 96-point curve exists.

The HAR is not evidence for adapter design if it requires login, contains
private data, or exposes only monthly and year-to-date aggregates.
