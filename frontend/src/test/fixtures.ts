// Realistic, hand-built fixtures shaped exactly like the real backend
// responses (backend/app/api/schemas.py) -- used to mock `fetch` in tests so
// components can be exercised without a running API. These are NOT
// production data; they exist purely to give tests a stable, known shape.
import { vi } from "vitest";
import type {
  AuditEventListResponse,
  AuditStatusResponse,
  ExceptionDetailResponse,
  ExceptionListResponse,
  ExplanationResponse,
  ProvenanceResponse,
  QueueResponse,
  RunListResponse,
  RunResponse,
  SafetyMetrics,
  SourcesStatusResponse,
} from "../api/types";

export const mockRun: RunResponse = {
  run_id: "RUN-test0001",
  status: "completed",
  started_at: "2026-08-01T10:00:00Z",
  completed_at: "2026-08-01T10:00:05Z",
  duration_seconds: 5.2,
  records_processed: 300,
  matched: 281,
  exceptions: 300,
  auto_resolved: 219,
  human_review: 67,
  blocked: 2,
  rejected: 2,
  unresolved: 12,
  escalated: 0,
  audit_event_count: 3486,
  audit_chain_valid: true,
  stage_timings: [{ stage: "ingest", seconds: 0.1 }],
  errors: [],
  warnings: [],
};

export const mockRunList: RunListResponse = { items: [mockRun], total: 1 };

export const mockExceptionListItem = {
  exception_id: "EXC-p0-critical",
  run_id: mockRun.run_id,
  order_id: "ORD-1",
  payment_id: "PAY-1",
  category: "fee_mismatch",
  reconciliation_status: "mismatch",
  financial_exposure: "7663.77",
  risk_level: "CRITICAL",
  decision: "HUMAN_REVIEW",
  review_required: true,
  ai_investigated: true,
  contradiction_found: true,
};

export const mockExceptionList: ExceptionListResponse = {
  items: [
    mockExceptionListItem,
    { ...mockExceptionListItem, exception_id: "EXC-clean-01", category: "exact_match", risk_level: "LOW", decision: "SAFE_TO_RESOLVE", review_required: false, ai_investigated: false, contradiction_found: false, financial_exposure: "0.00" },
  ],
  page: 1,
  page_size: 25,
  total: 2,
};

export const mockQueue: QueueResponse = {
  items: [
    {
      exception_id: "EXC-p0-critical",
      order_id: "ORD-1",
      payment_id: "PAY-1",
      priority: "P0",
      priority_score: "199580.08",
      risk_level: "CRITICAL",
      risk_score: "199580.08",
      financial_exposure: "7663.77",
      currency: "INR",
      age_days: 40,
      sla_status: "BREACHED",
      exception_category: "fee_mismatch",
      decision_status: "HUMAN_REVIEW",
      contradiction_count: 1,
      missing_evidence_count: 0,
      recommended_action: "REVIEW_EVIDENCE",
      reason_codes: ["CRITICAL_RISK", "SLA_BREACHED", "CONTRADICTORY_EVIDENCE"],
      explanation_reference: "/exceptions/EXC-p0-critical/explanation",
      provenance_reference: "/exceptions/EXC-p0-critical/provenance",
    },
    {
      exception_id: "EXC-p3-clean",
      order_id: "ORD-2",
      payment_id: "PAY-2",
      priority: "P3",
      priority_score: "12.00",
      risk_level: "LOW",
      risk_score: "12.00",
      financial_exposure: "0.00",
      currency: "INR",
      age_days: 1,
      sla_status: "WITHIN_SLA",
      exception_category: "exact_match",
      decision_status: "SAFE_TO_RESOLVE",
      contradiction_count: 0,
      missing_evidence_count: 0,
      recommended_action: "NONE_REQUIRED",
      reason_codes: ["CLEAN_LOW_PRIORITY"],
      explanation_reference: "/exceptions/EXC-p3-clean/explanation",
      provenance_reference: "/exceptions/EXC-p3-clean/provenance",
    },
  ],
  summary: {
    total: 2,
    counts_by_priority: { P0: 1, P1: 0, P2: 0, P3: 1 },
    total_financial_exposure: "7663.77",
    sla_breached_count: 1,
    sla_at_risk_count: 0,
    highest_exposure_exception_id: "EXC-p0-critical",
    most_common_category: "fee_mismatch",
  },
  page: 1,
  page_size: 25,
  total: 2,
};

export const mockExceptionDetail: ExceptionDetailResponse = {
  exception_id: "EXC-p0-critical",
  run_id: mockRun.run_id,
  correlation_id: "CORR-1",
  order_id: "ORD-1",
  payment_id: "PAY-1",
  category: "fee_mismatch",
  reconciliation_status: "mismatch",
  financial_exposure: "7663.77",
  risk_level: "CRITICAL",
  risk_score: "199580.08",
  ai_investigated: true,
  hypotheses: [{ hypothesis_id: "HYP-1", hypothesis_type: "FEE_ADJUSTMENT", claim: "Difference explained by card fee.", confidence: 0.62 }],
  challenges: [{ hypothesis_id: "HYP-1", hypothesis_type: "FEE_ADJUSTMENT", status: "CONTRADICTED", reason: "Actual fee-rule calculation does not explain the residual.", expected_value: "7673.60", observed_value: "7663.77", residual: "9.83" }],
  verification_conclusion: "CONTRADICTED",
  policy: { decision: "REJECTED", policy_id: "RECONCILEAI-CORE-POLICY", policy_version: "1.0.0", risk_level: "LOW", required_approval: false, reasons: [], blocked_reasons: ["A hypothesis was actively disproven by deterministic verification."] },
  decision: "REJECTED",
  review: null,
  provenance_available: true,
};

export const mockExplanation: ExplanationResponse = {
  exception_id: "EXC-p0-critical",
  order_id: "ORD-1",
  payment_id: "PAY-1",
  decision: "REJECTED",
  decision_status: "REJECTED",
  financial_summary: { currency: "INR", gross_amount: "7673.60", expected_amount: "7673.60", observed_amount: "7663.77", explained_amount: "0.00", unexplained_amount: "9.83" },
  source_records: { payment_id: "PAY-1", order_id: "ORD-1", settlement_ids: ["STL-1"], bank_transaction_ids: ["BTX-1"], refund_ids: [], fee_rule_method: "card" },
  matching_evidence: { match_status: "mismatch", accepted_settlement_id: null, candidates: [] },
  calculation_evidence: [{ label: "Fee rule check", rule_id: "FEE-CARD-01", inputs: { amount: "7673.60", fee: "0.00" }, expected_value: "7673.60", observed_value: "7663.77", residual: "9.83", verification_result: "CONTRADICTED" }],
  exception_evidence: {},
  ai_investigation_status: "INVESTIGATED",
  ai_hypotheses: [{ hypothesis_id: "HYP-1", hypothesis_type: "FEE_ADJUSTMENT", claim: "Difference explained by card fee.", ai_confidence: 0.62, supporting_evidence: [], contradicting_evidence: ["Fee rule does not produce this residual."], verification_result: "CONTRADICTED", verification_reason: "Actual fee-rule calculation does not explain the residual.", final_disposition: "REJECTED" }],
  self_challenge: [{ hypothesis_id: "HYP-1", challenge_question: "Does the fee rule fully explain the residual?", counter_evidence: ["Residual persists after fee deduction."], verification_result: "CONTRADICTED", final_result: "Hypothesis rejected." }],
  policy: { policy_id: "RECONCILEAI-CORE-POLICY", policy_version: "1.0.0", decision: "REJECTED", rules_evaluated: ["POLICY-VERIFIER-FAIL-001"], rules_passed: ["POLICY-VERIFIER-FAIL-001"], rules_failed: [], reasons: [], blocked_reasons: ["A hypothesis was actively disproven by deterministic verification."], required_approval: false, risk_level: "LOW" },
  risk: { risk_level: "CRITICAL", risk_score: "199580.08", reasons: ["High financial delta", "Contradicted hypothesis"] },
  resolution: { resolution_type: "NO_ACTION", requires_approval: false, review_state: null, dual_control_required: null, financial_impact: "9.83" },
  audit_references: { exception_id: "EXC-p0-critical", correlation_id: "CORR-1", run_id: mockRun.run_id, audit_events_available: true },
  contradictions: [{ field: "net_amount", expected: "7673.60", observed: "7663.77", source_a: "fee_rule", source_b: "settlement", status: "CONTRADICTED", impact: "₹9.83 unexplained" }],
  missing_evidence: [],
  confidence_note: "AI confidence is advisory only and never overrides deterministic verification.",
  human_readable: "Payment PAY-1 shows a ₹9.83 residual that the AI's fee-adjustment hypothesis does not explain once verified deterministically. The proposal was rejected with no action.",
  priority: { priority: "P1", priority_score: "199580.08", reason_codes: ["SLA_BREACHED", "CONTRADICTORY_EVIDENCE", "AUTO_RESOLUTION_BLOCKED"], recommended_action: "CHECK_FEE_RULE" },
};

export const mockProvenance: ProvenanceResponse = {
  exception_id: "EXC-p0-critical",
  correlation_id: "CORR-1",
  timeline: [
    { timestamp: "2026-08-01T10:00:00Z", event_type: "RUN_STARTED", actor_type: "SYSTEM", actor_id: null },
    { timestamp: "2026-08-01T10:00:01Z", event_type: "EXCEPTION_CREATED", actor_type: "SYSTEM", actor_id: null },
    { timestamp: "2026-08-01T10:00:02Z", event_type: "AI_INVESTIGATION", actor_type: "AI", actor_id: "mock-provider" },
    { timestamp: "2026-08-01T10:00:03Z", event_type: "POLICY_EVALUATED", actor_type: "SYSTEM", actor_id: null },
  ],
  ai_believed: ["Difference explained by card fee."],
  supporting_evidence: [],
  contradicting_evidence: [["Fee rule does not produce this residual."]],
  verification_conclusion: "CONTRADICTED",
  policy_decision: "REJECTED",
  policy_id: "RECONCILEAI-CORE-POLICY",
  policy_version: "1.0.0",
  financial_exposure: "7663.77",
  approval_required: false,
  review_id: null,
  audit_chain_valid: true,
  audit_events_checked: 12,
};

export const mockAuditStatus: AuditStatusResponse = {
  run_id: mockRun.run_id,
  event_count: 12,
  chain_valid: true,
  invalid_reason: null,
  first_event: { event_id: "EVT-1", event_type: "RUN_STARTED", timestamp: "2026-08-01T10:00:00Z" },
  last_event: { event_id: "EVT-12", event_type: "RUN_COMPLETED", timestamp: "2026-08-01T10:00:05Z" },
};

export const mockAuditEvents: AuditEventListResponse = {
  run_id: mockRun.run_id,
  items: [
    { event_id: "EVT-1", sequence: 1, event_type: "RUN_STARTED", timestamp: "2026-08-01T10:00:00Z", actor_type: "SYSTEM", actor_id: null, entity_type: "run", entity_id: mockRun.run_id, correlation_id: mockRun.run_id, details: '{"dataset":"seeds"}' },
  ],
  page: 1,
  page_size: 25,
  total: 1,
};

type Handler = (url: string) => unknown;

export function installFetchMock(handlers: Record<string, unknown>) {
  const handler: Handler = (url) => {
    const path = url.split("?")[0];
    for (const [pattern, body] of Object.entries(handlers)) {
      if (path === pattern || path.startsWith(pattern)) return body;
    }
    throw new Error(`No mock registered for ${url}`);
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      const body = handler(url);
      return {
        ok: true,
        status: 200,
        json: async () => body,
      } as Response;
    }),
  );
}

export const mockSourcesStatus: SourcesStatusResponse = {
  sources: [
    { name: "Synthetic Fixture", mode: "SYNTHETIC DATA", configured: true, available: true, record_count: 300, detail: "The primary 300-record ground-truthed demo dataset." },
    { name: "Razorpay Adapter", mode: "SYNTHETIC DATA", configured: true, available: true, record_count: 3, detail: "Reads realistic, synthetic Razorpay-shaped fixtures." },
    { name: "Bank Source", mode: "SYNTHETIC DATA", configured: true, available: true, record_count: 3, detail: "Generic bank-statement-export fixture." },
    { name: "Internal Ledger", mode: "SYNTHETIC DATA", configured: true, available: true, record_count: 3, detail: "Generic internal order-management-system export fixture." },
  ],
};

export const mockSafetyMetrics: SafetyMetrics = {
  available: true,
  total: 300,
  graded: 300,
  false_auto_resolutions: 0,
  false_auto_resolution_rate: 0,
  match_rate: 0.73,
  reason_unavailable: null,
};

export function installErrorFetchMock(status: number, code: string, message: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status,
      json: async () => ({ error: { code, message, request_id: "REQ-test" } }),
    })) as unknown as typeof fetch,
  );
}
