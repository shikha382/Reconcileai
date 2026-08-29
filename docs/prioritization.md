# Prioritization & Finance Work Queue (Milestone 11)

M9 proved the system is hard to fool. M10 proved every decision can be explained with evidence. M11 answers the operational question those two milestones set up but never asked: **given many exceptions, which ones should a finance controller look at first, and why?**

## Why this exists

A finance controller doesn't triage 300 exceptions in the order the pipeline produced them. They need a queue: most urgent first, with a concrete, evidence-backed reason for every ranking. M11 builds that queue as a **read-only operational layer** — it consumes already-computed M3/M5/M6/M10 results and never makes a financial decision of its own.

## What already existed (and was reused, not duplicated)

Before writing any new code, this milestone searched the repository for `priority`, `risk`, `SLA`, `age`. It found `app.policy.risk` (M5) already implements:

- `assess_sla(payment, reference_now)` → `SLAAssessment` (age, due date, `SLAStatus.BREACHED`/`AT_RISK`/`WITHIN_SLA`)
- `assess_priority(payment, root_cause, reference_now)` → `PriorityAssessment` (`priority_level` — CRITICAL/HIGH/MEDIUM/LOW, `priority_score`, `priority_reasons`), built on top of M3's own `compute_risk_score` formula

These were written in M5 but **never wired into the real pipeline** (`resolution_service.py` imports `assess_priority`/`assess_sla` but never calls them; `review_packet.py`'s `build_review_packet` — the only consumer — is invoked only by its own test file, never by `decision_service`/`reconciliation_pipeline`). M11's job was to finish connecting this existing, tested logic to a real queue and API, and to extend it with the newer M6/M10 signals (contradictions, missing evidence) M5's original formula predates — **not** to invent a second priority formula.

## Architecture

```
backend/app/prioritization/
    schemas.py    PrioritizedException, QueueSummary, ReasonCode, RecommendedAction (Phase 2/5/6)
    scorer.py     build_prioritized_exception(), attach_priority() (Phase 3)
    queue.py      get_priority_queue(), summarize_queue(), QueueFilters (Phase 7-9)
```

`build_prioritized_exception(decision, payment, reference_now, explanation=None)` is the only place computation happens, and every number in it is READ, not derived from scratch:

| Field | Source |
|---|---|
| `priority` / `priority_score` | `app.policy.risk.assess_priority` (M5, called verbatim) |
| `sla_status` / `age_days` | `app.policy.risk.assess_sla` (M5, called verbatim) |
| `risk_level` / `risk_score` | `DecisionResult.policy_decision.risk_level`, `EvidenceBundle.risk_score` (M3/M5, already computed) |
| `financial_exposure` | `EvidenceBundle.financial_exposure.gross_amount` (M3) |
| `decision_status` | `DecisionResult.policy_decision.decision` (M5) |
| `contradiction_count` | `DecisionResult.contradiction_records` (M6) |
| `missing_evidence_count` | `ExplanationReport.missing_evidence` (M10, optional) |

## Priority model (Phase 3)

The priority LEVEL (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`, mapped to `P0`/`P1`/`P2`/`P3`) is M5's own `assess_priority` output, unchanged. M11 does not escalate or re-weight this tier — the base formula (`risk_score = |financial_delta| × confidence_deficit × sla_aging_factor`, combined with SLA status) already folds in exposure, verification uncertainty, and aging, and `confidence_deficit` already reflects M3's own root-cause status (including `CONTRADICTED`). Escalating a second time for the same signal would double-count it.

What M11 *adds* is transparency: **reason codes** that name every real, independently-checkable factor contributing to urgency — including two M11 didn't have before (contradiction count from M6's self-challenge, missing-evidence count from M10's explanation) — surfaced as additional context and used as queue tie-breakers, never as a second tier-escalation rule.

## Reason codes (Phase 5)

Only codes backed by real, already-computed data:

| Code | Fires when |
|---|---|
| `CRITICAL_RISK` / `HIGH_EXPOSURE` | `policy_decision.risk_level` is `CRITICAL` / `HIGH` (M5) |
| `SLA_BREACHED` / `SLA_AT_RISK` | `assess_sla`'s own status (M5) |
| `OLD_EXCEPTION` | `age_days >= MAX_AGING_DAYS` (30 — reuses `app.engines.risk.scoring.MAX_AGING_DAYS`, the same aging-factor cap M3's own risk score already uses, not a second threshold) |
| `CONTRADICTORY_EVIDENCE` | at least one `CONTRADICTED` entry in `DecisionResult.contradiction_records` (M6) |
| `MISSING_EVIDENCE` | `ExplanationReport.missing_evidence` is non-empty (M10) |
| `AUTO_RESOLUTION_BLOCKED` | `decision_status` is `HUMAN_REVIEW` or `REJECTED` |
| `HIGH_VALUE_REFUND` | `category == "refund_mismatch"` and `gross_amount > 5000.00` — the midpoint of `data/synthetic/generator.py`'s own `gen_refund_mismatch` amount range (500–10000), not an arbitrary number |
| `UNRESOLVED_FINANCIAL_DIFFERENCE` | `root_cause.unexplained_amount > 0` |
| `CLEAN_LOW_PRIORITY` | none of the above fired — the honest "nothing wrong" answer, mirroring `assess_priority`'s own "low exposure, within SLA" fallback |

## SLA handling (Phase 4/5)

Reused entirely from M5: `SLA_DUE_DAYS = 7`, `SLA_AT_RISK_FRACTION = 0.70`. A known, documented characteristic of running this against the synthetic dataset (not a defect, and unchanged from M3/M5's own documented reasoning): since a synthetic batch has no real "now," `reference_now` is the batch's own latest `captured_at`, so most of the 300 records — generated across a 60-day window — are already "older than 7 days" relative to that reference point, and a large share show `SLA_BREACHED`. This is the exact same characteristic M3's `sla_aging_factor` module docstring already documents; M11 inherits it, doesn't introduce it.

## Queue ordering and tie-breaking (Phase 7)

`get_priority_queue` is a pure, deterministic sort — same inputs always produce the same order, no randomness, no LLM involvement. Sort key, in the brief's own specified order:

1. Priority tier (`P0` < `P1` < `P2` < `P3`)
2. SLA urgency (`BREACHED` < `AT_RISK` < `WITHIN_SLA`)
3. Financial exposure (descending)
4. Risk score (descending)
5. Age in days (descending)
6. Exception ID (ascending) — the final, stable tie-break guaranteeing a total order regardless of input order

Financial values are converted to `Decimal` for the sort key only (Phase 10's own "priority calculations may normalize values only for ranking" instruction) — the stored `financial_exposure`/`risk_score` fields on `PrioritizedException` stay Decimal-exact strings throughout; nothing here mutates a payment, settlement, bank transaction, refund, or policy decision.

## Recommended action (Phase 6)

Advisory only — `recommend_action()` returns a plain string. It never calls an approval/resolution function, never mutates a record, and is computed strictly *after* the real `PolicyDecision` already exists. A `SAFE_TO_RESOLVE` case gets `NONE_REQUIRED`; category and reason codes drive the rest (`CHECK_FEE_RULE` for `fee_mismatch`, `INVESTIGATE_REFUND` for `refund_mismatch`, `VERIFY_SETTLEMENT` for split/aggregated/partial/over/under-settlement categories, `REQUEST_MISSING_EVIDENCE` for `UNRESOLVED`/`missing_transaction`, `ESCALATE_FINANCE_CONTROLLER` for `P0` or any contradiction, `REVIEW_EVIDENCE` as the generic fallback).

## Relationship to M5 policy (Phase 10)

Priority is downstream of the decision, never upstream of it. `build_prioritized_exception` takes an already-finalized `DecisionResult` as input; nothing in `app.prioritization` calls `evaluate_policy`, `verify_hypothesis`, or any M2–M6 decision-making function. Explicit, directly-tested invariants (`backend/tests/prioritization/test_decision_invariance.py`): building priority (even repeatedly, even from a tampered/forged `PrioritizedException`) never changes `policy_decision.decision`, `risk_level`, `reasons`, `review` state, AI investigation outcomes, or contradiction records.

## Relationship to M10 explainability (Phase 13)

Not a second explanation system. `app.prioritization.scorer.attach_priority(explanation, prioritized)` adds one `PriorityInfo` field (defined in `app.explainability.schemas` itself, to avoid a circular import between the two packages) to the existing `ExplanationReport`, and appends one rendered "PRIORITY" section to the *same* `human_readable` text — reusing the identical reason codes and recommended action already computed for the queue, never a separately-worded explanation.

## API (Phase 14-15)

`GET /exceptions/queue?run_id=...` — a new, read-only endpoint (see the dated decision on why a new route rather than extending `GET /exceptions`), reusing the *existing* `Capability.VIEW_EXCEPTION` (no new capability — an `AI`-labeled actor already had this from M4, and gains nothing new). Filters: `priority`, `risk_level`, `category`, `decision_status`, `sla_status`, `min_age_days`, `min_exposure` (parsed as Decimal, rejected as a clean `400 INVALID_FILTER` if malformed). Bounded pagination (1–100, matching M8's existing `MAX_PAGE_SIZE`). Response: `QueueResponse` — paginated `items` plus a `summary` computed over the *entire* filtered set, not just the current page.

## Performance (Phase 16)

Measured directly: prioritizing 40 real exceptions (with M10 explanations) took **~0.09%** of the time the underlying pipeline took to produce those same 40 `DecisionResult`s. The pure sort/summary layer (`get_priority_queue`/`summarize_queue`) processes 10,000 synthetic records in well under a second — no AI investigation, matching, verification, policy, or audit generation is ever rerun to compute a priority.

## Known limitations

- `PriorizedException`/`QueueFilters` are plain dataclasses with no validation layer of their own — `queue.py`'s sort/summary functions are pure and trust whatever list they're given (by design: they are a display/aggregation layer, not a re-verification layer). The REAL system never constructs an internally-inconsistent `PrioritizedException` (verified directly in `test_scorer.py`); adversarial tests on hand-crafted malformed records exist to prove robustness (no crash), not to claim the display layer re-validates upstream data.
- The API's `GET /exceptions/queue` builds a context-less `ExplanationReport` per exception (no `ReconciliationContext`/`Payment`/`Settlement` available from `RunRegistry` alone, the same limitation already documented for M10's own `GET /exceptions/{id}/explanation`) — `missing_evidence_count` is still accurate, just without the fee-rule-specific precision refinement that requires context.
- SLA/aging thresholds (`SLA_DUE_DAYS=7`, `MAX_AGING_DAYS=30`) are M3/M5's own existing constants, reused as-is — M11 introduces no new threshold beyond `HIGH_VALUE_REFUND_THRESHOLD` (5000.00, documented above).
