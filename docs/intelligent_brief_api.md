# Intelligent Brief API

## Safety Model

Briefs and questions are human-reviewed research outputs. They do not submit
trades, change recommendations, or alter confidence scores in the existing
scenario recommendation module.

## Deterministic Briefs

Each brief snapshot keeps local fact counts, missing-information warnings,
risk level, confidence score, review state, and `no_auto_trading=true`. BENCH
appears only as an isolated `research_only` benchmark fact.

DeepSeek may add a structured explanation. The adapter uses fixed API
configuration, explicit timeout, bounded retry, JSON validation, and a
deterministic fallback. Model ids are environment settings.

## Brief Review Loop

Operators can inspect recent briefs through `GET /v1/intelligence/briefs` and
open the full evidence snapshot plus review history through
`GET /v1/intelligence/briefs/{brief_id}`. Reviews are append-only records
created through `POST /v1/intelligence/briefs/{brief_id}/reviews`, while the
brief keeps its latest `human_review_status` for dashboard display.

Reviewing a brief is a local audit action only. It does not trigger collection,
fetch URLs, send additional content to external models, modify recommendation
evidence, or execute trades.

## Cited Questions

Local search retrieves chunks with embeddings and lexical matches, then calls
the local BGE reranker. External Q&A context is filtered to documents with
`external_processing_allowed=true`. The response stores:

- retrieved chunk ids
- citations
- excluded restricted chunk count
- confidence score
- missing information
- human-review requirement

The system returns an evidence warning instead of inventing an answer when no
authorized chunks are available.
