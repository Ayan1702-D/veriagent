# Operator checklist

These steps require account access, credentials, human review, or screen recording and therefore
cannot be completed from the repository alone.

## 1. Choose and configure a model provider

The simplest path is Gemini because the checked-in defaults use Gemini model IDs.

1. Open [Google AI Studio](https://aistudio.google.com/apikey) and create an API key.
2. Use a current Auth key rather than a legacy unrestricted Standard key. See Google's
   [API-key guidance](https://ai.google.dev/gemini-api/docs/api-key).
3. Confirm the configured model IDs still appear in the official
   [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models).
4. Store the key only as `GEMINI_API_KEY` in local `.env` and Render's Environment page.

The current defaults are:

```dotenv
CHEAP_MODEL=gemini/gemini-3.5-flash-lite
STRONG_MODEL=gemini/gemini-3.8-flash
```

Alternatives require both a key and compatible LiteLLM model identifiers:

- [Groq key setup](https://console.groq.com/docs/quickstart) and
  [current production models](https://console.groq.com/docs/models)
- [OpenRouter developer portal](https://openrouter.ai/developers) and
  [key documentation](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys)

Do not put any provider key in `NEXT_PUBLIC_*`, Git, `render.yaml`, or `vercel.json`.

## 2. Configure local development

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`, replace the selected provider placeholder, and leave unused provider keys blank.
Tavily is optional; create a key from the [Tavily dashboard](https://app.tavily.com/home) only if
you want that additional search provider.

Then run:

```powershell
docker compose up --build --detach
python scripts/smoke_test.py http://localhost:8000
```

On Windows, open Docker Desktop first and wait until its Linux engine reports that it is running.
The release audit validated the Compose file, but the local end-to-end container smoke could not be
completed because the installed Docker engine did not become available.

Open `http://localhost:3000`. Test one seeded example first, then one new claim. A new claim should
move past the planner only when the selected model key and model IDs are valid.

## 3. Build and review a real evaluation dataset

The checked-in dataset has one implementation-authored smoke case. Before publishing accuracy:

1. Expand `backend/eval/dataset/claims.jsonl` across domains and all five verdicts.
2. Have at least two people label each claim independently.
3. Record reviewer names or stable IDs, review dates, disagreements, and resolution rules in
   `docs/eval-report.md`.
4. Use source URLs and domains that reviewers actually checked.
5. Add reviewed PDF, TXT, or Markdown documents through `POST /api/corpus`.

With a configured provider and populated local corpus index:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m eval.run_eval --mode record --compare-corpus --no-regression-gate
.\.venv\Scripts\python.exe -m eval.run_eval --mode replay --compare-corpus --update-baseline
Set-Location ..
```

Inspect the generated JSON and Markdown before committing paired artifacts under
`backend/eval/dataset/replays/with-corpus/` and `without-corpus/`. Do not create an ablation by
copying the same replay into both directories.

## 4. Push the release candidate

Review `git diff`, exclude `.env`, databases, Chroma data, recordings you do not want public, and
temporary verification directories. Then commit and push to the GitHub remote:

```powershell
git add .
git status
git commit -m "Prepare VeriAgent release candidate"
git push origin main
```

In GitHub, open **Settings → Code security and analysis** and enable available secret scanning and
dependency alerts. GitHub documents this under
[Securing your repository](https://docs.github.com/en/code-security/getting-started/securing-your-repository).

## 5. Deploy the backend on Render

1. Open the [Render dashboard](https://dashboard.render.com/).
2. Choose **New → Blueprint**, connect the GitHub repository, and select `render.yaml`.
3. Enter `CORS_ORIGINS` as a JSON array containing the expected Vercel production origin.
4. Apply the Blueprint.
5. Under **veriagent-api → Environment**, add `GEMINI_API_KEY` or your chosen provider secret.
6. Verify `CHEAP_MODEL` and `STRONG_MODEL` match that provider.
7. Deploy and copy the assigned `https://...onrender.com` URL.

Render's official references are the [Blueprint specification](https://render.com/docs/blueprint-spec),
[environment-variable guide](https://render.com/docs/configure-environment-variables), and
[free-tier limits](https://render.com/docs/free).

## 6. Deploy the frontend on Vercel

1. Open [Vercel New Project](https://vercel.com/new) and import the GitHub repository.
2. Set the project root directory to `frontend`.
3. Under **Project → Settings → Environment Variables**, add
   `NEXT_PUBLIC_API_URL=<your Render origin>` for Production.
4. Deploy and copy the stable production `https://...vercel.app` URL.
5. Return to Render and replace `CORS_ORIGINS` with the exact Vercel origin, then redeploy the API.

Use Vercel's [project settings](https://vercel.com/docs/project-configuration/project-settings),
[environment-variable](https://vercel.com/docs/environment-variables), and
[deployment](https://vercel.com/docs/deployments) documentation if the dashboard layout changes.

## 7. Verify the live pair

Run the backend smoke test, allowing for a Render cold start:

```powershell
python scripts/smoke_test.py https://YOUR-API.onrender.com --timeout 180
```

Then open the Vercel site and submit the EV grid-mix sample. Confirm:

- the browser sends API requests to the Render origin;
- the run completes with `replay_of: "demo-ev-grid"`;
- token, search, and fetch usage remain zero;
- the timeline ends, the evidence table is populated, and the quote badge says verified;
- a fresh claim works only after the provider credential is configured.

No live URLs are stored in the repository today, so this check remains yours to perform. Record the
two final URLs in `docs/release-verification.md` after it passes.

## 8. Record the demo

Use Windows Snipping Tool screen recording, Clipchamp, OBS, or another recorder. Capture 60–90
seconds at a readable desktop width:

1. landing page and one example selection;
2. run page while the agent timeline advances;
3. budget meter;
4. evidence table and verified-quote badge;
5. final verdict, audit expansion, and Markdown copy action.

Export a compact GIF to `docs/assets/veriagent-demo.gif`, or commit an MP4 and update the README
link. Do not show API keys, dashboard environment variables, browser extensions, or personal tabs.

## 9. Re-check free-tier behavior before sharing

- Render free web services sleep after 15 idle minutes and lose local SQLite, uploaded corpus, and
  Chroma changes on spin-down or restart.
- Free Render Postgres expires after 30 days and is not durable production storage.
- Vercel Hobby is limited to personal, non-commercial use and pauses usage after limits are
  exhausted.

Review [Render free limits](https://render.com/docs/free) and the
[Vercel Hobby plan](https://vercel.com/docs/plans/hobby) each time you publish or demo the project.
