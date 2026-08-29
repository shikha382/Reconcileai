# Data Model

All monetary fields are `Decimal`, never `float`. Every financial record carries: a stable ID, `source`, `amount`, `currency`, `timestamp`, `reference`, `status`, and a `metadata` JSON blob for anything source-specific that doesn't deserve its own column.

## Core financial entities

**Order**
`order_id` (PK), `customer_ref`, `amount` (Decimal), `currency`, `created_at`, `status`, `metadata`

**Payment**
`payment_id` (PK), `order_id` (FK → Order), `amount` (Decimal), `currency`, `method`, `captured_at`, `status`, `gateway_ref`, `metadata`

**Settlement**
`settlement_id` (PK), `payment_id` (FK → Payment, nullable — aggregated settlements may not map 1:1), `settlement_batch_id`, `amount` (Decimal), `fee` (Decimal), `tax` (Decimal), `net_amount` (Decimal), `currency`, `settled_at`, `utr_reference`, `status`, `metadata`

**BankTransaction**
`bank_txn_id` (PK), `amount` (Decimal), `currency`, `value_date`, `narration`, `direction` (credit/debit), `matched_settlement_id` (nullable FK), `metadata`

**Refund**
`refund_id` (PK), `payment_id` (FK → Payment), `amount` (Decimal), `currency`, `initiated_at`, `processed_at`, `status`, `reference`, `metadata`

**FeeRule**
`fee_rule_id` (PK), `method`, `mdr_percent` (Decimal), `fixed_fee` (Decimal), `tax_percent` (Decimal), `effective_from`, `effective_to`

## Reconciliation / exception entities

**ReconciliationMatch**
`match_id` (PK), `left_record_ref`, `right_record_ref`, `match_type` (`exact` / `normalized` / `fuzzy` / `ai_assisted`), `confidence_score` (Decimal, deterministically computed — see `ai-design.md`), `status` (`proposed` / `verified` / `rejected`), `created_at`

**Exception**
`exception_id` (PK), `record_refs` (list), `category` (enum — see taxonomy below), `amount_at_risk` (Decimal), `status` (`open` / `auto_resolved` / `human_review` / `unresolved`), `priority_score` (Decimal — see VaR prioritization), `created_at`, `resolved_at`

**Evidence**
`evidence_id` (PK), `exception_id` (FK), `source_type`, `source_ref`, `content` (structured, not free text), `collected_at`

**AIHypothesis**
`hypothesis_id` (PK), `exception_id` (FK), `proposed_category`, `proposed_resolution`, `cited_evidence_ids` (list — every ID here must exist in Evidence, validated before use), `raw_model_output` (structured JSON, stored verbatim for audit), `model_self_reported_signals` (advisory only, never authoritative), `created_at`

**Decision**
`decision_id` (PK), `exception_id` (FK), `hypothesis_id` (FK, nullable — a decision can also be purely deterministic with no AI involvement), `decision_type` (`auto_resolve` / `human_review` / `unresolved` / `blocked`), `verification_result` (pass/fail + detail), `policy_result` (pass/fail + rule triggered), `decided_at`, `decided_by` (`system` / `human`)

**Approval**
`approval_id` (PK), `decision_id` (FK), `approver`, `approved_at`, `notes`

**AuditEvent**
`event_id` (PK), `entity_type`, `entity_id`, `action`, `actor` (`system` / `ai` / `human`), `payload_hash`, `prev_hash`, `hash` (SHA-256 chain — see below), `timestamp`

## Exception taxonomy (fixed enum, minimum set)

`missing_transaction`, `duplicate`, `partial_settlement`, `over_settlement`, `under_settlement`, `fee_mismatch`, `refund_mismatch`, `timing_mismatch`, `reference_mismatch`, `split_settlement`, `aggregated_settlement`, `reversed_transaction`, `ambiguous_match`, `unexplained_difference`

## Audit hash chaining

Each `AuditEvent.hash = SHA256(prev_hash + canonical_json(payload))`. `prev_hash` is the previous event's `hash` (genesis event uses a fixed seed string). This makes the log tamper-evident: recomputing the chain from the first event and comparing to stored hashes detects any retroactive edit. This is a demonstration of tamper-evidence, not a cryptographic non-repudiation system — do not oversell it as more than that in the demo narrative.

## Notes

- `Settlement.payment_id` is nullable specifically to support `aggregated_settlement` (many payments → one settlement) and `split_settlement` (one payment → many settlements) cases; the actual many-to-many linkage lives in `ReconciliationMatch`, not as a foreign key on `Settlement` itself.
- `ReconciliationMatch` rows are created for **rejected** candidates too (status `rejected`), not only accepted ones — this is what powers the "Why NOT Matched" feature (`docs/ai-design.md`).

## Milestone 5 entities (implemented as plain dataclasses, not yet DB-persisted)

`PolicyInput`/`PolicyDecision` (`app.policy.schemas`), `ResolutionProposal`, `ReviewRequest`/`ApprovalDecision`, `Actor`. Map onto this document's original `Decision`/`Approval` sketch, extended with the fuller five-way decision vocabulary (`SAFE_TO_RESOLVE`/`HUMAN_REVIEW`/`REJECTED`/`ESCALATED`/`UNRESOLVED`) and the closed `ResolutionType`/`ReasonCode` enums M5's brief required. `ReviewRequest`/`ApprovalWorkflowStore` remain in-memory (see the M6 addendum below for the explicit decision to keep it that way for now) — see `PROJECT_PLAN.md`'s M5 note for what a persisted version would need.

## Milestone 6 entity: `AuditEventRecord` (this document's original `AuditEvent` sketch, now actually persisted and hash-chained)

`AuditEventRecord` (`backend/app/db/models.py`, table `audit_events`) is the M1 sketch's `AuditEvent` finally implemented as a real, persistent, append-only table:

`event_id` (PK, str), `sequence` (int, unique, explicitly assigned — not autoincrement), `event_type`, `timestamp`, `entity_type`, `entity_id` (indexed), `actor_type`, `actor_id` (nullable), `source`, `correlation_id` (indexed), `payload_json` (Decimal-safe JSON), `schema_version`, `previous_event_hash`, `event_hash`.

This maps onto the original sketch's `entity_type`/`entity_id`/`action`(→`event_type`)/`actor`(→`actor_type`+`actor_id`)/`payload_hash`(→ folded into `event_hash`'s own computation)/`prev_hash`(→`previous_event_hash`)/`hash`(→`event_hash`)/`timestamp` fields, extended with `sequence` (contiguity checking), `correlation_id` (cross-event threading, not in the original sketch), and `schema_version` (so old events remain verifiable under a schema that has since evolved). Full hashing/verification detail in `docs/audit-ledger.md`.

Only `app.audit.ledger.AuditLedger.append()` writes to this table — no `UPDATE`/`DELETE` code path exists anywhere against it, by construction (the class has no such method).

## Milestone 6 decision: `ApprovalWorkflowStore` (Phase 16) stays in-memory

Evaluated explicitly rather than left unaddressed: persisting `ReviewRequest`/`ApprovalDecision` to a table was considered for M6, since the ledger now durably makes `REVIEW_REQUESTED` an audit event regardless. **Decision: kept in-memory**, because (a) the audit ledger already durably records that a review was requested, with the full proposal/policy-decision snapshot, even though the *live pending-approval queue* itself doesn't survive a restart; (b) persisting it correctly would mean re-deriving/serializing the exact same state-machine, dual-control, and idempotency-key logic `app.policy.approval` already implements and is fully tested against, which is exactly the kind of rewrite-for-its-own-sake this project avoids; (c) no caller (API/UI) exists yet that needs a review request to survive a process restart. If a future milestone adds real persistence here, it must preserve `ApprovalWorkflowStore`'s existing state machine/idempotency/authorization/dual-control/expiry semantics exactly, per the M6 brief's own instruction — not redesign them.
