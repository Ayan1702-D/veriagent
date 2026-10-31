import type {
  ApiErrorBody,
  AuditResponse,
  EvalMetrics,
  RunAcceptedResponse,
  RunBudget,
  RunResponse,
} from "./types";

function apiBase(): string {
  const value = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (!value) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }
  return value;
}

export function apiUrl(path: string): string {
  return `${apiBase()}${path}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code = "api_error",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // The fallback below keeps non-JSON failures readable.
    }
    throw new ApiError(
      body.error?.message ?? `Request failed with status ${response.status}`,
      response.status,
      body.error?.code,
    );
  }

  return (await response.json()) as T;
}

export function createRun(
  claim: string,
  budget?: Partial<RunBudget>,
): Promise<RunAcceptedResponse> {
  return request<RunAcceptedResponse>("/api/runs", {
    method: "POST",
    body: JSON.stringify({ claim, ...(budget ? { budget } : {}) }),
  });
}

export function getRun(runId: string): Promise<RunResponse> {
  return request<RunResponse>(`/api/runs/${encodeURIComponent(runId)}`);
}

export function getAudit(runId: string): Promise<AuditResponse> {
  return request<AuditResponse>(`/api/runs/${encodeURIComponent(runId)}/audit`);
}

export function replayRun(runId: string): Promise<RunAcceptedResponse> {
  return request<RunAcceptedResponse>(`/api/runs/${encodeURIComponent(runId)}/replay`, {
    method: "POST",
  });
}

export function getLatestEval(): Promise<EvalMetrics> {
  return request<EvalMetrics>("/api/eval/latest");
}
