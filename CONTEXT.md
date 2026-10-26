# VeriAgent Context

## Overview
VeriAgent is a multi-agent research and fact-verification system. It investigates a claim, retrieves evidence, ranks sources, extracts quotes, finds contradictions, verifies citations, and writes a report.
Verdicts: `SUPPORTED | REFUTED | MIXED | CONDITIONAL | INSUFFICIENT`. It reports uncertainty and never forces true/false.

## Differentiators
1. **Scope-aware verdicts**: Detects qualifiers ("always", "regardless", "all") and tests boundary conditions.
2. **Deterministic citation check**: Fuzzy-matches extracted quotes against stored page snapshots (`rapidfuzz`) without LLM tokens.
3. **Budget governor**: Hard caps on tokens, searches, fetches, loops, and wall-clock seconds per run.
4. **Record/replay audit trail**: Every LLM and tool response is recorded so runs replay offline deterministically.
5. **Adversarial verification pass**: Searches for counter-evidence to its tentative conclusion.
6. **Source independence**: Deduplicates syndicated or near-duplicate articles so repeated press releases do not inflate support.
7. **Eval harness gated in CI**: Regression-gated metrics on a reviewed claim dataset using recorded cassettes.

## Tech Stack (Zero Budget)
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, LangGraph, LiteLLM, SQLAlchemy (SQLite dev / Postgres prod), `httpx`, `trafilatura`, `rapidfuzz`, ChromaDB + `fastembed` (optional RAG).
- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS.
- **Quality & Ops**: `pytest`, `ruff`, `mypy`, GitHub Actions, Docker.

## Core Schemas (`backend/src/veriagent/schemas/`)
- `Claim`: `id, text, qualifiers[], atomic_subclaims[]`
- `SubQuestion`: `id, claim_id, question, search_queries[]`
- `Source`: `id, url, title, domain, fetched_at, snapshot_hash, rank_score, source_type (primary|secondary|news|blog)`
- `Evidence`: `id, source_id, quote, date, stance (supports|contradicts|neutral), quote_verified (bool), context_conditions[]`
- `Finding`: `subclaim_id, supporting[], contradicting[], gaps[], verdict, confidence`
- `RunBudget`: `max_llm_tokens, max_searches, max_fetches, max_loops, max_seconds`
- `AuditEvent`: `run_id, seq, node, type, payload, tokens, ts`
- `Report`: `claim, findings[], verdict, limitations[], citations[]`

## Repository Layout
- `backend/src/veriagent/{api,core,llm,graph/nodes,tools,ranking,verification,rag,schemas,db,audit}`
- `backend/eval`, `backend/tests`
- `frontend/` (Next.js App Router)
- `docs/`, `corpus/`