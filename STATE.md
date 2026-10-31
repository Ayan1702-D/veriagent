# VeriAgent Build State

- **Current Level**: L10 (Curated Corpus RAG)
- **Status**: Complete
- **Completed**:
  - [x] L0: Repo directory tree, `pyproject.toml`, `Makefile`, `.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `CONTEXT.md`, `STATE.md`.
  - [x] L1: Core Pydantic v2 schemas (`schemas/models.py`), `config.py`, `core/errors.py`, `core/budget.py`, `core/logging.py`, `audit/recorder.py`.
  - [x] L2: `llm/router.py`, `llm/cache.py`, `llm/client.py`, `llm/fake.py`, `llm/prompts/*.md`.
  - [x] L3: `core/security.py`, `tools/search/`, `tools/fetch.py`, `tools/parse.py`, `ranking/scorer.py`, `ranking/dedupe.py`.
  - [x] L4: `verification/quote_match.py` (`verify_quote`), `verification/entailment.py` (`check_support`, `build_counter_queries`, `apply_unsupported_claim_rule`), and `test_l4_verification.py`.
  - [x] L5: LangGraph state, nodes, conditional routing, graph builder, budget exhaustion handling, and `test_l5_graph.py`.
  - [x] L6: SQLAlchemy persistence, database audit sink, FastAPI run/audit/replay/SSE endpoints, background execution, rate limiting, CORS, consistent errors, and `test_l6_api.py`.
  - [x] L7: Next.js App Router frontend with live SSE run tracking, accessible report components, evaluation dashboard, responsive layouts, and dark mode.
  - [x] L8: Validated JSONL evaluation datasets, offline replay artifacts, retrieval/citation/classification/support/human-agreement metrics, JSON and Markdown reports, direction-aware regression gating, pull-request workflow, and focused metric tests.
  - [x] L9a: Slim non-root backend container, local Compose stack, Render and Vercel configuration, strict production settings, seeded offline demo replays, smoke test, and deployment runbook.
  - [x] L10: PDF/TXT/Markdown corpus ingestion, overlapping FastEmbed chunks in ChromaDB, curated retrieval through the search-provider interface, verified corpus quotes, guarded upload API, and corpus ablation evaluation reports.
- **Next Up**:
  - [ ] Awaiting the next implementation task.
- **Blockers / Open Decisions**: None.
