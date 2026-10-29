# VeriAgent Build State

- **Current Level**: L4 (Verification Layer: Deterministic Quote Matching, Entailment, Adversarial Counter-Queries)
- **Status**: Complete
- **Completed**:
  - [x] L0: Repo directory tree, `pyproject.toml`, `Makefile`, `.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `CONTEXT.md`, `STATE.md`.
  - [x] L1: Core Pydantic v2 schemas (`schemas/models.py`), `config.py`, `core/errors.py`, `core/budget.py`, `core/logging.py`, `audit/recorder.py`.
  - [x] L2: `llm/router.py`, `llm/cache.py`, `llm/client.py`, `llm/fake.py`, `llm/prompts/*.md`.
  - [x] L3: `core/security.py`, `tools/search/`, `tools/fetch.py`, `tools/parse.py`, `ranking/scorer.py`, `ranking/dedupe.py`.
  - [x] L4: `verification/quote_match.py` (`verify_quote`), `verification/entailment.py` (`check_support`, `build_counter_queries`, `apply_unsupported_claim_rule`), and `test_l4_verification.py`.
- **Next Up**:
  - [ ] L5: LangGraph workflow nodes, state schema, conditional routing edges, and graph builder (`graph/`).
- **Blockers / Open Decisions**: None.