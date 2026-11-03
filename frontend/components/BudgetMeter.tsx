import type { BudgetUsage, RunBudget } from "@/lib/types";

export function BudgetMeter({ budget, usage }: { budget: RunBudget; usage: BudgetUsage }) {
  const incoming = {
    tokens: usage.tokens ?? 0,
    searches: usage.searches ?? 0,
    seconds: usage.seconds ?? 0,
  };
  const meters = [
    ["Tokens", incoming.tokens, budget.max_llm_tokens],
    ["Searches", incoming.searches, budget.max_searches],
    ["Time", Math.round(incoming.seconds), budget.max_seconds],
  ] as const;
  return <section className="budget-panel" aria-labelledby="budget-title">
    <h2 id="budget-title" className="eyebrow">Budget</h2>
    {meters.map(([label, used, maximum]) => {
      const percent = maximum ? Math.min(100, used / maximum * 100) : 0;
      return <div className={`budget-row ${percent >= 80 ? "warning" : ""}`} key={label}>
        <div><span>{label}</span><span>{used.toLocaleString()} / {maximum.toLocaleString()}{label === "Time" ? "s" : ""}</span></div>
        <div className="meter-track" role="progressbar" aria-label={`${label} used`} aria-valuemin={0} aria-valuemax={maximum} aria-valuenow={used}>
          <span style={{ width: `${percent}%` }} />
        </div>
      </div>;
    })}
  </section>;
}
