# VeriAgent Build State

- **Current Level**: L3 (Tools & Ranking: Search, SSRF Guard, Fetch, Parse, Scorer, Dedupe)
- **Status**: Complete
- **Completed**:
  - [x] L0: Repo directory tree, `pyproject.toml`, `Makefile`, `.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `CONTEXT.md`, `STATE.md`.
  - [x] L1: Core Pydantic v2 schemas (`schemas/models.py`), `config.py`, `core/errors.py`, `core/budget.py`, `core/logging.py`, `audit/recorder.py`.
  - [x] L2: `llm/router.py`, `llm/cache.py`, `llm/client.py`, `llm/fake.py`, `llm/prompts/*.md`.
  - [x] L3: `core/security.py` (SSRF guard), `tools/search/{base,ddg,wikipedia,openalex,tavily}.py`, `tools/fetch.py`, `tools/parse.py`, `ranking/domains.yaml`, `ranking/scorer.py`, `ranking/dedupe.py`, and `test_l3_tools_and_ranking.py`.
- **Next Up**:
  - [ ] L4: Deterministic quote matching (`verification/quote_match.py`), LLM entailment verification (`verification/entailment.py`), and LangGraph workflow nodes (`graph/`).
- **Blockers / Open Decisions**: None.