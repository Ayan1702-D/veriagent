# Release verification — 2026-11-01

## Clean-clone checks

The release candidate was committed only inside a temporary snapshot and cloned again for the
check; the project branch history was not changed.

| Check | Result |
|---|---|
| `make lint` | Passed: Ruff, formatting, and mypy; 59 source files typed |
| `make test` | Passed: 57 tests |
| `make eval` | Passed: deterministic n=1 replay and 0.02 regression gate |

On the managed Windows runner, pytest's system temporary directory was inaccessible, so `TEMP` and
`TMP` were pointed to a writable directory inside the clean clone. No product code was changed for
that runner restriction.

## Security checks

- SSRF rejection passed for direct loopback, cloud metadata, and DNS names resolving to restricted
  addresses.
- Production CORS rejects wildcard, HTTP, localhost, path, query, and fragment origins; the
  configured frontend origin receives the expected preflight header.
- The in-memory per-IP limiter returned HTTP 429 with the standard error envelope and
  `Retry-After` header.
- Every reachable Git revision was scanned for high-confidence OpenAI, Groq, OpenRouter, Tavily,
  Google, GitHub, AWS, and private-key formats. No matches were found. `.env.example` is the only
  tracked environment file.

This is a focused format scan, not a substitute for a repository secret-scanning service.

## Behavioral checks without provider credentials

The three seeded claims completed offline and replayed the expected reports:

| Claim | Verdict |
|---|---|
| EV lifetime emissions regardless of grid mix | `CONDITIONAL` |
| Remote work always improves software productivity | `MIXED` |
| Coffee after 2 PM always disrupts sleep | `REFUTED` |

Eight unrecorded claims, including an India EV-lifecycle claim, all terminated at the planner with
`LLM call failed after 3 attempts for node='planner'`. Fresh research therefore requires a valid
model-provider credential. The fallback covers only the three exact seeded claims.

## Items not verified

- No production Render or Vercel URLs are configured in the repository, so a live frontend-to-live
  backend request was not possible.
- The paired replay artifacts required for a with/without-curated-corpus ablation are absent.
- No model-provider credential is available in the verification environment, so those artifacts
  could not be recorded honestly.
- A 60–90 second product recording has not been captured.
