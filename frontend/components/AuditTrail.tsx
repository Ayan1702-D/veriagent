import Link from "next/link";
import type { AuditEvent } from "@/lib/types";

export function AuditTrail({ events, runId, running = false }: { events: AuditEvent[]; runId?: string; running?: boolean }) {
  const tail = events.slice(-3);
  return <section className="audit-tail" aria-label="Latest audit events" aria-live="polite">
    {tail.length ? tail.map((event, index) => <div key={event.seq}>
      <time dateTime={event.ts}>{new Date(event.ts).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" })}</time>
      <strong>{event.node}</strong><span>{event.type.replaceAll("_", " ")}</span>
      {running && index === tail.length - 1 && <i className="audit-cursor" aria-hidden="true" />}
    </div>) : <p>Waiting for the first audit event{running ? <i className="audit-cursor" aria-hidden="true" /> : "."}</p>}
    {runId && <Link href={`/runs/${runId}/audit`}>Open full audit →</Link>}
  </section>;
}
