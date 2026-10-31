"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createRun } from "@/lib/api";

const EXAMPLES = [
  "Electric vehicles always produce fewer lifetime emissions, regardless of grid mix.",
  "Remote work makes software teams more productive than office work.",
  "Drinking coffee after 2 PM always disrupts nighttime sleep.",
];

export function ClaimForm() {
  const router = useRouter();
  const [claim, setClaim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = claim.trim();
    if (normalized.length < 3) {
      setError("Give us a complete claim to investigate.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const run = await createRun(normalized);
      router.push(`/runs/${run.run_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The investigation could not start.");
      setSubmitting(false);
    }
  }

  return (
    <div className="claim-console" id="claim-intake">
      <div className="console-label">
        <span>Form VA–01 / Claim intake</span>
        <span className="console-status"><i /> Desk open</span>
      </div>
      <form onSubmit={submit} aria-describedby={error ? "claim-error" : "claim-hint"}>
        <label htmlFor="claim"><span>01.</span> Statement under examination</label>
        <textarea
          id="claim"
          name="claim"
          rows={5}
          minLength={3}
          maxLength={2000}
          value={claim}
          onChange={(event) => setClaim(event.target.value)}
          placeholder="Enter one specific, checkable statement."
          disabled={submitting}
        />
        <div className="form-meta">
          <span id="claim-hint">Avoid questions. Include conditions such as “always” or “in India”.</span>
          <span>{claim.length} / 2,000</span>
        </div>
        {error && <p className="form-error" id="claim-error" role="alert">{error}</p>}
        <button className="primary-action" type="submit" disabled={submitting}>
          <span>{submitting ? "Registering case…" : "Register for examination"}</span>
          <span aria-hidden="true">→</span>
        </button>
      </form>

      <div className="example-claims">
        <p>Sample filings / select to copy</p>
        {EXAMPLES.map((example, index) => (
          <button type="button" key={example} onClick={() => setClaim(example)} disabled={submitting}>
            <span>[{String.fromCharCode(65 + index)}]</span>
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
