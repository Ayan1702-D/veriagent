# VeriAgent - Phase 1 Design

A multi-agent research and fact-verification system. It investigates a claim instead of simply answering it, and reports uncertainty and conflicting evidence rather than forcing true/false.

Example claim: "Electric vehicles always produce fewer lifetime emissions than petrol vehicles, regardless of how electricity is generated."
Expected style of result: **CONDITIONAL** - depends on grid mix, with cited evidence on both sides.

---

## 1. Positioning (what makes it unique)

| Differentiator | What it is | Why it impresses |
|---|---|---|
| Scope-aware verdicts | Detects qualifiers ("always", "regardless", "all") and tests the claim's boundary conditions | Shows reasoning, not retrieval |
| Deterministic citation check | Every quote must be fuzzy-matched in the stored page snapshot, no LLM involved | Zero tokens, no hallucinated citations, measurable |
| Budget governor | Hard caps on tokens, searches, fetches, loops, seconds per run, visible live in the UI | Production thinking |
| Record/replay audit trail | Every LLM and search response is stored so any run replays exactly and offline | Debuggability and free evals |
| Adversarial pass | Verifier searches for counter-evidence to its own conclusion | Fights confirmation bias |
| Source independence | Detects syndicated or duplicate sources so 5 copies of a press release don't count as 5 sources | Rare in student projects |
| Eval harness in CI | Regression-gated metrics on a reviewed claim set | Strongest interview talking point |

**Verdict taxonomy:** `SUPPORTED`, `REFUTED`, `MIXED`, `CONDITIONAL`, `INSUFFICIENT`.

---

## 2. Tech stack (zero budget)

| Layer | Choice | Notes |
|---|---|---|
| Orchestration | LangGraph (Python) | State machine with loops and budgets |
| Backend | FastAPI + Pydantic v2, SSE streaming | Async, typed |
| LLM access | LiteLLM wrapper | Swap Gemini / Groq / OpenRouter free models without code changes |
| Search | DuckDuckGo (`ddgs`), Wikipedia, OpenAlex / Crossref / Semantic Scholar, Tavily free tier (optional) | General plus primary sources |
| Parsing | `trafilatura` | Clean text plus stored snapshot |
| RAG | ChromaDB (local) + `fastembed` | Small ONNX embeddings, no GPU |
| Database | SQLite (dev), Postgres on Neon/Supabase free tier (prod) | Via SQLAlchemy |
| Frontend | Next.js + TypeScript + Tailwind | Live run view |
| Tests / CI | pytest, ruff, GitHub Actions | Evals run in CI from cached responses |
| Deploy | Vercel (frontend) + Hugging Face Spaces Docker or Render (backend) | Verify current free-tier limits first |

---

## 3. System architecture

```text
                    +-------------------------------------+
                    |          Next.js Frontend           |
                    |  ClaimForm -> RunView (live SSE)    |
                    |  EvidenceTable | AuditTrail | Eval  |
                    +----------------+--------------------+
                                     | REST + SSE
                    +----------------v--------------------+
                    |            FastAPI API              |
                    |  rate-limit | validation | CORS     |
                    +----------------+--------------------+
                                     | starts run
      +------------------------------v------------------------------+
      |                    LangGraph Workflow                       |
      |                                                             |
      |  Planner --> Researcher --> Extractor --> Contradiction     |
      |  (decompose   (search,       (quotes,      Analyst          |
      |   + scope)     fetch, rank)   dates, refs) (agree/disagree/ |
      |      ^                                      gaps)           |
      |      |  gaps found AND budget left            |             |
      |      +----------------------------------- Verifier          |
      |                                          (quote match +     |
      |                                           entailment +      |
      |                                           adversarial)      |
      |                                               |             |
      |                                         Report Generator    |
      |                                                             |
      |  Budget Governor wraps every node | Audit Recorder logs     |
      +-------+----------------+-------------------+----------------+
              |                |                   |
        +-----v-----+   +------v-------+   +-------v--------+
        | LLM layer |   | Tools layer  |   |   Data layer   |
        | LiteLLM   |   | search/fetch |   | SQL + Chroma   |
        | router +  |   | rank/dedupe  |   | run events,    |
        | cache     |   | SSRF guard   |   | snapshots      |
        +-----------+   +--------------+   +----------------+
```

**Key decisions**
- Six specialised steps in one controlled graph, not six independent LLMs. Cheaper and more reliable.
- Model router: small model for extraction and classification, stronger model only for contradiction analysis and the report.
- Verifier runs deterministic checks first (quote exists, URL fetched, date parsed), then an LLM entailment check only on what remains.
- The loop-back edge (Verifier to Planner/Researcher) is allowed only while budget remains.

---

## 4. Core data models (`schemas/`)

```text
Claim:        id, text, qualifiers[], atomic_subclaims[]
SubQuestion:  id, claim_id, question, search_queries[]
Source:       id, url, title, domain, fetched_at, snapshot_hash,
              rank_score, source_type (primary|secondary|news|blog)
Evidence:     id, source_id, quote, date, stance (supports|contradicts|neutral),
              quote_verified (bool), context_conditions[]
Finding:      subclaim_id, supporting[], contradicting[], gaps[], verdict, confidence
RunBudget:    max_llm_tokens, max_searches, max_fetches, max_loops, max_seconds
AuditEvent:   run_id, seq, node, type, payload, tokens, ts
Report:       claim, findings[], verdict, limitations[], citations[]
```

---

## 5. Project structure

```text
veriagent/
├── README.md                  # demo GIF, architecture diagram, eval table
├── Makefile                   # make dev | test | eval | lint
├── docker-compose.yml
├── .env.example
├── CONTEXT.md                 # short summary to paste into any AI tool
├── STATE.md                   # 10-line progress log
├── .github/workflows/
│   ├── ci.yml                 # lint + unit tests
│   └── eval.yml               # replay-based eval + metric regression gate
├── docs/
│   ├── architecture.md
│   ├── adr/                   # decision records
│   ├── audit-trail-spec.md
│   └── eval-report.md
│
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/veriagent/
│       ├── main.py            # FastAPI app factory
│       ├── config.py          # pydantic-settings
│       ├── api/
│       │   ├── routes_runs.py     # POST /runs, GET /runs/{id}, SSE stream
│       │   ├── routes_eval.py
│       │   ├── routes_corpus.py   # RAG upload/index
│       │   └── deps.py
│       ├── core/
│       │   ├── budget.py          # governor
│       │   ├── security.py        # SSRF guard, injection defence, limits
│       │   ├── logging.py         # structured JSON logs + run_id
│       │   ├── errors.py
│       │   └── rate_limit.py
│       ├── llm/
│       │   ├── client.py          # LiteLLM wrapper + retries
│       │   ├── router.py          # cheap vs strong model per node
│       │   ├── cache.py           # record/replay cassettes
│       │   ├── fake.py            # FakeLLM for tests
│       │   └── prompts/           # versioned .md prompt files per node
│       ├── graph/
│       │   ├── state.py
│       │   ├── builder.py         # wires nodes and conditional edges
│       │   ├── edges.py           # loop / stop decisions
│       │   └── nodes/
│       │       ├── planner.py
│       │       ├── researcher.py
│       │       ├── extractor.py
│       │       ├── contradiction.py
│       │       ├── verifier.py
│       │       └── reporter.py
│       ├── tools/
│       │   ├── search/ (base.py, ddg.py, wikipedia.py, openalex.py, tavily.py)
│       │   ├── fetch.py
│       │   └── parse.py
│       ├── ranking/
│       │   ├── scorer.py          # authority + recency + primary-source
│       │   ├── domains.yaml       # editable trust tiers
│       │   └── dedupe.py          # syndication / near-duplicate detection
│       ├── verification/
│       │   ├── quote_match.py     # deterministic fuzzy quote check
│       │   └── entailment.py      # LLM check, only on unresolved items
│       ├── rag/ (ingest.py, store.py, retriever.py)
│       ├── schemas/               # models from section 4
│       ├── db/ (models.py, session.py, repo.py)
│       └── audit/ (recorder.py, replay.py, renderer.py)
│   ├── eval/
│   │   ├── dataset/claims.jsonl   # reviewed claims + evidence
│   │   ├── metrics.py             # the 5 metrics
│   │   ├── run_eval.py
│   │   └── reports/
│   └── tests/ (unit/, integration/, fixtures/cassettes/)
│
├── frontend/
│   ├── package.json
│   ├── app/
│   │   ├── page.tsx               # claim input + examples
│   │   ├── runs/[id]/page.tsx     # live run + final report
│   │   └── eval/page.tsx          # metrics dashboard
│   ├── components/
│   │   ├── ClaimForm.tsx
│   │   ├── AgentTimeline.tsx      # nodes lighting up via SSE
│   │   ├── BudgetMeter.tsx
│   │   ├── EvidenceTable.tsx      # claim | supporting | contradicting | conclusion
│   │   ├── SourceCard.tsx         # rank, type, verified-quote badge
│   │   ├── VerdictBadge.tsx
│   │   ├── AuditTrail.tsx
│   │   └── ReportView.tsx         # export to Markdown/PDF
│   └── lib/ (api.ts, sse.ts, types.ts)
│
└── corpus/                        # curated docs for the RAG extension
```

---

## 6. API surface

```text
POST /api/runs                 body: claim, budget?  -> {run_id}
GET  /api/runs/{id}            -> status + report
GET  /api/runs/{id}/stream     -> SSE (node events, budget usage)
GET  /api/runs/{id}/audit      -> full event log
POST /api/runs/{id}/replay     -> re-run from cassettes (no tokens)
POST /api/corpus               -> add documents to RAG
GET  /api/eval/latest          -> latest metrics
GET  /health
```

---

## 7. Production-grade checklist

- **Security:** SSRF guard on fetches (block private IPs), fetched pages treated as untrusted data (prompt-injection defence), input length caps, rate limiting, CORS locked to your frontend, secrets only via env.
- **Reliability:** retries with caps and backoff, per-node timeouts, graceful "budget exhausted" report instead of a crash.
- **Observability:** structured logs with `run_id`, tokens and latency per node, audit trail UI.
- **Quality:** typed code (ruff/mypy), pytest with mocked LLM, eval gate in CI.
- **Docs:** README with diagram, ADRs, published eval report.

---

## 8. Evaluation plan

- Build 40-60 claims with reviewed evidence. Seed from public datasets such as SciFact or FEVER, then add your own topical claims (EVs, nutrition, tech).
- Metrics: evidence retrieval precision, citation validity, claim classification accuracy, unsupported-claim rate, agreement with human-reviewed conclusions.
- First run uses real APIs and records cassettes. Later runs replay them for free, so you can tune scoring and prompts without spending tokens.

Example report table:

| Claim | Supporting evidence | Contradicting evidence | Conclusion |
|---|---|---|---|
| Claim A | Source 1 | Source 2 | Mixed evidence |
| Claim B | Sources 3 and 4 | None found | Supported by available evidence |
| Claim C | Insufficient evidence | None found | Inconclusive |

Every source reference must point to the actual document or webpage used.

---

## 9. Build order (fastest path to a live demo)

| Step | Deliverable | Result |
|---|---|---|
| 1 | Schemas, config, mocked graph, FastAPI + SSE | End-to-end skeleton |
| 2 | Search, fetch, ranking, quote matcher | Real evidence, verified citations |
| 3 | Planner, Extractor, Contradiction, Verifier, Reporter with a real LLM | Working agent |
| 4 | Next.js live view + evidence table | Demoable UI |
| 5 | Budget governor, audit trail, replay | Production feel |
| 6 | Eval dataset + CI gate | Resume numbers |
| 7 | Deploy, README, demo GIF | Shareable |
| 8 | RAG extension | Bonus |

---

## 10. Review gate

**Assumptions**
- A public deployed demo matters more than a polished local one.
- Free-tier LLM rate limits are the main bottleneck, so the design leans on caching and cheap models.
- Next.js frontend plus Python backend is acceptable. A separate Node backend would add complexity without benefit.

**Top risks**
- Free hosting cold starts and memory limits can break the live demo. Keep embeddings light and the Chroma index small.
- Free search APIs get blocked or rate-limited. Tools sit behind a common interface and a cassette cache exists for this reason.
- Hand-reviewing 40 claims is the biggest time cost and also the most valuable part of the project.

**Disclaimer:** free-tier limits, package versions, and install commands change often. Verify against official docs before installing or deploying.
