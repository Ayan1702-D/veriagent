import type { AuditEvent } from "@/lib/types";

function prettyType(type: string): string {
  return type.replaceAll("_", " ");
}

export function AuditTrail({ events }: { events: AuditEvent[] }) {
  return (
    <section className="audit-section" aria-labelledby="audit-title">
      <div className="report-heading-row">
        <div>
          <span className="eyebrow">Reproducibility log</span>
          <h2 id="audit-title">Audit trail</h2>
        </div>
        <span className="count-stamp">{events.length} events</span>
      </div>
      {events.length === 0 ? (
        <div className="empty-state">Audit signals will appear as agents begin work.</div>
      ) : (
        <div className="audit-list">
          {events.map((event) => (
            <details key={event.seq}>
              <summary>
                <span className="audit-seq">{String(event.seq).padStart(2, "0")}</span>
                <span><strong>{event.node}</strong><small>{prettyType(event.type)}</small></span>
                <time dateTime={event.ts}>{new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
              </summary>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
