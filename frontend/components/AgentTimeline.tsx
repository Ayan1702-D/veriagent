import type { AuditEvent, RunStatus } from "@/lib/types";

const AGENTS = [
  ["planner", "Frame", "break the claim apart"],
  ["researcher", "Seek", "find independent sources"],
  ["extractor", "Quote", "lift exact evidence"],
  ["contradiction", "Cross-check", "map disagreements"],
  ["verifier", "Verify", "test quote support"],
  ["reporter", "Conclude", "calibrate the verdict"],
] as const;

export function AgentTimeline({ events, status }: { events: AuditEvent[]; status: RunStatus }) {
  const seen = new Set(events.map((event) => event.node));
  const lastAgent = [...events].reverse().find((event) => AGENTS.some(([id]) => id === event.node))?.node;

  return (
    <section className="timeline-panel" aria-labelledby="timeline-title">
      <div className="section-kicker"><span>Live fieldwork</span><span>{events.length} signals</span></div>
      <h2 id="timeline-title">Agent relay</h2>
      <ol className="agent-timeline">
        {AGENTS.map(([id, label, description], index) => {
          const complete = seen.has(id);
          const active = status === "running" && lastAgent === id;
          return (
            <li key={id} className={active ? "active" : complete ? "complete" : "pending"}>
              <div className="agent-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</div>
              <div>
                <strong>{label}</strong>
                <span>{description}</span>
              </div>
              <span className="agent-state">
                <span className="sr-only">{active ? "Active" : complete ? "Complete" : "Waiting"}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
