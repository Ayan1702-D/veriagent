import type { Finding } from "@/lib/types";
import { VerdictBadge } from "./VerdictBadge";

function EvidenceLinks({ ids, empty }: { ids: string[]; empty: string }) {
  if (ids.length === 0) return <span className="muted-cell">{empty}</span>;
  return (
    <div className="evidence-links">
      <strong>{ids.length} linked {ids.length === 1 ? "quote" : "quotes"}</strong>
      <span>{ids.slice(0, 2).map((id) => `#${id.slice(0, 7)}`).join(" · ")}</span>
    </div>
  );
}

export function EvidenceTable({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <div className="empty-state">No atomic findings were produced for this run.</div>;
  }

  return (
    <div className="evidence-table-wrap">
      <table className="evidence-table">
        <thead>
          <tr>
            <th scope="col">Claim</th>
            <th scope="col">Supporting</th>
            <th scope="col">Contradicting</th>
            <th scope="col">Conclusion</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((finding) => (
            <tr key={finding.subclaim_id}>
              <th scope="row">
                {finding.subclaim_id}
                {finding.gaps.length > 0 && <small>{finding.gaps[0]}</small>}
              </th>
              <td><EvidenceLinks ids={finding.supporting} empty="No linked support" /></td>
              <td><EvidenceLinks ids={finding.contradicting} empty="No contradiction" /></td>
              <td>
                <VerdictBadge verdict={finding.verdict} compact />
                <small>{Math.round(finding.confidence * 100)}% confidence</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
