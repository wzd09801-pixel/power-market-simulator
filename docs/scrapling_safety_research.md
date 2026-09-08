# Scrapling Safety Research Notes

Checked on 2026-06-08 from the user-supplied local archive
`Scrapling-main.zip`.

Archive SHA-256:

```text
A9DD361982F0ABC3F527154FB51F8EEB2E857A02E159FB1D79DAD0469217E619
```

This note records what can be learned from Scrapling without changing this
project's collection boundary. It is an engineering reference only. This
project does not vendor Scrapling, add it as a runtime dependency, or enable
its crawler, stealth, proxy, browser, or anti-bot features.

## Snapshot

- Package version in the archive: `0.4.9`.
- License in the archive: BSD 3-Clause.
- Core areas reviewed: parser, fetcher defaults, spider engine, scheduler,
  request fingerprinting, robots.txt manager, tests, and documentation.
- Local execution was limited to parser, scheduler, and robots.txt logic using
  static HTML and injected fake fetch functions. No live target was fetched.

## Useful Patterns

These patterns are compatible with the workstation's public-source collection
model and may be adapted in this repository with project-native code:

- Keep source adapters isolated behind a fixed registry entry and a typed
  handler. Do not let caller input select arbitrary URLs, modules, commands, or
  dynamic fetcher classes.
- Use injected fetch functions for robots.txt or source health logic so tests
  can prove behavior without network access.
- Cache robots.txt per domain during one run, but keep every blocking decision
  auditable.
- Combine explicit allowlists with per-domain concurrency, request delay, and
  bounded retry.
- Canonicalize request identity for queue deduplication. For persisted evidence
  and raw bodies, continue to use SHA-256 rather than crawler-internal hashes.
- Preserve checkpoint and scheduler state only as execution recovery metadata.
  It must not replace source evidence, raw payloads, object keys, or audit
  records.
- Treat development caches as local acceleration only. They are not source
  preservation.
- Test adapters with static fixtures, malformed input, disabled sources,
  duplicate content, timeout, retry exhaustion, and zero-request assertions.

## Rejected Capabilities

The following Scrapling capabilities are not allowed in this MVP and must not
be wired into workstation jobs or policy collection:

- Cloudflare or anti-bot bypass.
- Browser stealth modes, Patchright/Playwright runtime scraping, canvas noise,
  or fingerprint spoofing.
- TLS or browser impersonation as a default fetch strategy.
- Proxy rotation or proxy-based access workarounds.
- Google referer injection, HTTP/3 impersonation, or generated browser header
  profiles intended to look like a different client.
- Login automation, captcha handling, cookie replay, or session harvesting.
- AI or MCP tools that accept arbitrary URLs or browse outside a fixed source
  registry.

If a future research spike evaluates any of these features, it must remain in
an isolated experiment branch and cannot be connected to production collection
jobs or Example Province recommendation evidence.

## Dependency Findings

Scrapling's package layout is not a clean fit for direct dependency use in this
project:

- Importing spider submodules executes package-level imports that require HTTP
  and browser-related optional dependencies.
- The static fetcher is built around `curl_cffi` and defaults such as browser
  impersonation, stealth headers, retries, redirects, and optional proxy
  rotation.
- Response conversion imports Playwright types even when a caller only wants
  non-browser response handling.
- The parser defaults to `huge_tree=True`, which can be useful for large pages
  but is not the right default for untrusted large documents unless file size
  and memory bounds are enforced.

Because of this coupling, the current decision is to learn from Scrapling's
architecture but keep project-native adapters using ordinary HTTP clients,
explicit timeout, bounded retry, TLS validation, source preservation, and
registry-level gates.

## Local Execution Evidence

The local validation used a temporary virtual environment and installed only
the minimum libraries needed to import parser, robots, and scheduler code.
Playwright, Patchright, browserforge, stealth browser runtime, and proxy
tooling were not installed or executed.

The verified local behaviors were:

- Static HTML parsing via `Selector` extracted title text and link attributes.
- Scheduler deduplication dropped a canonical duplicate URL while allowing an
  explicit `dont_filter=True` retry-style request.
- Robots.txt parsing used an injected fake fetch function, blocked a disallowed
  path, allowed an allowed path, and cached the domain so the fake fetch was
  called once.

Observed output:

```text
parser.title Title
parser.links ['/a?b=2&a=1', '/b']
scheduler.enqueue True False True
scheduler.next https://example.org/path?a=1&b=2 9
robots.public True
robots.private False
robots.delay (2.0, (3, 1))
robots.fetch_calls 1 https://example.org/robots.txt
```

The `Request-rate: 3/10` fixture was returned by Protego as `(3, 1)` in this
local check, so any future robots request-rate implementation needs its own
unit tests and conservative interpretation.

## Project Rule

Scrapling may be cited as a reference for crawler structure, but project
adapters must continue to satisfy the existing data-source policy:

- fixed official or reviewed public entrypoints only
- no arbitrary URL fetch
- no bypass of TLS, login, captcha, robots.txt, rate limits, or
  anti-automation controls
- timeout, bounded retry, and structured failure audit
- raw source preservation with source URL, fetch time, media type, object key,
  byte size, and SHA-256
- no automatic recommendation use unless a data source is explicitly reviewed,
  labeled, and allowed by the recommendation safety rules
