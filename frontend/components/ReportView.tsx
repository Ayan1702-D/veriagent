"use client";

import { useState } from "react";
import type { Report } from "@/lib/types";
import { EvidenceTable } from "./EvidenceTable";
import { SourceCard } from "./SourceCard";
import { VerdictBadge } from "./VerdictBadge";

function markdown(report: Report): string {
  return `# VeriAgent report\n\n> ${report.claim.text}\n\n**Verdict: ${report.verdict}**\n\n${report.findings.map((f) => `## ${f.subclaim_id}\n\n- Verdict: ${f.verdict}\n- Confidence: ${Math.round(f.confidence * 100)}%`).join("\n\n")}\n\n## Limitations\n${report.limitations.map((item) => `- ${item}`).join("\n")}`;
}

export function ReportView({ report }: { report: Report; hasVerifiedQuotes?: boolean }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown(report) + "\n\n## Sources\n" + report.citations.map((source) => source.title + ": " + source.url).join("\n"));
      setCopied(true); setCopyError("");
    } catch { setCopyError("Copy unavailable. Select and copy the report text instead."); }
  }
  return <article className="report-view">
    <header className="verdict-summary">
      <VerdictBadge verdict={report.verdict} stamp />
      <div><span className="eyebrow">Overall verdict</span><p>{report.limitations[0] ?? "The conclusion reflects the verified evidence available in this run."}</p></div>
      <button type="button" onClick={copy}>{copied ? "Copied" : "Copy Markdown"}</button>
    </header>
    <EvidenceTable findings={report.findings} />
    {copyError && <p role="alert">{copyError}</p>}
    {report.limitations.length > 0 && <section className="source-register"><h3 className="eyebrow">Limitations</h3><ul>{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>}
    <section className="source-register">
      <h3 className="eyebrow">Cited sources · {report.citations.length}</h3>
      {report.citations.length ? report.citations.map((source) => <SourceCard key={source.id} source={source} />) : <p className="empty-state">No sources were cited.</p>}
    </section>
  </article>;
}
