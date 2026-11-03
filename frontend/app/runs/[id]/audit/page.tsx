"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getAudit, replayRun } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

export default function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [node, setNode] = useState("all");
  const [type, setType] = useState("all");
  const [step, setStep] = useState(0);
  const [replayedId, setReplayedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replaying, setReplaying] = useState(false);
  useEffect(() => { getAudit(id).then(({ events: rows }) => { setEvents(rows); setSelected(rows.at(-1) ?? null); setStep(rows.length); }).catch((caught) => setError(caught instanceof Error ? caught.message : "Audit unavailable.")); }, [id]);
  const nodes = useMemo(() => [...new Set(events.map((event) => event.node))], [events]);
  const types = useMemo(() => [...new Set(events.map((event) => event.type))], [events]);
  const filtered = events.filter((event) => (node === "all" || event.node === node) && (type === "all" || event.type === type));

  async function replay() {
    if (replaying) return;
    setError(null); setReplaying(true);
    try {
      const accepted = await replayRun(id); setReplayedId(accepted.run_id);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Replay could not start."); }
    finally { setReplaying(false); }
  }

  return <main id="main-content" className="page-shell audit-page">
    <header className="page-heading"><span className="eyebrow">Audit trail</span><h1>Run {id.slice(0, 8)}, every step</h1><span>{events.length} recorded events</span></header>
    {error && <p className="inline-alert" role="alert">{error}</p>}
    <div className="audit-filters">
      <label>node <select value={node} onChange={(event) => setNode(event.target.value)}><option value="all">all</option>{nodes.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>type <select value={type} onChange={(event) => setType(event.target.value)}><option value="all">all</option>{types.map((item) => <option key={item}>{item}</option>)}</select></label>
    </div>
    <div className="audit-layout">
      <div className="audit-table-wrap">
        <table className="audit-table"><thead><tr><th>Seq</th><th>Time</th><th>Node</th><th>Type</th><th>Summary</th><th>Tok</th></tr></thead>
          <tbody>{filtered.map((event, index) => <tr key={event.seq} className={selected?.seq === event.seq ? "selected" : ""} style={{ animationDelay: `${index * .04}s` }} onClick={() => setSelected(event)}>
            <td><button type="button" onClick={() => setSelected(event)} aria-label={`Inspect event ${event.seq}`}>#{event.seq}</button></td><td>{new Date(event.ts).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" })}</td><td>{event.node}</td><td>{event.type}</td><td>{Object.values(event.payload).slice(0, 2).map(String).join(", ") || "—"}</td><td>{event.tokens}</td>
          </tr>)}</tbody>
        </table>
        {!filtered.length && <p className="empty-state">No events match these filters.</p>}
      </div>
      <aside className="audit-side">
        <section className="event-payload"><h2>Event {selected?.seq ?? "—"} payload</h2><pre>{selected ? JSON.stringify(selected, null, 2) : "Select an event"}</pre></section>
        <section className="replay-panel"><h2>Inspect stored events</h2><label>Step {step} of {events.length}<input type="range" min="0" max={events.length} value={step} disabled={!events.length} onChange={(event) => { const value = Number(event.target.value); setStep(value); setSelected(events[value - 1] ?? null); }} /></label><p>Replay creates a separate run from the stored report. Available for completed runs.</p><button type="button" disabled={replaying || !events.length} onClick={replay}>{replaying ? "Creating replay…" : "Replay run"}</button>{replayedId && <Link href={`/runs/${replayedId}`}>Open replayed run →</Link>}</section>
      </aside>
    </div>
  </main>;
}
