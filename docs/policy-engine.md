# Policy Engine (Milestone 5)

The `PolicyEngine` (`app.policy.engine`) is the deterministic control layer between "what the AI/deterministic verifier found" and "what actually happens next". It is a pure function: `evaluate_policy(PolicyInput) -> PolicyDecision`. It never reads AI confidence, AI-recommended-action, or any prose explanation — only structured fields.

## Precedence (fixed, documented, never reordered)

```
BLOCK / SAFETY RULES  >  MANDATORY APPROVAL  >  RISK RULES  >  AUTO-RESOLUTION ELIGIBILITY
```

Each tier is evaluated in order. The first tier with a fired rule decides the outcome; lower tiers are never consulted for the *decision* (though every tier's rules are still recorded in `rules_evaluated` for audit — nothing is silently skipped from the trace, only from deciding the outcome). This order is what makes the brief's own policy-conflict example resolve safely: a verified ₹8,000+ fee mismatch fires both an auto-eligibility rule (tier 4) and a high-exposure risk rule (tier 3) — RISK outranks AUTO_ELIGIBILITY, so the result is `HUMAN_REVIEW`, never `SAFE_TO_RESOLVE`.

There is one tier-0 pre-check ahead of BLOCK: an exception classified `missing_transaction` with root-cause status `UNEXPLAINED` maps directly to `UNRESOLVED` — "nothing exists yet" is a different kind of outcome than a safety violation or a review requirement, and must be recognized before `POLICY-UNEXPLAINED-001` (a MANDATORY_APPROVAL rule) would otherwise mislabel it `HUMAN_REVIEW` (a real bug caught while building this milestone — see `CLAUDE.md`'s M5 decision).

## The rules

**BLOCK tier** (→ `REJECTED`):
- `POLICY-VERIFIER-FAIL-001` — root-cause status is `CONTRADICTED` (a hypothesis was actively disproven, not merely uncertain)
- `POLICY-EVIDENCE-001` — evidence is incomplete
- `POLICY-NEGATIVE-RESIDUAL-001` — residual amount is negative (an invalid value, never rounded away)
- `POLICY-UNKNOWN-TYPE-001` — no classified category and not a verified clean match

**MANDATORY_APPROVAL tier** (→ `HUMAN_REVIEW`, `required_approval=True`):
- `POLICY-AMBIG-001` — ambiguous candidates always require human review
- `POLICY-CONFLICT-001` — conflicting evidence blocks automatic resolution
- `POLICY-CATEGORY-001` — the exception's category is policy-blocked from auto-resolution regardless of verification (`duplicate`, `reversed_transaction`, `ambiguous_match`, `partial_settlement`, `unexplained_difference` — see `app.services.resolution_service.NEVER_AUTO_RESOLVE_CATEGORIES`, reusing M4's `app.ai.policy.NEVER_AUTO_RESOLVE_CATEGORIES` rather than a second list)
- `POLICY-UNEXPLAINED-001` — unexplained residual amount requires human review

**RISK tier** (→ `HUMAN_REVIEW`, `required_approval=True`):
- `POLICY-HIGH-RISK-001` — risk level HIGH or CRITICAL
- `POLICY-EXPOSURE-001` — financial exposure exceeds `MAX_AUTO_RESOLVE_EXPOSURE` (₹1,00,000 — the same threshold M4's AI-hypothesis policy gate uses)

**AUTO_ELIGIBILITY tier** (→ `SAFE_TO_RESOLVE`):
- `POLICY-AUTO-001` — verified, zero residual, no ambiguity/conflict, evidence complete, eligible category, within exposure threshold — **all** conditions, not any one of them

Adapted from the brief's example policy IDs (`POLICY-FEE-001`, `POLICY-REFUND-001`) into one composite eligibility rule rather than one rule per category, since M2/M3 already independently verify the fee/refund arithmetic before a case ever reaches the policy engine — the policy question at this layer is "is this *kind* of already-verified result eligible for auto-resolution", not "re-derive whether the fee math is right".

## Fail-closed

Any BLOCK-tier condition, or reaching the end of all four tiers without a fired auto-eligibility rule, defaults to `HUMAN_REVIEW` (or `REJECTED` for BLOCK) — never `SAFE_TO_RESOLVE` by omission.

## Versioning

Every `PolicyDecision` carries `policy_id`, `policy_version`, an `input_hash` (SHA-256 of the structured input, truncated), and `evaluated_at`. `app.policy.simulation.simulate()` provides a dry-run mode: evaluate the same `PolicyInput` against a different named version (`POLICY_VERSIONS` in `simulation.py`) without touching the live policy, returning whether the outcome would actually change.

## Results against the real 300-record dataset

Policy-decision accuracy 1.0000 (0 mismatches against `ground_truth.expected_action`), false-auto-resolution rate 0.0000, all 5 M1 adversarial cases blocked (2 via `POLICY-VERIFIER-FAIL-001`, 3 via ambiguity/category rules). Full numbers in `CLAUDE.md`'s M5 entry.

## Known limitations

- The threshold constants (`MAX_AUTO_RESOLVE_EXPOSURE`, risk-level bucket boundaries in `app.policy.risk`) are qualitative choices tuned against this dataset's exposure range, not derived from a live production loss-tolerance model.
- `app.policy.simulation.simulate()` temporarily mutates `app.policy.engine`'s module-level globals and restores them in a `finally` block — correct for a single-threaded synchronous call (as used throughout this codebase and its tests) but not safe under concurrent simulation calls; a real multi-version registry would parameterize `evaluate_policy` directly instead.
