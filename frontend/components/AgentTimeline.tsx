import type { AuditEvent, RunStatus } from "@/lib/types";

const NODES = [
  ["planner", "Planner"], ["researcher", "Researcher"], ["extractor", "Extractor"],
  ["contradiction", "Contradiction"], ["verifier", "Verifier"], ["reporter", "Report"],
] as const;

function summary(node: string, events: AuditEvent[]): string {
  const event = [...events].reverse().find((item) => item.node === node);
  if (!event) return "waiting";
  const p = event.payload;
  if (node === "planner") return `${p.subquestions_count ?? p.subclaims_count ?? "—"} subclaims · qualifiers found`;
  if (node === "researcher") return `${p.total_sources ?? "—"} sources · snapshots stored`;
  if (node === "extractor") return `${p.extracted_count ?? "—"} quotes · ${p.verified_quotes_count ?? "—"} verified`;
  if (node === "contradiction") return `${p.findings_count ?? "—"} findings · gaps checked`;
  if (node === "verifier") return `${p.counter_queries_added ?? 0} counter-queries added`;
  if (node === "reporter") return `verdict · ${String(p.verdict ?? "complete").toLowerCase()}`;
  return event.type.replaceAll("_", " ");
}

export function AgentTimeline({ events, status }: { events: AuditEvent[]; status: RunStatus }) {
  const seen = new Set(events.map((event) => event.node));
  const lastNode = [...events].reverse().find((event) => NODES.some(([id]) => id === event.node))?.node;
  const loop = [...events].reverse().find((event) => event.type === "loop_back");
  return (
    <section aria-labelledby="timeline-title">
      <h2 id="timeline-title" className="eyebrow">Pipeline</h2>
      <ol className="agent-timeline" aria-live="polite">
        {NODES.map(([id, label], index) => {
          const active = status === "running" && lastNode === id;
          const done = seen.has(id) && !active;
          return <li key={id} className={active ? "live" : done ? "done" : "queued"}>
            <span className="node-dot" aria-hidden="true" />
            <div><strong>{String(index + 1).padStart(2, "0")} {label}</strong><small>{summary(id, events)}</small></div>
          </li>;
        })}
      </ol>
      {loop && <p className="loop-note">Loop {String(loop.payload.loop_count ?? "—")} · {String(loop.payload.reason ?? "evidence gap")}</p>}
    </section>
  );
}
