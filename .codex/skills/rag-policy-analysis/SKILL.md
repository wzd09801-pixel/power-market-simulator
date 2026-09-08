---
name: rag-policy-analysis
description: Use when implementing policy document parsing, chunking, embeddings, vector retrieval, rule diff analysis, LLM-based policy impact summaries, cited answers, or hydro-market compliance analysis for this project.
---

# RAG Policy Analysis

Policy and rule outputs must be evidence-backed.

## Scope

Support:

- policy document ingestion
- HTML, PDF, and Word parsing
- chunking and metadata preservation
- embedding and vector search
- rule diff
- hydro generation company impact analysis
- cited market brief and policy watch sections

## RAG Rules

Every LLM answer must include:

- retrieved document ids
- cited chunk ids or source URLs
- confidence score
- missing information
- whether human review is required

Do not answer policy questions without retrieved evidence. Do not invent market
rules. Mark outdated or uncertain material explicitly.

## Chunking Defaults

Use 800 to 1200 Chinese characters per chunk with 150 to 250 characters of
overlap, preserving:

- title
- source
- publish date
- effective date when known
- section heading
- source URL or object key

## Rule Diff Output

Rule diff JSON should include:

- document title
- effective date if available
- changed items
- affected market stage
- impact to hydro
- risk level
- operator checklist
- code rule update needed
- evidence
