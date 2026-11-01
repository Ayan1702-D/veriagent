# Evaluation report

## Scope

The checked-in evaluation is a deterministic regression smoke test for the evaluation pipeline.
It is not large or diverse enough to measure VeriAgent's general fact-verification quality.

## Dataset construction

- Dataset: `backend/eval/dataset/claims.jsonl`
- Version: `smoke-v1`
- Size: 1 claim
- Domain: global electric-vehicle sales
- Verdict represented: `SUPPORTED`
- Expected source: the International Energy Agency's Global EV Outlook 2025
- Replay artifact: `backend/eval/dataset/replays/global-ev-sales-2024.json`

The claim and label were authored during implementation to exercise every metric and the replay
regression gate. The expected URL/domain points to the source represented in the stored replay.
The replay contains one source, one deterministically verified quote, one finding, and one verdict.

## Review status

No independent domain expert or second human annotator has reviewed the current label. The
`human_verdict` field records the implementation author's label and must not be described as an
independent human benchmark. Before publishing accuracy claims, add a documented review protocol,
at least two reviewers, disagreement resolution, and a materially larger multi-domain dataset.

## Results

Release verification on 2026-11-01 ran the replay from a clean clone.

| Metric | Result |
|---|---:|
| Retrieval precision | 1.000 |
| Citation validity | 1.000 |
| Classification accuracy | 1.000 |
| Unsupported-claim rate | 0.000 |
| Exact human-verdict agreement | 1.000 |
| Adjacent human-verdict agreement | 0.000 |

The confusion matrix contains one `SUPPORTED` prediction for one `SUPPORTED` label. These results
mean the recorded case is reproduced correctly. They do not establish expected performance on new
claims.

## Curated-corpus comparison

A valid with/without-corpus ablation was not produced. Replay mode requires paired artifacts under
`backend/eval/dataset/replays/with-corpus/` and
`backend/eval/dataset/replays/without-corpus/`; those artifacts do not exist. Live recording also
requires a configured model provider. The release check therefore retained the available
without-curated-corpus smoke result as `backend/eval/reports/baseline.json` and did not fabricate a
corpus comparison.

## Unseen-claim check

Eight bounded, previously unrecorded claims were submitted without provider credentials. Each
terminated with `LLM call failed after 3 attempts for node='planner'`. This confirms that fresh
research is unavailable without a model provider. Separately, all three seeded claims completed
offline through replay with `CONDITIONAL`, `MIXED`, and `REFUTED` verdicts.

## Next dataset milestone

Build a balanced set spanning all five verdict classes and several domains. Keep source snapshots
and expected URLs, have two people label each claim independently, record disagreements, and freeze
paired with/without-corpus artifacts before updating this report or presenting aggregate accuracy.
