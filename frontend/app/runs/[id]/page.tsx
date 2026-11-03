"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AgentTimeline } from "@/components/AgentTimeline";
import { AuditTrail } from "@/components/AuditTrail";
import { BudgetMeter } from "@/components/BudgetMeter";
import { ReportView } from "@/components/ReportView";
import { getAudit, getRun } from "@/lib/api";
import { subscribeToRun } from "@/lib/sse";
import type { AuditEvent, BudgetUsage, RunResponse } from "@/lib/types";

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<RunResponse | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [usage, setUsage] = useState<BudgetUsage>({});
  const [connection, setConnection] = useState("connecting");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    const [nextRun, audit] = await Promise.all([getRun(id), getAudit(id)]);
    setRun(nextRun); setUsage(nextRun.budget_usage); setError(null);
    setEvents((current) => [...new Map([...audit.events, ...current].map((event) => [event.seq, event])).values()].sort((a, b) => a.seq - b.seq));
  }, [id]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      refresh().catch((caught) => setError(caught instanceof Error ? caught.message : "Case unavailable.")).finally(() => setLoading(false));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  useEffect(() => subscribeToRun(id, {
    onAudit: ({ event, budget_usage }) => { setEvents((current) => current.some((item) => item.seq === event.seq) ? current : [...current, event].sort((a, b) => a.seq - b.seq)); setUsage(budget_usage); },
    onEnd: ({ budget_usage }) => { setUsage(budget_usage); setConnection("ended"); refresh().catch(() => setError("The final report could not be loaded.")); },
    onState: setConnection, onError: setError,
  }), [id, refresh]);
  const verified = useMemo(() => events.some((event) => event.type === "extraction_completed" && Number(event.payload.verified_quotes_count ?? 0) > 0), [events]);
  const exhausted = events.some((event) => event.type === "budget_exhausted");

  if (loading) return <main id="main-content" className="page-shell loading-block">Opening case ledger…</main>;
  if (!run) return <main id="main-content" className="page-shell fatal-state"><h1>Case unavailable</h1><p>{error}</p><Link href="/">Return home</Link></main>;
  return <main id="main-content" className="page-shell run-page">
    <div className="run-meta">RUN {run.run_id.slice(0, 4).toUpperCase()} · {run.replay_of ? "REPLAY" : "LIVE DATA"} · {connection}</div>
    {error && <div className="inline-alert" role="alert">{error} <button onClick={() => refresh().catch(() => setError("Refresh failed. Please try again."))}>Retry</button></div>}
    {exhausted && <div className="partial-banner">Stopped early · the report uses partial evidence because the run budget was exhausted.</div>}
    <div className="run-ledger-grid">
      <aside className="case-rail">
        <span className="eyebrow">Claim under investigation</span>
        <h1>{run.claim.text}</h1>
        <AgentTimeline events={events} status={run.status} />
        <BudgetMeter budget={run.budget} usage={usage} />
      </aside>
      <section className="case-body">
        {run.status === "failed" && <div className="fatal-state compact"><h2>Run failed</h2><p>{run.error ?? "The investigation stopped unexpectedly."}</p></div>}
        {run.report ? <ReportView report={run.report} hasVerifiedQuotes={verified} /> : run.status !== "failed" ? <section className="pending-report" aria-live="polite"><span className="eyebrow">Overall verdict</span><h2>{run.status === "completed" ? "No report available" : "Evidence review in progress"}</h2><p>Findings appear here when the investigation finishes.</p></section> : null}
        <AuditTrail events={events} runId={run.run_id} running={run.status === "running"} />
      </section>
    </div>
  </main>;
}
