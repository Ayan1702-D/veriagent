"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { createRun } from "@/lib/api";

const EXAMPLES = [
  "Drinking coffee after 2 PM always disrupts nighttime sleep.",
  "Remote work makes software teams more productive than office work.",
  "Electric vehicles always produce fewer lifetime emissions, regardless of grid mix.",
];
const QUALIFIERS = /\b(always|never|all|regardless)\b/gi;

export function ClaimForm() {
  const router = useRouter();
  const [claim, setClaim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const qualifiers = useMemo(() => [...new Set(claim.match(QUALIFIERS)?.map((item) => item.toLowerCase()) ?? [])], [claim]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = claim.trim();
    if (normalized.length < 3) return setError("Enter one complete claim to investigate.");
    setSubmitting(true);
    setError(null);
    try {
      const run = await createRun(normalized);
      router.push(`/runs/${run.run_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The case could not be opened.");
      setSubmitting(false);
    }
  }

  return (
    <section className="claim-form-wrap" id="claim-intake">
      <form onSubmit={submit} aria-describedby={error ? "claim-error" : "claim-hint"}>
        <label className="eyebrow" htmlFor="claim">Claim</label>
        <textarea id="claim" required placeholder="Write one factual statement to investigate, or select an example." minLength={3} maxLength={2000} value={claim} onChange={(event) => { setClaim(event.target.value); setError(null); }} disabled={submitting} aria-invalid={Boolean(error)} aria-describedby="claim-hint" />
        <p className="qualifier-line" id="claim-hint">
          Qualifiers detected: {qualifiers.length ? qualifiers.map((word) => <mark key={word}>{word}</mark>) : <span>none</span>} · scope will be tested
        </p>
        <p className="budget-note">Each investigation uses the server’s research limits. Actual limits and usage appear in your run.</p>
        {error && <p className="form-error" id="claim-error" role="alert">{error}</p>}
        <div className="claim-actions">
          <button className="primary-action" type="submit" disabled={submitting || claim.trim().length < 3}>{submitting ? "Opening…" : "Open case"}</button>
          <span>Inspect the evidence behind each verdict</span>
        </div>
      </form>
      <div className="sample-slips" aria-label="Example claims">
        {EXAMPLES.map((example) => <button type="button" key={example} onClick={() => setClaim(example)} disabled={submitting}>{example}</button>)}
      </div>
    </section>
  );
}
