# VeriAgent free-tier deployment

This setup uses a Docker-based Render web service for the API and Vercel for the
Next.js frontend. The three claims shown on the landing page are pre-seeded and
automatically run in offline replay mode. They do not require an LLM key, a search
provider, or outbound network access.

## 1. Run the production-shaped stack locally

Prerequisites: Docker Desktop with Compose v2 and Python 3.11+ for the smoke test.

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose config
docker compose up --build --detach
docker compose ps
python scripts/smoke_test.py http://localhost:8000
```

Open `http://localhost:3000`. To inspect or stop the stack:

```powershell
docker compose logs --follow backend
docker compose down
```

Use `docker compose down --volumes` only when you intentionally want to delete the
local SQLite data and npm dependency volumes.

## 2. Deploy the Docker backend to Render

The root [render.yaml](render.yaml) is a Render Blueprint using the free Docker web
service plan. Render expects the service to bind to `0.0.0.0`; the image reads its
assigned `PORT` automatically and exposes `/health` for platform health checks.

First push this repository to GitHub:

```powershell
git add backend/Dockerfile backend/.dockerignore docker-compose.yml render.yaml DEPLOYMENT.md scripts/smoke_test.py
git add backend/src/veriagent/config.py backend/src/veriagent/demo.py backend/src/veriagent/main.py backend/src/veriagent/api/routes_runs.py
git add backend/tests/unit/test_l9_deployment.py frontend/vercel.json .env.example Makefile STATE.md
git commit -m "Prepare free-tier deployment"
git push origin HEAD
```

Then:

1. In Render, choose **New → Blueprint** and connect the repository.
2. Keep `render.yaml` as the Blueprint path.
3. For the prompted `CORS_ORIGINS` value, enter a JSON array containing the expected
   Vercel production origin, for example `["https://veriagent.vercel.app"]`.
4. Apply the Blueprint and wait for `/health` to become healthy.
5. Copy the assigned URL, such as `https://veriagent-api.onrender.com`.

Optional live-provider secrets can be added under **Service → Environment** and then
deployed again. The seeded demonstrations work without them.

Render free web services use an ephemeral filesystem and spin down after inactivity.
Consequently, non-demo SQLite runs can disappear after a restart, while the demo runs
are recreated automatically on every startup. This is intentional for the free demo;
use managed PostgreSQL for durable production history. See the official
[Render free-tier limitations](https://render.com/docs/free) and
[Blueprint reference](https://render.com/docs/blueprint-spec).

## 3. Deploy the frontend to Vercel

Run these commands from the repository root, replacing the URL with the Render URL:

```powershell
Set-Location frontend
npx vercel@latest link
npx vercel@latest env add NEXT_PUBLIC_API_URL production
npx vercel@latest deploy --prod
Set-Location ..
```

When `vercel env add` prompts for a value, enter the backend origin only, for example
`https://veriagent-api.onrender.com` with no trailing slash. The project root should
be `frontend`; `frontend/vercel.json` selects Next.js and the production build.

If Vercel assigns a different production domain than the one entered on Render,
replace `CORS_ORIGINS` in Render with the exact origin and redeploy the backend. Do
not use `*`. Preview deployments need their own exact origin added to the JSON array.
Vercel documents both [monorepo root directories](https://vercel.com/docs/monorepos)
and [CLI deployments](https://vercel.com/docs/projects/deploy-from-cli).

## 4. Verify the deployed pair

The first request can take about a minute while a free Render service wakes up:

```powershell
python scripts/smoke_test.py https://veriagent-api.onrender.com --timeout 180
```

Expected output:

```text
SMOKE TEST PASSED: health ok; replay <run-id> completed
```

Then visit the Vercel URL and submit any of the three sample filings. Its run response
will contain `replay_of` with one of the `demo-*` source IDs and zero network/LLM usage.

## Environment variables

| Variable | Where | Secret? | Required | Purpose |
|---|---|---:|---:|---|
| `APP_ENV=production` | Render | No | Yes | Enables strict production validation. |
| `DATABASE_URL` | Render | Usually | Yes | SQLite is non-secret in the Blueprint; managed database URLs are secrets. |
| `CORS_ORIGINS` | Render | No | Yes | JSON array of exact HTTPS frontend origins. Wildcards and localhost are rejected in production. |
| `RATE_LIMIT_REQUESTS` | Render | No | Yes | Per-IP requests allowed in each window; default `30`. |
| `RATE_LIMIT_WINDOW_SECONDS` | Render | No | Yes | Rate-limit window; default `60`. |
| `MAX_LLM_TOKENS` | Render | No | Yes | Per-run cap; production value `6000`. |
| `MAX_SEARCHES` | Render | No | Yes | Per-run search cap; production value `4`. |
| `MAX_FETCHES` | Render | No | Yes | Per-run fetch cap; production value `6`. |
| `MAX_LOOPS` | Render | No | Yes | Research retry cap; production value `1`. |
| `MAX_SECONDS` | Render | No | Yes | Run wall-time cap; production value `45`. |
| `QUOTE_MATCH_THRESHOLD` | Render | No | No | Quote verification threshold; default `85`. |
| `DEMO_REPLAY_ENABLED` | Render | No | Yes | Seeds and auto-replays the three landing-page examples. |
| `CORPUS_ENABLED` | Render | No | No | Enables curated corpus upload and retrieval. |
| `CORPUS_DIR` | Render | No | No | Uploaded document directory; `/app/corpus` in the container. |
| `CHROMA_PATH` | Render | No | No | Local Chroma persistence directory. |
| `CORPUS_EMBEDDING_MODEL` | Render | No | No | FastEmbed model identifier. |
| `CORPUS_MAX_DOCUMENT_BYTES` | Render | No | No | Per-upload size cap; default 10 MiB. |
| `CORPUS_CHUNK_SIZE`, `CORPUS_CHUNK_OVERLAP` | Render | No | No | Character chunking controls. |
| `CORPUS_TOP_K` | Render | No | No | Curated chunks returned per search. |
| `CHEAP_MODEL`, `STRONG_MODEL` | Render | No | Live only | LiteLLM model identifiers. |
| `GEMINI_API_KEY` | Render | **Yes** | Live only | Gemini credential. |
| `GROQ_API_KEY` | Render | **Yes** | Live only | Groq credential. |
| `OPENROUTER_API_KEY` | Render | **Yes** | Live only | OpenRouter credential. |
| `TAVILY_API_KEY` | Render | **Yes** | No | Enables Tavily search. |
| `OPENALEX_MAILTO` | Render | Personal | No | Contact address for polite OpenAlex usage. |
| `NEXT_PUBLIC_API_URL` | Vercel | No, public | Yes | Browser-visible Render API origin. |

Never put provider keys in `NEXT_PUBLIC_*` variables, `render.yaml`, `vercel.json`, or
the Docker image. `NEXT_PUBLIC_API_URL` is intentionally public and is embedded in the
frontend build.

Corpus files and the embedded Chroma index are also ephemeral on the Render free plan. Use a
persistent Chroma service or durable disk before relying on curated uploads in production.
