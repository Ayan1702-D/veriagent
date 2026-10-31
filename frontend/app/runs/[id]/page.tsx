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

type Connection = "connecting" | "live" | "reconnecting" | "ended";

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<RunResponse | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [usage, setUsage] = useState<BudgetUsage>({});
  const [connection, setConnection] = useState<Connection>("connecting");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextRun, audit] = await Promise.all([getRun(id), getAudit(id)]);
    setRun(nextRun);
    setUsage(nextRun.budget_usage);
    setEvents(audit.events);
  }, [id]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      refresh()
        .catch((caught) => active && setError(caught instanceof Error ? caught.message : "This run could not be loaded."))
        .finally(() => active && setLoading(false));
    }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [refresh]);

  useEffect(() => subscribeToRun(id, {
    onAudit: (payload) => {
      setEvents((current) => current.some((event) => event.seq === payload.event.seq)
        ? current : [...current, payload.event].sort((a, b) => a.seq - b.seq));
      setUsage(payload.budget_usage);
    },
    onEnd: (payload) => {
      setUsage(payload.budget_usage);
      setConnection("ended");
      refresh().catch((caught) => setError(caught instanceof Error ? caught.message : "The final report could not be loaded."));
    },
    onState: setConnection,
    onError: setError,
  }), [id, refresh]);

  const hasVerifiedQuotes = useMemo(() => events.some((event) =>
    event.type === "extraction_completed" && Number(event.payload.verified_quotes_count ?? 0) > 0,
  ), [events]);

  if (loading) return <main id="main-content" className="page-shell"><div className="loading-block"><span className="loading-pulse" /> Opening case file…</div></main>;
  if (error && !run) {
    return <main id="main-content" className="page-shell"><div className="fatal-state"><span>Case unavailable</span><h1>We lost the evidence trail.</h1><p>{error}</p><Link href="/">Start another claim</Link></div></main>;
  }
  if (!run) return null;

  return (
    <main id="main-content" className="run-page page-shell">
      <header className="case-header">
        <div>
          <div className="case-meta"><span>Case {run.run_id.slice(0, 8)}</span><span className={`connection connection-${connection}`}><i /> {connection}</span></div>
          <h1>{run.claim.text}</h1>
        </div>
        <div className={`status-stamp status-${run.status}`}><small>Run status</small><strong>{run.status}</strong></div>
      </header>
      {error && <div className="inline-alert" role="alert">Live update issue: {error}</div>}
      {run.status === "failed" && <div className="fatal-state compact"><span>Run failed</span><p>{run.error ?? "The investigation stopped unexpectedly."}</p></div>}
      <div className="run-instruments">
        <AgentTimeline events={events} status={run.status} />
        <BudgetMeter budget={run.budget} usage={usage} />
      </div>
      {run.report ? <ReportView report={run.report} hasVerifiedQuotes={hasVerifiedQuotes} /> : run.status !== "failed" ? (
        <section className="waiting-report" aria-live="polite">
          <span className="orbit-mark" aria-hidden="true"><i /><i /><i /></span>
          <div><span className="eyebrow">Agents at work</span><h2>The report is still taking shape.</h2><p>Evidence will settle here when the challenge and verification passes finish.</p></div>
        </section>
      ) : null}
      <AuditTrail events={events} />
    </main>
  );
}
