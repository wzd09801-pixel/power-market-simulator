# Policy Knowledge Foundation

## Purpose

The personal research knowledge base preserves public policy material,
research documents, and local uploads without turning the API into an
arbitrary URL fetcher. Source reliability, traceability, and explicit document
labels take priority.

## Document Layers

- `official_policy`
- `official_market_notice`
- `public_research`
- `user_uploaded`

Every document keeps its source, raw MinIO object, SHA-256, parsed text,
immutable version, chunks, and human-review state. Public research material is
never presented as an official source.

## Operator Review Package

`GET /v1/policy/documents/{document_id}/review-package` returns a local JSON
review package for one policy document. The package includes provenance,
latest-version and raw-object summaries, chunk and embedding coverage, bounded
chunk excerpts, review history, and explicit safety flags. It is intended for
operator inspection and local browser download from the Operations Action
Center.

The package is read-only: it does not include the full raw payload, write a
server-side artifact, fetch sources, run network probes, call external models,
authorize external processing, promote knowledge into recommendation evidence,
or execute trades.

## External Processing Boundary

Uploads start with `external_processing_allowed=false`. An operator may change
that flag only through the audited per-document endpoint. Future external LLM
requests must filter context chunks using the document-level flag before
constructing prompts.

## Fixed Source Candidates

The initial registry contains:

- Example Energy Regulator downloads
- Example Electricity Council
- Example Electricity Association
- Example Research Institute

Collection remains disabled by default. INSTITUTE is manual-import only because
its public website currently responds with HTTP 418 to automated requests.
Collectors must not bypass TLS failures, login gates, CAPTCHA challenges, or
anti-automation controls.

## Local Embeddings

The Docker embedding service defaults to `BAAI/bge-m3`. It exposes an internal
fixed `/embed` endpoint and stores 1024-dimensional pgvector values on chunks.
The API remains usable when the embedding service is temporarily unavailable:
it preserves chunks without vectors so local evidence is not lost.

## Host-Only Trial Smoke

Run the local trial smoke before connecting real documents:

```powershell
.\scripts\validate_rag_trial.ps1
```

The smoke creates an in-memory API test app, uploads a local text document,
checks chunks, corpus overview, review package, cited search, Q&A authorization
boundaries, and document review. It uses deterministic local test embeddings
and a fake local model client, so it does not access external networks or real
model providers.
