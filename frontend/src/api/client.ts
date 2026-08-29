// The ONLY place this app makes an HTTP request. Every call goes straight to
// the real ReconcileAI API (see docs/api.md) -- no mock data, no client-side
// decision logic, no client-side priority/risk recomputation. In dev, Vite's
// proxy (vite.config.ts) forwards these same-origin paths to the FastAPI
// process, so no CORS configuration is required for local demo use.
import type {
  AuditEventListResponse,
  AuditStatusResponse,
  ExceptionDetailResponse,
  ExceptionFilterParams,
  ExceptionListResponse,
  ExplanationResponse,
  HealthResponse,
  ProvenanceResponse,
  QueueFilterParams,
  QueueResponse,
  RunListResponse,
  RunResponse,
  SafetyMetrics,
  SourcesStatusResponse,
} from "./types";

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string | null;

  constructor(message: string, code: string, status: number, requestId: string | null) {
    super(message);
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    // Network failure (API unreachable) -- never a raw exception message
    // reaches a component; components only ever see ApiError.
    throw new ApiError("Could not reach the ReconcileAI API.", "NETWORK_ERROR", 0, null);
  }

  if (!response.ok) {
    let code = "UNKNOWN_ERROR";
    let message = `Request failed with status ${response.status}.`;
    let requestId: string | null = null;
    try {
      const body = await response.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        requestId = body.error.request_id ?? null;
      }
    } catch {
      // Response body wasn't valid JSON (e.g. a plain 404 from a middleware) -- fall back to the generic message above.
    }
    throw new ApiError(message, code, response.status, requestId);
  }

  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== null) {
      usp.set(key, String(value));
    }
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  sourcesStatus: () => request<SourcesStatusResponse>("/sources/status"),

  listRuns: () => request<RunListResponse>("/runs"),

  getRun: (runId: string) => request<RunResponse>(`/runs/${encodeURIComponent(runId)}`),

  startRun: (dataset: string) =>
    request<RunResponse>("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset }),
    }),

  getRunAuditStatus: (runId: string) => request<AuditStatusResponse>(`/runs/${encodeURIComponent(runId)}/audit`),

  getRunSafetyMetrics: (runId: string) => request<SafetyMetrics>(`/runs/${encodeURIComponent(runId)}/safety-metrics`),

  listRunAuditEvents: (runId: string, page: number, pageSize: number) =>
    request<AuditEventListResponse>(`/runs/${encodeURIComponent(runId)}/audit/events${query({ page, page_size: pageSize })}`),

  listExceptions: (params: ExceptionFilterParams) =>
    request<ExceptionListResponse>(`/exceptions${query(params as Record<string, string | number | undefined>)}`),

  getExceptionsQueue: (runId: string, params: QueueFilterParams) =>
    request<QueueResponse>(`/exceptions/queue${query({ run_id: runId, ...params } as Record<string, string | number | undefined>)}`),

  getException: (exceptionId: string) => request<ExceptionDetailResponse>(`/exceptions/${encodeURIComponent(exceptionId)}`),

  getExceptionProvenance: (exceptionId: string) =>
    request<ProvenanceResponse>(`/exceptions/${encodeURIComponent(exceptionId)}/provenance`),

  getExceptionExplanation: (exceptionId: string) =>
    request<ExplanationResponse>(`/exceptions/${encodeURIComponent(exceptionId)}/explanation`),
};
