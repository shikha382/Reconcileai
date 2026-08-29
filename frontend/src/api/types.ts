// Mirrors backend/app/api/schemas.py field-for-field. These are the ONLY
// shapes the frontend knows about -- never a raw SQLAlchemy dump, never an
// internal dataclass. Money fields stay `string` throughout (the backend's
// own Decimal-safe convention) and are only ever parsed to a Number for
// DISPLAY formatting, never summed or recomputed here.

export interface StageTiming {
  stage: string;
  seconds: number;
}

export interface RunResponse {
  run_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  records_processed: number;
  matched: number;
  exceptions: number;
  auto_resolved: number;
  human_review: number;
  blocked: number;
  rejected: number;
  unresolved: number;
  escalated: number;
  audit_event_count: number;
  audit_chain_valid: boolean;
  stage_timings: StageTiming[];
  errors: string[];
  warnings: string[];
}

export interface RunListResponse {
  items: RunResponse[];
  total: number;
}

export interface ExceptionListItem {
  exception_id: string;
  run_id: string;
  order_id: string;
  payment_id: string;
  category: string | null;
  reconciliation_status: string;
  financial_exposure: string;
  risk_level: string;
  decision: string;
  review_required: boolean;
  ai_investigated: boolean;
  contradiction_found: boolean;
}

export interface ExceptionListResponse {
  items: ExceptionListItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface HypothesisSummary {
  hypothesis_id: string;
  hypothesis_type: string;
  claim: string;
  confidence: number;
}

export interface ChallengeSummary {
  hypothesis_id: string;
  hypothesis_type: string;
  status: string;
  reason: string;
  expected_value: string | null;
  observed_value: string | null;
  residual: string | null;
}

export interface PolicyResultSummary {
  decision: string;
  policy_id: string;
  policy_version: string;
  risk_level: string;
  required_approval: boolean;
  reasons: string[];
  blocked_reasons: string[];
}

export interface ReviewSummary {
  review_id: string;
  state: string;
  dual_control_required: boolean;
  created_by: string;
}

export interface ExceptionDetailResponse {
  exception_id: string;
  run_id: string;
  correlation_id: string;
  order_id: string;
  payment_id: string;
  category: string | null;
  reconciliation_status: string;
  financial_exposure: string;
  risk_level: string;
  risk_score: string;
  ai_investigated: boolean;
  hypotheses: HypothesisSummary[];
  challenges: ChallengeSummary[];
  verification_conclusion: string;
  policy: PolicyResultSummary;
  decision: string;
  review: ReviewSummary | null;
  provenance_available: boolean;
}

export interface TimelineEntry {
  timestamp: string;
  event_type: string;
  actor_type: string;
  actor_id: string | null;
}

export interface ProvenanceResponse {
  exception_id: string;
  correlation_id: string | null;
  timeline: TimelineEntry[];
  ai_believed: string[];
  supporting_evidence: string[][];
  contradicting_evidence: string[][];
  verification_conclusion: string;
  policy_decision: string | null;
  policy_id: string | null;
  policy_version: string | null;
  financial_exposure: string | null;
  approval_required: boolean;
  review_id: string | null;
  audit_chain_valid: boolean;
  audit_events_checked: number;
}

export interface AuditEventSummary {
  event_id: string;
  event_type: string;
  timestamp: string;
}

export interface AuditStatusResponse {
  run_id: string;
  event_count: number;
  chain_valid: boolean;
  invalid_reason: string | null;
  first_event: AuditEventSummary | null;
  last_event: AuditEventSummary | null;
}

export interface AuditEventDetail {
  event_id: string;
  sequence: number;
  event_type: string;
  timestamp: string;
  actor_type: string;
  actor_id: string | null;
  entity_type: string;
  entity_id: string;
  correlation_id: string;
  details: string;
}

export interface AuditEventListResponse {
  run_id: string;
  items: AuditEventDetail[];
  page: number;
  page_size: number;
  total: number;
}

// --- Explanation (M10) -------------------------------------------------------

export interface EvidenceItem {
  evidence_id: string;
  evidence_type: string;
  source_type: string;
  source_id: string;
  field: string | null;
  observed_value: string | null;
  expected_value: string | null;
  relationship: string | null;
  status: string;
  explanation: string;
  severity: string;
  provenance_reference: string | null;
}

export interface FinancialSummary {
  currency: string;
  gross_amount: string;
  expected_amount: string;
  observed_amount: string;
  explained_amount: string;
  unexplained_amount: string;
}

export interface SourceRecordRefs {
  payment_id: string;
  order_id: string;
  settlement_ids: string[];
  bank_transaction_ids: string[];
  refund_ids: string[];
  fee_rule_method: string | null;
}

export interface CandidateMatchEvidence {
  settlement_id: string;
  verdict: string;
  score: string;
  match_class: string;
  positive_evidence: EvidenceItem[];
  negative_evidence: EvidenceItem[];
}

export interface MatchingExplanation {
  match_status: string;
  accepted_settlement_id: string | null;
  candidates: CandidateMatchEvidence[];
}

export interface CalculationTrace {
  label: string;
  rule_id: string | null;
  inputs: Record<string, string>;
  expected_value: string | null;
  observed_value: string | null;
  residual: string | null;
  verification_result: string;
}

export interface AIHypothesisTrace {
  hypothesis_id: string;
  hypothesis_type: string;
  claim: string;
  ai_confidence: number;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  verification_result: string;
  verification_reason: string;
  final_disposition: string;
}

export interface SelfChallengeTrace {
  hypothesis_id: string;
  challenge_question: string;
  counter_evidence: string[];
  verification_result: string;
  final_result: string;
}

export interface ExplanationPolicy {
  policy_id: string;
  policy_version: string;
  decision: string;
  rules_evaluated: string[];
  rules_passed: string[];
  rules_failed: string[];
  reasons: string[];
  blocked_reasons: string[];
  required_approval: boolean;
  risk_level: string;
}

export interface ExplanationRisk {
  risk_level: string;
  risk_score: string;
  reasons: string[];
}

export interface ExplanationResolution {
  resolution_type: string;
  requires_approval: boolean;
  review_state: string | null;
  dual_control_required: boolean | null;
  financial_impact: string;
}

export interface ExplanationAuditReferences {
  exception_id: string;
  correlation_id: string;
  run_id: string | null;
  audit_events_available: boolean;
}

export interface ContradictionItem {
  field: string;
  expected: string | null;
  observed: string | null;
  source_a: string;
  source_b: string;
  status: string;
  impact: string;
}

export interface MissingEvidenceItem {
  required: string;
  available: string[];
  impact: string;
  resulting_decision_influence: string;
}

export interface PriorityInfo {
  priority: string;
  priority_score: string;
  reason_codes: string[];
  recommended_action: string;
}

export interface ExplanationResponse {
  exception_id: string;
  order_id: string;
  payment_id: string;
  decision: string;
  decision_status: string;
  financial_summary: FinancialSummary;
  source_records: SourceRecordRefs;
  matching_evidence: MatchingExplanation;
  calculation_evidence: CalculationTrace[];
  exception_evidence: Record<string, unknown>;
  ai_investigation_status: string;
  ai_hypotheses: AIHypothesisTrace[];
  self_challenge: SelfChallengeTrace[];
  policy: ExplanationPolicy;
  risk: ExplanationRisk;
  resolution: ExplanationResolution;
  audit_references: ExplanationAuditReferences;
  contradictions: ContradictionItem[];
  missing_evidence: MissingEvidenceItem[];
  confidence_note: string;
  human_readable: string;
  priority: PriorityInfo | null;
}

// --- Prioritization / work queue (M11) ---------------------------------------

export interface PrioritizedException {
  exception_id: string;
  order_id: string;
  payment_id: string;
  priority: string;
  priority_score: string;
  risk_level: string;
  risk_score: string;
  financial_exposure: string;
  currency: string;
  age_days: number;
  sla_status: string;
  exception_category: string | null;
  decision_status: string;
  contradiction_count: number;
  missing_evidence_count: number;
  recommended_action: string;
  reason_codes: string[];
  explanation_reference: string | null;
  provenance_reference: string | null;
}

export interface QueueSummary {
  total: number;
  counts_by_priority: Record<string, number>;
  total_financial_exposure: string;
  sla_breached_count: number;
  sla_at_risk_count: number;
  highest_exposure_exception_id: string | null;
  most_common_category: string | null;
}

export interface QueueResponse {
  items: PrioritizedException[];
  summary: QueueSummary;
  page: number;
  page_size: number;
  total: number;
}

export interface HealthResponse {
  status: string;
  service: string;
}

// --- Data sources (M14) -------------------------------------------------------

export interface SourceStatus {
  name: string;
  mode: string; // "SYNTHETIC DATA" | "MOCK PROVIDER" | "LIVE READ-ONLY" | "UNAVAILABLE"
  configured: boolean;
  available: boolean;
  record_count: number | null;
  detail: string;
}

export interface SourcesStatusResponse {
  sources: SourceStatus[];
}

// --- Safety metrics (M15) -----------------------------------------------------

export interface SafetyMetrics {
  available: boolean;
  total: number;
  graded: number;
  false_auto_resolutions: number;
  false_auto_resolution_rate: number;
  match_rate: number;
  reason_unavailable: string | null;
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    request_id: string | null;
  };
}

export interface QueueFilterParams {
  priority?: string;
  risk_level?: string;
  category?: string;
  decision_status?: string;
  sla_status?: string;
  min_age_days?: number;
  min_exposure?: string;
  page?: number;
  page_size?: number;
}

export interface ExceptionFilterParams {
  run_id?: string;
  category?: string;
  risk_level?: string;
  decision?: string;
  page?: number;
  page_size?: number;
}
