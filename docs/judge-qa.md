# Judge Q&A Preparation (Milestone 15)

Every answer below reflects the actual implementation — cross-referenced against real code, real tests, and real measured results. Where a claim is measured, the exact source is named.

**Why AI?**
Some exceptions genuinely need judgment a fixed rule can't express — e.g. "is this residual explained by a fee, a timing delay, or a duplicate?" AI investigates only the residual cases M3's deterministic triage can't already resolve (24.7% of the dataset, M4) — never the whole dataset.

**Why not rules only?**
Rules-only (Baselines A/B/C in `docs/demo-runbook.md`) either miss legitimately-reformatted references (exact-ID: recall 0.89) or accept unsafe matches with no safety net (naive fuzzy: 14.67% unsafe auto-resolution rate, measured directly, `scripts/evaluate_competitive_baselines.py`). AI adds investigative flexibility rules don't have — but only ever as a *proposal*.

**Why not LLM only?**
An LLM's own recommendation is never independently verified — see `docs/demo-runbook.md`'s Baseline D discussion. This project's own historical record (two real, dated defects, M4 and M9) shows exactly what happens when a single signal is trusted without a full verification/policy layer: real false auto-resolutions, caught and fixed only because the discipline of independent verification exists.

**How do you prevent hallucinations?**
The AI can only cite record IDs that actually exist (`app.ai.verifier.validate_grounding`) and can only select from a closed, 12-value hypothesis-type enum (`app.ai.schemas.HypothesisType`) — it cannot invent a financial fact or a transaction ID. Every hypothesis is independently re-derived with real Decimal arithmetic before anything is trusted (`app.ai.verifier.verify_hypothesis`).

**Can AI override policy?**
No — structurally, not just by convention. `app.policy.engine.evaluate_policy` is the sole decision authority (unified via M6's `decision_service`); the AI's own confidence/recommendation is never read by it (`app.policy.schemas`/`app.ai.policy` — `AIHypothesis.confidence`/`recommended_action` are stored for audit only). Proven adversarially: `tests/adversarial/test_ai_misleading_evidence.py` (5 cases, including "extremely high AI confidence does not override contradiction").

**What happens if AI is wrong?**
Its hypothesis is independently verified against real financial arithmetic; if the verification contradicts it, the contradiction is recorded (`app.challenge.contradiction`), the case is routed to `HUMAN_REVIEW` or blocked, and everything is on the audit trail. Measured result: 0.0000% false auto-resolution rate across the full 300-record dataset (`tests/audit/test_evaluation_m6.py`, re-confirmed every milestone).

**What happens if the provider API is down?**
The read-only Razorpay adapter (M14) has a bounded-retry, typed error model (`ProviderTimeoutError`/`ProviderNetworkError`/etc., `app.adapters.errors`) — a down provider surfaces a clean, categorized error, never a silent fallback to fabricated data. The core reconciliation pipeline itself doesn't depend on any live provider at all; the demo runs entirely on local synthetic fixtures.

**Why synthetic data?**
Reproducibility, offline operation, known adversarial cases, and known ground truth — a live account has no ground truth to grade against. Documented decision: `docs/demo-runbook.md` §17, `docs/provider-adapters.md`'s live-integration decision.

**Can this work with real Razorpay data?**
Yes, architecturally — a read-only adapter (`backend/app/adapters/`) already maps real Razorpay Payment/Settlement/Refund entity shapes into the exact same canonical records the reconciliation engine consumes. It has never been exercised against Razorpay's actual production API in this environment (no real credentials exist) — that is the one honest gap, documented in `docs/production-readiness.md`.

**How do you prevent duplicate reconciliation?**
Ingestion is idempotent — `session.merge()` keyed on a deterministic ID means re-ingesting the same record never creates a duplicate row (`app.ingestion.pipeline.ingest_records`, M1, re-proven for adapter-sourced data in M14's `test_idempotency.py`).

**How are refunds handled?**
Each refund must be matched by an equal-amount DEBIT bank transaction; a real historical defect (a duplicated refund double-claiming one real debit) was found and fixed — each debit can now be claimed as evidence by at most one refund (`app.engines.reconciliation.verification.verify_refund_consistency`, M9).

**How are fees handled?**
Verified against the configured `FeeRule` for that payment method, AND cross-checked against the actually-confirmed bank credit — a real historical defect (a fee-consistent settlement with a mismatched bank credit reaching `MATCHED`) was found via seeded fuzzing and fixed (`app.engines.reconciliation.matching.resolve_single_linked_settlement`, M9).

**How are partial settlements handled?**
Classified by a documented magnitude heuristic (≥85% of payment covered → `under_settlement`, else `partial_settlement`) since the dataset has no structural field distinguishing them — recorded as a dated decision in `CLAUDE.md`, not silently guessed.

**How do you detect false matches?**
Multi-signal scoring (reference/amount/date/fee/merchant/link) plus a non-negotiable ambiguity rule — a candidate that isn't clearly the best match is never silently accepted (`app.engines.reconciliation.relationships`). Measured: 0 incorrect matches across the full dataset (`app.engines.reconciliation.evaluation`).

**How do you explain decisions?**
`app.explainability.builder.build_explanation` assembles one canonical, evidence-first report per exception directly from the real decision objects — financial summary, matching evidence, calculation trace, AI hypotheses vs. verified fact, contradictions, missing evidence, policy, resolution — never a second, independently-worded narrative (M10).

**How do you audit the system?**
An append-only, SHA-256 hash-chained ledger (`app.audit.ledger.AuditLedger`) with no update/delete method at all — structurally, not just by permission. Tamper detection tested against 8+ tamper types (`backend/tests/audit/`).

**What happens when evidence conflicts?**
It's classified SUPPORTED/CONTRADICTED/INSUFFICIENT_EVIDENCE (`app.challenge.contradiction`) and a contradiction sets `PolicyInput.conflicting_evidence = True`, which M5's existing `POLICY-CONFLICT-001` rule routes to mandatory human review — never silently resolved either way.

**What makes this different from existing reconciliation tools?**
Root-cause diagnosis with negative evidence ("why NOT matched"), AI investigation with independent deterministic verification, a policy engine as the sole decision authority, and complete hash-chained auditability — measured against three naive baselines directly (`docs/demo-runbook.md`), not just claimed.

**What is the biggest limitation?**
No live LLM provider or live Razorpay API has ever been exercised in this environment — every result here is against `MockAIProvider` and synthetic fixtures. This is stated plainly in `CLAUDE.md`'s known-risks section, not hidden.

**What would you build next?**
Per `PROJECT_PLAN.md`: a persisted review/approval workflow over HTTP (currently in-memory only), and exercising the real LLM/Razorpay adapters against actual credentials in a controlled environment.
