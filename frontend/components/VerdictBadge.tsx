import type { Verdict } from "@/lib/types";

const LABELS: Record<Verdict, string> = {
  SUPPORTED: "Supported",
  REFUTED: "Refuted",
  MIXED: "Mixed evidence",
  CONDITIONAL: "Conditional",
  INSUFFICIENT: "Insufficient",
};

export function VerdictBadge({ verdict, compact = false }: { verdict: Verdict; compact?: boolean }) {
  return (
    <span className={`verdict verdict-${verdict.toLowerCase()} ${compact ? "verdict-compact" : ""}`}>
      <span className="verdict-dot" aria-hidden="true" />
      <span className="sr-only">Verdict: </span>
      {LABELS[verdict]}
    </span>
  );
}
