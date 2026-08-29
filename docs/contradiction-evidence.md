# Structured Challenge / Contradiction Evidence

M6's one technically distinctive feature. **Not free-form chain-of-thought** — every field in a `ContradictionRecord` is a structured evidence classification, built directly from an already-computed `HypothesisOutcome` (M4's hypothesis + deterministic verifier result + policy decision). Nothing here re-derives financial logic or invents a second verification path; this module answers one question — "what evidence could prove this hypothesis wrong, and did it?" — by reusing M3's own evidence/constraint concepts (`ConstraintResult`, `NegativeEvidenceReport`) rather than duplicating them.

## Why this exists

An AI hypothesis being "deterministically verified" (M4) is binary: passed or failed. That collapses two genuinely different situations into one bit — a hypothesis that failed because the evidence actively disagrees with it (a real contradiction, a red flag) and a hypothesis that failed merely because not enough evidence was available yet (insufficient, not necessarily wrong). M6 makes that distinction explicit and structured, and — more importantly — makes it something the policy engine can act on as its own signal, not just a pass/fail gate the AI layer already consumed internally.

## `ContradictionRecord` (`backend/app/challenge/contradiction.py`)

```python
@dataclass
class ContradictionRecord:
    hypothesis_id: str
    hypothesis_type: str
    supporting_evidence: list[str]      # evidence_ids, when SUPPORTED
    contradicting_evidence: list[str]   # evidence_ids, when CONTRADICTED
    missing_evidence: list[str]         # cited-but-never-retrieved IDs, when INSUFFICIENT_EVIDENCE
    status: str                         # SUPPORTED | CONTRADICTED | INSUFFICIENT_EVIDENCE
    expected_value: str | None
    observed_value: str | None
    residual: str | None
    reason: str
```

`build_contradiction_record(outcome: HypothesisOutcome, grounding_violations=None)`:

- If the hypothesis cited IDs never actually retrieved via a logged tool call this session (M4's grounding check), the record is `INSUFFICIENT_EVIDENCE` regardless of what the verifier said — a claim grounded in nothing can't be evaluated as either supported or contradicted.
- Else if the deterministic verifier passed, the record is `SUPPORTED`, carrying the verifier's own `evidence_ids` as `supporting_evidence`.
- Else, the record is `CONTRADICTED`, carrying the same `evidence_ids` as `contradicting_evidence` — the evidence that disproved the claim.

## The self-challenge rule (Phase 11)

`has_unresolved_contradiction(records: list[ContradictionRecord]) -> bool` is `True` if **any** tested hypothesis for the exception was `CONTRADICTED`.

This function does not itself decide anything. `app.services.decision_service.run_decision_pipeline` calls it after building all of an exception's `ContradictionRecord`s, and if it's `True`, sets `policy_input.conflicting_evidence = True` before calling M5's `evaluate_policy()`. M5's policy engine already has a dedicated rule for exactly this field — `POLICY-CONFLICT-001` in its `MANDATORY_APPROVAL` tier, which outranks the `AUTO_ELIGIBILITY` tier. **The challenge layer feeds evidence to the policy engine; it never overrides it, and it never adds a second, competing decision path.** This is why the integration required no new policy logic — `PolicyInput.conflicting_evidence` already existed in M5's schema, unused by any caller until M6's decision service started setting it from a real signal.

Verified empirically: `backend/tests/audit/test_decision_service.py::test_self_challenge_rule_blocks_auto_resolution_whenever_a_contradiction_exists` confirms across the full 300-record dataset that **no** exception with a contradicted hypothesis ever reaches `SAFE_TO_RESOLVE` — either the self-challenge rule's `POLICY-CONFLICT-001` fires, or (when the underlying root-cause `verifier_status` was already `CONTRADICTED`) the BLOCK tier's `POLICY-VERIFIER-FAIL-001` fires first and rejects it outright, which is an even stronger safety outcome, not a bypass.

## Bounded and deterministic (Phase 12)

This is a single-pass classification of an already-completed verification result. There is no loop, no recursive self-reflection, and no second LLM call anywhere in this module. If an LLM is involved at all, it only ever proposed the *original* hypothesis, back in M4 — `app.challenge.contradiction` never asks a model anything; it is pure Python over already-structured data. This satisfies the M6 brief's explicit boundary: no unrestricted second LLM, no multi-agent swarm, no unbounded self-reflection.

## Audit trail

Every `ContradictionRecord` is written to the ledger via `HYPOTHESIS_CHALLENGED` (always), plus `CONTRADICTION_FOUND` + `HYPOTHESIS_REJECTED` (if `CONTRADICTED`) or `HYPOTHESIS_VERIFIED` (if `SUPPORTED`) — see `docs/audit-ledger.md` and `docs/decision-provenance.md` for how these compose into one correlation-threaded, tamper-evident record per exception.
