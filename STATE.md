# VeriAgent Build State

- **Current Level**: L6 (Persistence and FastAPI Runtime)
- **Status**: Complete
- **Completed**:
  - [x] L0: Repo directory tree, `pyproject.toml`, `Makefile`, `.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `CONTEXT.md`, `STATE.md`.
  - [x] L1: Core Pydantic v2 schemas (`schemas/models.py`), `config.py`, `core/errors.py`, `core/budget.py`, `core/logging.py`, `audit/recorder.py`.
  - [x] L2: `llm/router.py`, `llm/cache.py`, `llm/client.py`, `llm/fake.py`, `llm/prompts/*.md`.
  - [x] L3: `core/security.py`, `tools/search/`, `tools/fetch.py`, `tools/parse.py`, `ranking/scorer.py`, `ranking/dedupe.py`.
  - [x] L4: `verification/quote_match.py` (`verify_quote`), `verification/entailment.py` (`check_support`, `build_counter_queries`, `apply_unsupported_claim_rule`), and `test_l4_verification.py`.
  - [x] L5: LangGraph state, nodes, conditional routing, graph builder, budget exhaustion handling, and `test_l5_graph.py`.
  - [x] L6: SQLAlchemy persistence, database audit sink, FastAPI run/audit/replay/SSE endpoints, background execution, rate limiting, CORS, consistent errors, and `test_l6_api.py`.
- **Next Up**:
  - [ ] L7: Frontend and later roadmap layers.
- **Blockers / Open Decisions**: None.
