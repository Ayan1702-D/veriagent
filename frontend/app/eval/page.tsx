"use client";

import { useEffect, useState } from "react";
import { getLatestEval } from "@/lib/api";
import type { EvalMetrics } from "@/lib/types";

const TILES = [
  ["evidence_precision", "Retrieval precision"],
  ["citation_validity", "Citation validity"],
  ["claim_accuracy", "Classification accuracy"],
  ["unsupported_claim_rate", "Unsupported-claim rate (lower is better)"],
  ["human_agreement", "Human agreement"],
] as const;

export default function EvalPage() {
  const [metrics, setMetrics] = useState<EvalMetrics | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    getLatestEval().then((data) => { if (active) setMetrics(data); })
      .catch(() => { if (active) setError("The evaluation report is not available from the server."); });
    return () => { active = false; };
  }, [attempt]);
  return <main id="main-content" className="page-shell eval-page">
    <header className="page-heading"><div><span className="eyebrow">Evaluation</span><h1>How good is it, really?</h1></div></header>
    {error ? <section className="empty-state"><p>{error}</p><p>No scores are shown until measured results are available.</p><button type="button" onClick={() => { setError(""); setAttempt((value) => value + 1); }}>Try again</button></section>
      : !metrics ? <p role="status">Loading evaluation report…</p>
      : <><p>{metrics.dataset_size} cases in the reported dataset. Review methodology alongside the scores.</p>
        <section className="metric-grid" aria-label="Evaluation metrics">{TILES.map(([key, label]) => {
          const value = metrics[key];
          const valid = Number.isFinite(value) && value >= 0 && value <= 1;
          return <article key={key}><h2>{label}</h2><strong>{valid ? value.toFixed(2) : "—"}</strong><small>{valid ? "Reported result" : "Not reported"}</small>{valid && <div className="metric-gauge"><i style={{ width: value * 100 + "%" }} /></div>}</article>;
        })}</section>
        <p className="budget-note">Baseline comparisons and the confusion matrix are unavailable in this API response.</p>
      </>}
  </main>;
}
