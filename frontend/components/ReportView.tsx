"use client";

import { useState } from "react";
import type { Report } from "@/lib/types";
import { EvidenceTable } from "./EvidenceTable";
import { SourceCard } from "./SourceCard";
import { VerdictBadge } from "./VerdictBadge";

function toMarkdown(report: Report): string {
  const findings = report.findings.map((finding) =>
    `### ${finding.subclaim_id}\n\n- Verdict: **${finding.verdict}**\n- Confidence: ${Math.round(finding.confidence * 100)}%\n- Gaps: ${finding.gaps.join("; ") || "None recorded"}`,
  ).join("\n\n");
  const sources = report.citations.map((source, index) =>
    `${index + 1}. [${source.title || source.domain}](${source.url})`,
  ).join("\n");
  const limitations = report.limitations.map((item) => `- ${item}`).join("\n");
  return `# VeriAgent report\n\n> ${report.claim.text}\n\n**Verdict: ${report.verdict}**\n\n## Findings\n\n${findings || "No findings."}\n\n## Limitations\n\n${limitations || "None recorded."}\n\n## Sources\n\n${sources || "No sources cited."}`;
}

export function ReportView({ report, hasVerifiedQuotes = false }: { report: Report; hasVerifiedQuotes?: boolean }) {
  const [copied, setCopied] = useState(false);

  async function copyReport() {
    await navigator.clipboard.writeText(toMarkdown(report));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <article className="report-view">
      <header className="report-hero">
        <div className="report-ident"><span>Memorandum VA–R</span><span>Final disposition</span></div>
        <div className="report-verdict">
          <span className="eyebrow">Calibrated conclusion</span>
          <h2>Finding</h2>
          <VerdictBadge verdict={report.verdict} />
        </div>
        <button className="copy-button" type="button" onClick={copyReport} aria-live="polite">
          {copied ? "Copied ✓" : "Copy as Markdown"}
        </button>
      </header>

      <section className="report-section" aria-labelledby="evidence-title">
        <div className="report-heading-row">
          <div><span className="eyebrow">Claim matrix</span><h3 id="evidence-title">Evidence map</h3></div>
          <span className="count-stamp">{report.findings.length} findings</span>
        </div>
        <EvidenceTable findings={report.findings} />
      </section>

      <section className="report-section" aria-labelledby="sources-title">
        <div className="report-heading-row">
          <div><span className="eyebrow">Receipts</span><h3 id="sources-title">Cited sources</h3></div>
          <span className="count-stamp">{report.citations.length} sources</span>
        </div>
        {report.citations.length > 0 ? (
          <div className="source-grid">
            {report.citations.map((source) => <SourceCard key={source.id} source={source} verifiedQuote={hasVerifiedQuotes} />)}
          </div>
        ) : <div className="empty-state">No sources were cited in this report.</div>}
      </section>

      <section className="limitations" aria-labelledby="limitations-title">
        <span className="eyebrow">Read with care</span>
        <h3 id="limitations-title">Limitations</h3>
        {report.limitations.length > 0 ? (
          <ul>{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        ) : <p>No material limitations were recorded.</p>}
      </section>
    </article>
  );
}
