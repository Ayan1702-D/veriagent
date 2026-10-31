export type Verdict =
  | "SUPPORTED"
  | "REFUTED"
  | "MIXED"
  | "CONDITIONAL"
  | "INSUFFICIENT";

export type RunStatus = "queued" | "running" | "completed" | "failed";
export type Stance = "supports" | "contradicts" | "neutral";
export type SourceType = "primary" | "secondary" | "news" | "blog" | "curated";

export interface Claim {
  id: string;
  text: string;
  qualifiers: string[];
  atomic_subclaims: string[];
}

export interface RunBudget {
  max_llm_tokens: number;
  max_searches: number;
  max_fetches: number;
  max_loops: number;
  max_seconds: number;
}

export interface BudgetUsage {
  tokens?: number;
  searches?: number;
  fetches?: number;
  loops?: number;
  seconds?: number;
}

export interface Source {
  id: string;
  url: string;
  title: string;
  domain: string;
  fetched_at: string;
  snapshot_hash: string;
  rank_score: number;
  source_type: SourceType;
}

export interface Evidence {
  id: string;
  source_id: string;
  quote: string;
  date: string | null;
  stance: Stance;
  quote_verified: boolean;
  context_conditions: string[];
}

export interface Finding {
  subclaim_id: string;
  supporting: string[];
  contradicting: string[];
  gaps: string[];
  verdict: Verdict;
  confidence: number;
}

export interface Report {
  claim: Claim;
  findings: Finding[];
  verdict: Verdict;
  limitations: string[];
  citations: Source[];
}

export interface AuditEvent {
  run_id: string;
  seq: number;
  node: string;
  type: string;
  payload: Record<string, unknown>;
  tokens: number;
  ts: string;
}

export interface RunResponse {
  run_id: string;
  status: RunStatus;
  claim: Claim;
  budget: RunBudget;
  budget_usage: BudgetUsage;
  replay_of: string | null;
  report: Report | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditResponse {
  run_id: string;
  events: AuditEvent[];
}

export interface RunAcceptedResponse {
  run_id: string;
  status: "queued";
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

export interface StreamAuditPayload {
  event: AuditEvent;
  budget_usage: BudgetUsage;
}

export interface StreamEndPayload {
  run_id: string;
  status: RunStatus;
  budget_usage: BudgetUsage;
}

export interface EvalMetrics {
  generated_at: string;
  dataset_size: number;
  citation_validity: number;
  claim_accuracy: number;
  evidence_precision: number;
  unsupported_claim_rate: number;
  human_agreement: number;
  verdict_distribution: Partial<Record<Verdict, number>>;
}
