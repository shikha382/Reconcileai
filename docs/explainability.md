# Explainability (Milestone 10)

M7 proved the pipeline works end-to-end. M8 exposed it as an API. M9 proved it's hard to fool. M10 proves it can **explain** every decision with evidence a finance person can independently trace back to source data.

## Evidence-first architecture

`backend/app/explainability/` is a **read/trace layer**, not a new engine:

```
schemas.py           the canonical ExplanationReport contract (dataclasses)
builder.py            build_explanation(decision, context=None, payment=None, settlement=None) -> ExplanationReport
completeness.py       check_explanation_completeness(report) -> CompletenessResult
provenance_check.py   validate_provenance(report, decision, ledger=None) -> ProvenanceValidationResult
```

`build_explanation` performs **no matching, verification, risk, policy, or audit logic of its own**. Every field is read from an already-computed M2–M6 object:

| Contract section | Source |
|---|---|
| Decision / decision status | `DecisionResult.policy_decision`, `DecisionResult.review` |
| Financial summary | `EvidenceBundle.financial_exposure` (M3) |
| Source records | `EvidenceBundle.connected_records` (M3's evidence graph) |
| Matching evidence | `EvidenceBundle.negative_evidence_report` (M3's "Why NOT Matched" engine) |
| Calculation evidence | `RootCauseResult.decomposition` (M3), optionally `verify_fee_consistency` re-invoked for display (M2) |
| AI hypotheses | `DecisionResult.ai_investigation.outcomes` (M4) |
| Self-challenge | `DecisionResult.contradiction_records` (M6) |
| Policy | `DecisionResult.policy_decision` (M5) — copied field-for-field, never recomputed |
| Risk | `EvidenceBundle.risk_score`, `PolicyDecision.risk_level` (M3/M5) |
| Resolution / approval | `DecisionResult.proposal`, `DecisionResult.review` (M5) |
| Audit references | `DecisionResult.correlation_id`, `.exception_id`, `.run_id` (M6/M7) |

The one exception, and it's deliberate: `_fee_calculation_trace` may re-invoke `verify_fee_consistency` — the same authoritative, already-tested function M2 uses to make the actual decision — purely to recover its full structured output (`rule_id`, expected fee/tax) for **display**. This is calling the one authoritative calculator a second time to read its answer more fully, not a second implementation of fee math.

## Two real findings from building this layer

Both are documented as dated decisions in `CLAUDE.md`, fixed at the explanation layer only (never in M2/M3's own business logic):

1. **M2's `reconciliation_status` and M3's `NegativeEvidenceReport.accepted_settlement_id` can legitimately disagree** on an ambiguous case — M3's `evaluate_candidate()` accepts a candidate on hard-constraint-passing alone, without M2's own score-threshold-plus-margin ambiguity rule. Found via a real `ambiguous_match` case whose `NegativeEvidenceReport` reported a single "ACCEPTED" candidate while M2 correctly called the payment `AMBIGUOUS`. The explanation layer defers to M2's authoritative status: it never surfaces an "accepted" settlement ID for a case the real decision didn't actually accept.
2. **`NO_FEE_RULE_APPLICABLE`/`NO_REFUND_ON_RECORD` reason codes collapse two different situations** — "genuinely nothing configured/claimed" vs. "nothing to check because there was no gap/refund in the first place." Found via the Phase 25 demo: a clean, fully auto-resolved exact-match case showed a spurious "MISSING EVIDENCE: applicable fee rule" line, even though nothing was actually missing — no fee was ever deducted, so there was nothing to verify. The explanation layer now distinguishes these (using `context.fee_rule_by_method` when available) and never reports a non-issue as missing evidence.

## AI hypothesis vs. fact (Phase 7)

Every `AIHypothesisTrace` carries `ai_confidence` labeled explicitly as advisory-only (`ExplanationReport.confidence_note`, the same disclaimer on every report), `verification_result` (`PASSED`/`FAILED`/`NOT_TESTED`) from the real deterministic verifier, and `final_disposition` (`ACCEPTED`/`REJECTED`/`NOT_ACCEPTED`) — an AI claim only ever reads `ACCEPTED` when the real verifier passed it AND the real policy decision was `SAFE_TO_RESOLVE`. A rejected hypothesis's claim text may still appear (quoted, as what the AI proposed) but is always immediately paired with its verification result on the same line of the rendered text — never presented standalone as if it settled anything.

## Self-challenge (Phase 8)

Every `ContradictionRecord` (M6) becomes a `SelfChallengeTrace`: a deterministic, templated challenge question (`_CHALLENGE_QUESTIONS`, one per `HypothesisType` — never AI-generated prose), the real counter-evidence, and the real verification result. A `CONTRADICTED` self-challenge always appears in `ExplanationReport.contradictions` too (Phase 12) — never hidden inside prose alone.

## Missing evidence (Phase 13)

`_missing_evidence_items` scans **every** constraint (not just failing ones — some missing-evidence reason codes are attached to a vacuously-`passed=True` constraint per M2's own convention) and reports what's actually, genuinely missing: no settlement/candidate at all, no confirmed bank credit, no fee rule configured for a method that needed one. It never converts an absence into a positive claim ("fee is probably correct") — the impact statement is always phrased as what *cannot* be verified, never what is assumed true.

## Explanation completeness (Phase 14)

`check_explanation_completeness` enforces, per decision type:

- `SAFE_TO_RESOLVE` must show a zero unexplained residual, a genuine matched/verified relationship, and a policy rule that actually fired.
- `HUMAN_REVIEW` must cite a real reason (policy reasons, contradictions, or missing evidence).
- `REJECTED` must cite a blocking reason.
- `UNRESOLVED` must identify what remains unknown.

Every explanation, regardless of decision, must carry a `correlation_id` and a rendered human-readable summary.

## Provenance integrity (Phase 15)

`validate_provenance` never trusts an `ExplanationReport`'s own claims — it cross-checks every identifier against the real `DecisionResult` it claims to describe: `exception_id`/`correlation_id`/`payment_id` must match; every settlement/bank-transaction/refund ID must actually appear in the evidence graph (`bundle.connected_records`); every AI `hypothesis_id` must be one the real investigation actually produced; every self-challenge reference must correspond to a real `ContradictionRecord`. When a live `AuditLedger` is supplied, it additionally confirms the claimed `correlation_id` resolves to real, persisted events belonging to the claimed exception — a broken or fabricated reference is a validation failure, never silently accepted.

## Hallucination prevention (Phase 16)

Because the explanation is assembled entirely from typed, structured fields (never free-form LLM generation), the four brief-numbered hallucination scenarios are structurally impossible, not just tested-for: no refund record means `source_records.refund_ids == []`, so nothing can claim a refund caused anything; no fee rule means no `fee_verification` trace can exist to claim consistency; a real AI provider outage produces `ai_investigation_status == "UNAVAILABLE_OR_DEGRADED"` with zero hypotheses, never a fabricated one; and the rendered text template has no code path that can print "automatically resolved" unless `decision == "SAFE_TO_RESOLVE"` was itself already true.

## Golden cases (Phase 17)

15 golden cases (`backend/tests/explainability/test_golden_cases.py`) assert **structured semantic facts** — `decision == "SAFE_TO_RESOLVE"`, `residual == Decimal("9.83")`, `policy.required_approval is True` — never a snapshot of wording. Natural-language phrasing may change freely; the underlying financial facts must not.

## API exposure (Phase 19–20)

`GET /exceptions/{exception_id}/explanation` — a new, dedicated endpoint (see the dated decision in `CLAUDE.md` on why extension of the existing `/provenance` route was not chosen), gated by the same `Capability.VIEW_PROVENANCE` the provenance endpoint already uses — **no new capability was added**, so an `AI`-labeled actor gains nothing merely because this endpoint exists. Returns `ExplanationResponse` (`app.api.schemas`), an explicit Pydantic DTO mirroring `ExplanationReport` field-for-field; no SQLAlchemy object or internal dataclass is ever returned directly.

## Performance (Phase 21)

Measured directly (`backend/tests/explainability/test_performance.py`): building explanations for 40 real exceptions took **~0.08% of the time** the underlying pipeline (matching + AI + policy + audit) took for those same 40 exceptions — confirming the explanation layer consumes already-produced results and reruns nothing expensive. A dedicated test also confirms `build_explanation` makes **zero** additional calls to `run_exception_intelligence`.

## Known limitations

- Without `context`/`payment`/`settlement` (the case for the current API endpoint, since `RunRegistry` doesn't store the `ReconciliationContext`), the fee-verification calculation trace and the literal `FeeRule` ID are omitted — never fabricated, just absent. The demo script and any caller with direct pipeline access get the fuller trace.
- `_CHALLENGE_QUESTIONS` covers all 12 `HypothesisType` values with a specific question; any future hypothesis type falls back to a generic question rather than failing.
- The human-readable renderer is a fixed template, not a natural-language generator — this is deliberate (Phase 16), not a limitation to fix later.
