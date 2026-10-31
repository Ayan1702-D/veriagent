import type { BudgetUsage, RunBudget } from "@/lib/types";

const METERS = [
  ["tokens", "Tokens", "max_llm_tokens"],
  ["searches", "Searches", "max_searches"],
  ["fetches", "Fetches", "max_fetches"],
  ["loops", "Loops", "max_loops"],
] as const;

export function BudgetMeter({ budget, usage }: { budget: RunBudget; usage: BudgetUsage }) {
  return (
    <section className="budget-panel" aria-labelledby="budget-title">
      <div className="section-kicker"><span>Guardrails</span><span>Hard limits</span></div>
      <h2 id="budget-title">Run budget</h2>
      <div className="budget-list">
        {METERS.map(([usageKey, label, budgetKey]) => {
          const used = usage[usageKey] ?? 0;
          const maximum = budget[budgetKey];
          const percent = maximum === 0 ? 0 : Math.min(100, (used / maximum) * 100);
          return (
            <div className="budget-row" key={usageKey}>
              <div><span>{label}</span><span>{used.toLocaleString()} / {maximum.toLocaleString()}</span></div>
              <div
                className="meter-track"
                role="progressbar"
                aria-label={`${label} budget used`}
                aria-valuemin={0}
                aria-valuemax={maximum}
                aria-valuenow={used}
              >
                <span style={{ width: `${percent}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
