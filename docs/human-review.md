# Human Review & Approval Workflow (Milestone 5)

Approval changes **workflow state only**. Nothing in `app.policy.approval` mutates a financial record — that is M5's explicit, non-negotiable boundary.

## Review request lifecycle

```
PENDING_REVIEW ─┬─→ APPROVED
                ├─→ REJECTED
                ├─→ EXPIRED   (past its expiry_at, never decided)
                └─→ CANCELLED (withdrawn before a decision)
```

A `ReviewRequest` (`app.policy.schemas.ReviewRequest`) is created only when `PolicyDecision.required_approval` is true, and carries: the exception, financial impact, evidence IDs, the AI hypothesis summary and verifier-result summary (if AI was involved), rejected alternatives (from M3's negative-evidence report), the proposed resolution, the policy decision that triggered the review, risk level, `created_by` (the maker), `created_at`/`expiry_at`, and whether dual control is required.

A reviewer submits one of `APPROVE` / `REJECT` / `REQUEST_MORE_EVIDENCE` (`app.policy.schemas.ReviewDecisionType`) with a structured `reason_code` (`app.policy.schemas.ReasonCode` — `VERIFIED_EVIDENCE`, `FINANCIAL_RISK`, `AMBIGUOUS_MATCH`, `EVIDENCE_INSUFFICIENT`, `POLICY_BLOCK`, `INCORRECT_PROPOSAL`, `DUPLICATE`, `OTHER`) plus an optional free-text comment — the reason code, not the comment, is what any downstream logic or metric reads; the comment is for a human reader only.

## Dual control (maker ≠ checker)

`ReviewRequest.dual_control_required` is set whenever the policy decision's risk level is `HIGH` or `CRITICAL` (`app.policy.approval.DUAL_CONTROL_RISK_LEVELS`). When set, the actor who created the proposal (`created_by`) cannot also approve it — `submit_review_decision` raises `AuthorizationError` if the same actor ID attempts both. A different authorized human reviewer can approve normally.

## Authorization

`app.policy.authorization` defines a fixed capability table (`ACTOR_CAPABILITIES`) per `ActorType` (`SYSTEM`, `AI`, `HUMAN`, `POLICY_ENGINE`, `VERIFIER`). **AI has `PROPOSE_RESOLUTION` but never `APPROVE` or `CHANGE_POLICY`.** No actor type has `CHANGE_POLICY` in this MVP — a policy change is a deployment/config-review action, not a runtime capability any actor exercises. `POLICY_ENGINE` itself is not treated as a human actor and cannot approve anything, even though it decides everything upstream of a review.

## Idempotency

`review_idempotency_key(exception_id, proposal_id, policy_version)` is a SHA-256-derived key; `ApprovalWorkflowStore.create_review_request` returns the *existing* `ReviewRequest` if one already exists for that key, rather than creating a duplicate. A repeated decision on an already-terminal review (`APPROVED`/`REJECTED`/`EXPIRED`/`CANCELLED`) is a no-op — `submit_review_decision` returns an `ApprovalDecision` whose comment says so, without touching the review's state again.

## Human review packet

`app.policy.review_packet.build_review_packet` assembles one JSON-serializable object (`exception`, `financial_summary`, `ai_summary`, `evidence`, `negative_evidence`, `hypotheses`, `policy`, `risk`, `proposal`) so a future UI never needs to recompute business logic — it renders what's already there.

## Known limitations

- `ApprovalWorkflowStore` is in-memory only (a small registry keyed by idempotency key), mirroring M4's stateless investigation design. A persisted `ReviewRequest`/`ApprovalDecision` table is deferred — see `PROJECT_PLAN.md`'s M5 note.
- `REQUEST_MORE_EVIDENCE` currently only leaves the review `PENDING_REVIEW`; it does not yet trigger a new AI investigation round or notify anyone — that wiring belongs to whichever milestone adds real notification/orchestration.
- Review expiry (`expire_overdue`) must be called explicitly (no background scheduler) — consistent with the brief's "do not use real-time schedulers yet" instruction.
