"use client";

import { useEffect, useState } from "react";
import { getLatestEval } from "@/lib/api";
import type { EvalMetrics, Verdict } from "@/lib/types";

const PLACEHOLDER: EvalMetrics = {
  generated_at: new Date(0).toISOString(), dataset_size: 120, citation_validity: 0.96,
  claim_accuracy: 0.84, evidence_precision: 0.89, unsupported_claim_rate: 0.04,
  human_agreement: 0.87,
  verdict_distribution: { SUPPORTED: 31, REFUTED: 22, MIXED: 27, CONDITIONAL: 26, INSUFFICIENT: 14 },
};
const METRICS = [
  ["citation_validity", "Citation validity", "Quotes trace back to stored sources"],
  ["claim_accuracy", "Claim accuracy", "Verdicts match reviewed labels"],
  ["evidence_precision", "Evidence precision", "Retrieved evidence is relevant"],
  ["human_agreement", "Human agreement", "Alignment with expert reviewers"],
] as const;

export default function EvalPage() {
  const [metrics, setMetrics] = useState<EvalMetrics | null>(null);
  const [placeholder, setPlaceholder] = useState(false);
  useEffect(() => { getLatestEval().then(setMetrics).catch(() => { setMetrics(PLACEHOLDER); setPlaceholder(true); }); }, []);

  return (
    <main id="main-content" className="eval-page page-shell">
      <header className="eval-header">
        <div className="document-meta"><span>Document VA–02</span><span>Evaluation register</span><span>Latest accepted run</span></div>
        <span className="eyebrow">System calibration / quality control</span>
        <h1>Evaluation register</h1>
        <p>Measured performance across citation integrity, evidence retrieval, classification, and agreement with reviewed conclusions.</p>
      </header>
      {!metrics ? <div className="loading-block"><span className="loading-pulse" /> Loading the latest evaluation…</div> : <>
        {placeholder && <div className="data-note"><strong>Preview dataset</strong><span>The evaluation endpoint is not available yet, so this view uses representative placeholder data.</span></div>}
        <section className="metric-grid" aria-label="Evaluation metrics">
          {METRICS.map(([key, label, description]) => { const value = metrics[key]; return <article key={key}><span>{label}</span><strong>{Math.round(value * 100)}<small>%</small></strong><div className="metric-line"><i style={{ width: `${value * 100}%` }} /></div><p>{description}</p></article>; })}
          <article className="metric-negative"><span>Unsupported claim rate</span><strong>{Math.round(metrics.unsupported_claim_rate * 100)}<small>%</small></strong><div className="metric-line"><i style={{ width: `${metrics.unsupported_claim_rate * 100}%` }} /></div><p>Lower is better</p></article>
        </section>
        <section className="distribution" aria-labelledby="distribution-title">
          <div><span className="eyebrow">Dataset mix</span><h2 id="distribution-title">Verdict distribution</h2><p>{metrics.dataset_size} reviewed claims in the latest evaluation set.</p></div>
          <div className="distribution-bars">{(Object.entries(metrics.verdict_distribution) as [Verdict, number][]).map(([verdict, count]) => <div key={verdict}><span>{verdict.toLowerCase()}</span><div><i style={{ width: `${(count / metrics.dataset_size) * 100}%` }} /></div><strong>{count}</strong></div>)}</div>
        </section>
      </>}
    </main>
  );
}
