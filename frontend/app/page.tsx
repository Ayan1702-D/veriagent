import { ClaimForm } from "@/components/ClaimForm";
import { VerdictBadge } from "@/components/VerdictBadge";
import type { Verdict } from "@/lib/types";

const LEGEND: [Verdict, string][] = [
  ["SUPPORTED", "verified evidence agrees"],
  ["REFUTED", "verified evidence contradicts"],
  ["MIXED", "credible sources disagree"],
  ["CONDITIONAL", "true only under stated conditions"],
  ["INSUFFICIENT", "not enough verified evidence"],
];

export default function Home() {
  return (
    <main id="main-content" className="page-shell home-page">
      <section className="home-intro">
        <div>
          <span className="eyebrow">Case intake</span>
          <h1>State a claim. <mark>See the evidence.</mark></h1>
          <p>VeriAgent plans, searches, quotes, cross-checks, and reports. When the evidence is split or thin, it says so instead of forcing true or false.</p>
        </div>
        <aside className="sample-panel" aria-label="Sample claims">
          <span className="eyebrow">Sample claims</span>
          <p>Select a filing below to place it in the claim ledger.</p>
        </aside>
      </section>
      <div className="home-grid">
        <ClaimForm />
        <aside className="verdict-legend" aria-labelledby="verdict-legend-title">
          <h2 id="verdict-legend-title" className="eyebrow">Possible verdicts</h2>
          {LEGEND.map(([verdict, description]) => (
            <div key={verdict}><VerdictBadge verdict={verdict} compact /><span>{description}</span></div>
          ))}
          <p>Reports evidence and uncertainty. Not a guarantee of truth.</p>
        </aside>
      </div>
    </main>
  );
}
