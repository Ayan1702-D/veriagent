import type { Verdict } from "@/lib/types";

const LABELS: Record<Verdict, string> = {
  SUPPORTED: "Supported", REFUTED: "Refuted", MIXED: "Mixed",
  CONDITIONAL: "Conditional", INSUFFICIENT: "Insufficient",
};

export function VerdictBadge({ verdict, compact = false, stamp = false }: { verdict: Verdict; compact?: boolean; stamp?: boolean }) {
  return <span className={`verdict verdict-${verdict.toLowerCase()} ${compact ? "verdict-compact" : ""} ${stamp ? "verdict-stamp" : ""}`}>
    <span className="sr-only">Verdict: </span>{LABELS[verdict]}
  </span>;
}
