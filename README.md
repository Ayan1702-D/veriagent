# VeriAgent

VeriAgent investigates factual claims and returns a cited verdict with an inspectable audit trail.

## Demo

> **Demo GIF placeholder** — add the final recording at `docs/assets/veriagent-demo.gif`.

<!-- Replace this comment with: ![VeriAgent demo](docs/assets/veriagent-demo.gif) -->

## Problem

Most answer systems optimize for a plausible response. A fact-verification workflow needs a
different set of controls: source retrieval, preserved evidence, counter-evidence searches,
quote verification, calibrated verdicts, resource limits, and a record of how the result was
produced.

VeriAgent treats verification as a bounded research process rather than a single model prompt.

## How it works

1. The planner splits a submitted statement into testable subclaims and search questions.
2. The researcher retrieves, deduplicates, and ranks candidate sources.
3. The extractor records quotations and links them to stored source snapshots.
4. The contradiction stage searches for exceptions and conflicting evidence.
5. The verifier checks quote matches and identifies unsupported conclusions.
6. The reporter issues one of five verdicts with limitations and citations.
7. Audit events and budget usage are persisted and streamed to the frontend.

> **Architecture diagram placeholder** — add the final diagram at
> `docs/assets/veriagent-architecture.svg`.

<!-- Replace this comment with: ![VeriAgent architecture](docs/assets/veriagent-architecture.svg) -->

## What makes it different

1. **Five verdicts.** Results can be `SUPPORTED`, `REFUTED`, `MIXED`, `CONDITIONAL`, or
   `INSUFFICIENT`; the system is not restricted to true/false output.
2. **Verified quotations.** Evidence quotes are matched against stored source text before they
   can support a conclusion.
3. **Counter-evidence search.** Contradictions and boundary conditions are investigated as a
   separate workflow stage.
4. **Source independence controls.** Duplicate URLs and repeated publications are reduced before
   synthesis.
5. **Hard budgets.** Tokens, searches, fetches, loops, and wall time have server-enforced caps.
6. **Inspectable execution.** Ordered audit events and live budget usage are available through
   REST and Server-Sent Events.
7. **Offline replay.** Completed runs and seeded demonstrations can be reproduced without network
   or model calls.

## Tech stack

| Area | Technology |
|---|---|
| API | Python 3.11, FastAPI, Pydantic v2 |
| Workflow | LangGraph |
| Models | LiteLLM with Gemini, Groq, or OpenRouter credentials |
| Retrieval | DuckDuckGo, Wikipedia, OpenAlex, optional Tavily |
| Curated RAG | FastEmbed, ChromaDB, pypdf |
| Persistence | SQLAlchemy, SQLite by default |
| Frontend | Next.js App Router, React, TypeScript, Tailwind CSS |
| Streaming | Server-Sent Events |
| Testing | pytest, FastAPI TestClient, FakeLLM |
| Deployment | Docker, Docker Compose, Render Blueprint, Vercel |

## Quick start

### Docker Compose

Requirements: Docker Desktop with Compose v2 and Python 3.11+ for the smoke test.

```powershell
Copy-Item .env.example .env
docker compose up --build --detach
python scripts/smoke_test.py http://localhost:8000
```

Open `http://localhost:3000`. The three sample claims use pre-seeded offline replays and do not
require provider keys.

```powershell
docker compose logs --follow backend
docker compose down
```

### Run from source

Backend:

```powershell
Copy-Item .env.example .env
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn veriagent.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend, in a second terminal:

```powershell
Set-Location frontend
npm ci
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
npm run dev
```

Run checks from the repository root:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests eval
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m eval.run_eval --mode replay
```

Upload a curated document and run a corpus ablation evaluation:

```powershell
curl.exe -X POST http://localhost:8000/api/corpus -F "file=@.\corpus\evidence.pdf" -F "title=Reviewed evidence"
Set-Location backend
.\.venv\Scripts\python.exe -m eval.run_eval --mode record --compare-corpus
```

Replay-mode corpus comparisons use separately recorded artifacts under
`backend/eval/dataset/replays/with-corpus/` and `without-corpus/`.

See [DEPLOYMENT.md](DEPLOYMENT.md) for Render and Vercel instructions and the complete environment
variable list.

## Evaluation results

The replay evaluation is regression-gated in pull requests. Replace the placeholders below with
results from the reviewed dataset and record the dataset version with each update.

| Metric | Result | Dataset/version |
|---|---:|---|
| Retrieval precision | `TBD` | `TBD` |
| Citation validity | `TBD` | `TBD` |
| Classification accuracy | `TBD` | `TBD` |
| Unsupported-claim rate | `TBD` | `TBD` |
| Exact human-verdict agreement | `TBD` | `TBD` |
| Adjacent human-verdict agreement | `TBD` | `TBD` |

Evaluation reports are written to `backend/eval/reports/` as JSON and Markdown. The confusion
matrix and per-claim results are included in each report.

## Limitations and honest caveats

- Retrieval coverage depends on public search endpoints, source availability, and page parsing.
- PDF ingestion extracts embedded text but does not perform OCR on scanned pages.
- The local Chroma index is single-node storage and must fit the deployment's memory and disk
  limits.
- A verified quote proves that text appears in a stored snapshot; it does not prove that the
  source is correct or that the quote entails the claim.
- Model-generated decomposition, evidence classification, and synthesis can still be wrong.
- Source ranking uses heuristics and cannot fully measure expertise, independence, or conflicts
  of interest.
- The current rate limiter is in memory and is not shared across multiple API instances.
- SQLite is suitable for local use and a stateless demo, but not for durable multi-instance
  production deployment.
- Free hosting can introduce cold starts, ephemeral storage, and external API limits.
- The seeded demo reports are fixed examples, not fresh investigations.
- The public API has no user accounts or authorization layer. Do not store sensitive claims.

VeriAgent is a research tool, not a substitute for professional medical, legal, financial, or
safety advice.

## Roadmap

- Expand the reviewed evaluation dataset across domains and verdict classes.
- Add durable PostgreSQL persistence and database migrations.
- Add authentication, per-user quotas, and distributed rate limiting.
- Improve domain provenance, publication-family detection, and source independence scoring.
- Add stronger entailment checks alongside deterministic quote matching.
- Support resumable runs and queued workers for longer investigations.
- Add export formats and shareable, versioned reports.
- Add deployment monitoring, structured traces, and cost reporting.
