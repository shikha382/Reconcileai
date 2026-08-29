# Safe Resolution (Milestone 5)

Milestone 5 is the control layer between "AI investigated this" (M4) and "something happened" (a later, controlled-integration milestone, if ever). It answers one question deterministically: **given the evidence, AI hypothesis (if any), verifier result, financial exposure, and business policy, what is the safest allowed next action?**

## Architecture

```
M3 EVIDENCE (EvidenceBundle) ──▶ M4 AI TRACE (optional) ──▶ DETERMINISTIC VERIFIER (already baked into
                                                              bundle.root_cause -- M2/M3/M4's own checkers)
                                                                    │
                                                                    ▼
                                                            app.policy.engine.evaluate_policy
                                                                    │
                                          ┌─────────────────────────┼─────────────────────────┐
                                          ▼                         ▼                         ▼
                                   SAFE_TO_RESOLVE            HUMAN_REVIEW                 REJECTED
                                          │                         │                    (or ESCALATED /
                                          ▼                         ▼                      UNRESOLVED)
                                  ResolutionProposal          ReviewRequest
                                  (verified=True)             (PENDING_REVIEW)
                                          │                         │
                                          └────────────┬────────────┘
                                                        ▼
                                              (structured AuditEvent)
```

**The financial system of record is not mutated anywhere in M5.** `resolve_exception` (`app.services.resolution_service`) produces a `PolicyInput`, a `PolicyDecision`, a `ResolutionProposal`, and — only when required — a `ReviewRequest`. None of these write to `Payment`/`Settlement`/`BankTransaction`/`Refund`.

## State machine

```
EXCEPTION_OPEN → INVESTIGATING → PROPOSAL_READY → POLICY_EVALUATED
                                                        │
                              ┌─────────────────────────┼─────────────────────────┐
                              ▼                         ▼                         ▼
                        AUTO_RESOLVE               HUMAN_REVIEW                BLOCKED
                              │                         │                         │
                              ▼                    APPROVED/REJECTED              ▼
                            CLOSED ◀───────────────────┘◀──────────────────  (re-investigate or CLOSED)
```

`app.policy.state_machine.transition(current, target)` is the only way to move between `ExceptionState` values; any transition not in `ALLOWED_TRANSITIONS` raises `InvalidStateTransitionError` and leaves the state untouched.

## Resolution proposals

`ResolutionProposal` (`app.policy.schemas`) is what the AI or the deterministic system may **propose** — never execute. `ResolutionType` is a closed six-value enum (`MARK_RECONCILED`, `LINK_RECORDS`, `CLASSIFY_EXCEPTION`, `REQUEST_HUMAN_REVIEW`, `ESCALATE`, `NO_ACTION`) — deliberately excluding anything like `EXECUTE_ARBITRARY_UPDATE`. Every proposal passes: schema validation (it's a typed dataclass — malformed input can't construct one), evidence validation (M3's bundle), deterministic verification (already in `bundle.root_cause`), the policy engine, the risk engine, and the approval-requirement check — only then is it `verified=True` and (if no review is required) ready for a resolution a later milestone could act on.

## Risk & SLA

`app.policy.risk` builds on M3's existing `risk_score` formula (amount × confidence-deficit × aging — never replaced, only reused) with two additions this milestone needed: `risk_level_for_score` (LOW/MEDIUM/HIGH/CRITICAL buckets) and `assess_sla` (WITHIN_SLA/AT_RISK/BREACHED, from a configurable due-date window, computed deterministically from `payment.captured_at` — no real-time scheduler). `assess_priority` combines both into a priority score/level/reasons list that explicitly prioritizes human attention without ever influencing the policy engine's own safety decision (risk is a policy *tier*, not a bypass).

## Actor model

`ActorType` (`SYSTEM`, `AI`, `HUMAN`, `POLICY_ENGINE`, `VERIFIER`) is a label, not a permission — `app.policy.authorization.ACTOR_CAPABILITIES` is checked explicitly for every action. See `docs/human-review.md` for the full authorization/dual-control model.

## Audit-ready events

`app.policy.audit.make_event` builds a structured `AuditEvent` (`EXCEPTION_CREATED`, `AI_INVESTIGATION_COMPLETED`, `HYPOTHESIS_VERIFIED`, `HYPOTHESIS_REJECTED`, `POLICY_EVALUATED`, `RESOLUTION_PROPOSED`, `REVIEW_REQUESTED`, `REVIEW_APPROVED`, `REVIEW_REJECTED`, `RESOLUTION_BLOCKED`) with `entity_id`, `actor_type`/`actor_id`, `source`, `payload`, and a `correlation_id` tying every event for one exception together. **This is not the final immutable hash-chain ledger** — these are the structured events that later milestone will seal, per the brief's own instruction not to build the ledger yet.

## Results against the real 300-record dataset

Policy-decision accuracy 1.0000, **false-auto-resolution rate 0.0000**, **unsafe-approval rate 0.0000**, all 5 M1 adversarial cases correctly blocked. 307/307 tests pass (220 M1–M4, 87 M5). Full detail, including two example traces (AI PROPOSED → VERIFIER → POLICY → RISK → outcome), in `CLAUDE.md`'s M5 entry and this milestone's final report.

## Known limitations

See `docs/policy-engine.md` and `docs/human-review.md` for area-specific limitations. Overall: no persisted DB model exists yet for `ResolutionProposal`/`PolicyDecision`/`ReviewRequest`/`AuditEvent` (all pure Python dataclasses, proven correct in-memory); no API layer is exposed (the brief allows deferring this if not already part of the architecture, and M2's own ingestion endpoint is still deferred for the same reason — see `PROJECT_PLAN.md`).
