# Final Validation (Milestone 16)

The single, complete judge-evidence package. Every numerical claim below names its exact source in the repository — code, test, or script — so it can be independently re-derived, not just read.

## 1. What ReconcileAI does

Automates the investigation of multi-source payment reconciliation exceptions — matching payments against settlements, bank credits, and refunds, classifying discrepancies, and routing them to the right outcome — while keeping the actual financial decision behind deterministic verification and policy controls, never behind an AI model's own judgment.

## 2. Why the problem matters

Finance teams reconcile records from multiple sources (payment gateway, settlement export, bank statement, internal order system, refund records) that legitimately disagree because of fees, timing, partial settlements, duplicates, and mangled references. A wrong automated decision either misses real money or wrongly clears something that needed a human's judgment — and a system that can't explain *why* it decided something is not auditable by a finance controller.

## 3. Architecture

```
Sources → Provider Adapters → Validation + Normalization → Deterministic Reconciliation
        → Exception Intelligence → AI Investigation → Self-Challenge → Verification
        → Risk + Policy → Decision → Audit + Explanation → Priority Queue → API → Frontend
```

Every stage is a real, tested module: `app.adapters` (M14), `app.schemas.records`/`app.engines.normalization` (M1), `app.engines.reconciliation` (M2), `app.engines.exceptions`/`app.engines.risk` (M3), `app.ai` (M4), `app.challenge` (M6), `app.engines.reconciliation.verification`/`app.ai.verifier` (M2/M4), `app.policy` (M5), `app.audit`/`app.explainability` (M6/M10), `app.prioritization` (M11), `app.api` (M8), `frontend/` (M12). See `docs/architecture.md` for the full per-milestone addenda.

## 4. AI role

AI investigates only the residual exceptions M3's deterministic triage cannot already resolve — 74/300 (24.7%) on the reference dataset (`app.ai.routing`, M4). It proposes a structured hypothesis from a closed, 12-value type enum (`app.ai.schemas.HypothesisType`) and can only cite record IDs that actually exist (`app.ai.verifier.validate_grounding`).

## 5. Why AI is NOT the final authority

`app.policy.engine.evaluate_policy` is the sole decision authority (unified via `app.services.decision_service`, M6); it never reads `AIHypothesis.confidence` or `recommended_action` (`app.ai.policy`, dated decision, M4/M5). Proven directly, not just by convention: `backend/tests/adversarial/test_ai_misleading_evidence.py` (5 cases), `test_policy_manipulation.py`, and this milestone's own `backend/tests/adversarial/test_m16_final_safety_invariants.py` (items 1 and 5 — extreme, manipulated AI confidence never forces `SAFE_TO_RESOLVE`).

## 6. Deterministic verification

Every AI hypothesis is independently re-derived with real Decimal arithmetic before anything is trusted (`app.ai.verifier.verify_hypothesis`, dispatching to the same M2/M3 checkers used everywhere else — never a second implementation). `backend/tests/adversarial/test_m16_final_safety_invariants.py::test_02` confirms every hypothesis outcome actually carries a real `verifier_result`, not an assumed one.

## 7. Policy layer

Four-tier precedence — BLOCK > MANDATORY_APPROVAL > RISK > AUTO_ELIGIBILITY (`app.policy.engine`, M5, dated decision) — evaluated top-to-bottom, first tier that fires decides. Contradictory evidence (`POLICY-CONFLICT-001`) and missing critical evidence both route to mandatory review or unresolved, never auto-resolve (`test_m16_final_safety_invariants.py::test_06`/`test_07`).

## 8. Audit / provenance

An append-only, SHA-256 hash-chained ledger (`app.audit.ledger.AuditLedger`) with no update/delete method at all — structurally absent, not merely unauthorized. Tamper detection tested against 8+ tamper types (`backend/tests/audit/`). Full decision provenance reconstructable from an exception ID alone (`app.audit.provenance.get_decision_provenance`, M6; `app.explainability`, M10).

## 9. Competitive baseline

Measured directly against the real 300-record dataset (`scripts/evaluate_competitive_baselines.py`, M13):

| Approach | Precision | Recall | Result |
|---|---|---|---|
| Exact-ID matching only | 1.00 | 0.89 | Misses reformatted references |
| Amount-only matching | 0.96 | 0.83 | 10 false matches |
| Naive fuzzy, no verification gate | — | — | **14.67% unsafe auto-resolution rate** |
| ReconcileAI | **1.0000** | **1.0000** | **0.0000% unsafe auto-resolution rate** |

## 10. Safety metrics

Live, per-run, ground-truth-compared (`GET /runs/{run_id}/safety-metrics`, `app.services.safety_metrics.compute_safety_metrics`, M15) — never hardcoded. Reports `available=false` (never a fabricated number) when a run's dataset has no `ground_truth.json`.

## 11. Golden adversarial example

The real ₹9.83 fee-mismatch case (expected settlement 7673.60, bank-confirmed 7663.77): AI proposes a card-fee explanation → deterministic verification finds the actual fee rule doesn't produce that residual → contradiction recorded → policy requires `HUMAN_REVIEW` via `POLICY-CONFLICT-001` → full audit trail. Reproduced this milestone via the full regression suite (`tests/audit/test_evaluation_m6.py`) and via the browser E2E smoke test (`frontend/e2e/smoke.spec.ts`).

## 12. Dataset description

300 ground-truthed synthetic records (`data/synthetic/generator.py`, deterministic, fixed seed), 14 exception-taxonomy categories (`shared/taxonomy.ExceptionCategory`), 5 adversarial cases. Audited (`scripts/audit_dataset.py`, M13): all IDs unique, zero dangling references.

## 13. Performance results

Re-measured this milestone (`scripts/benchmark_full_pipeline_m16.py`), synthetic data, local environment, MockAIProvider — no production SLA implied:

| Records | Reconcile + exception intelligence | rec/s |
|---|---|---|
| 300 | 0.025s | ~11,769 |
| 1,000 | 0.103s | ~9,727 |
| 5,000 | 0.519s | ~9,634 |
| 10,000 | 1.262s | ~7,927 |

Full decision pipeline (AI + verification + policy + audit per exception, MockAIProvider):

| Records | Total | rec/s |
|---|---|---|
| 300 | 2.11s | ~142 |
| 1,000 | 7.59s | ~132 |
| 2,000 | 15.89s | ~126 |

Both scale roughly linearly — no accidental O(n²) found. The full decision pipeline was not run to 10,000 records repeatedly (each exception does real AI-investigation + audit-append work, making that impractical for a demo-scale benchmark) — its per-unit cost is already established at 300–2,000 and shows no super-linear growth.

## 14. Provider integration status

Read-only Razorpay adapter (`backend/app/adapters/`, M14) — `fixture` mode (default, all automated tests), `mock` mode (test-controlled), `live` mode (real HTTP, bounded retry/rate-limit handling, **never exercised against a real Razorpay API in this environment** — no real credentials exist). See `docs/provider-adapters.md`.

## 15. Known limitations

No live LLM provider exercised. No live Razorpay network integration exercised. No persisted review/approval workflow (in-memory only, `ApprovalWorkflowStore`). Scalability demonstrated only around the 300-record demo scope (and up to 10,000 for the deterministic stages alone) — see `docs/production-readiness.md` for the full READY/PARTIAL/NOT IMPLEMENTED matrix. No concurrent-write test (concurrent READS are tested this milestone; `RunRegistry`/SQLite were never designed for concurrent writers).

## 16. What is genuinely implemented

Deterministic reconciliation, exception classification, AI investigation with grounding validation, self-challenge/contradiction detection, independent Decimal-exact verification, four-tier policy engine, hash-chained audit ledger, evidence-first explainability, deterministic priority queue, a production-style read-only API, a React frontend, a read-only provider adapter, 125+ adversarial tests, and now (M16) a formal 20-item final safety invariant suite, concurrency/replay hardening, provider-failure simulation, and a passing browser E2E smoke test.

## 17. What is fixture/mock only

The Razorpay adapter's `live` mode (never network-tested). `MockAIProvider` is what every test and the default demo run against — `GeminiProvider`/`OpenAICompatibleProvider` exist (`app.ai.provider`) but have never been exercised against a real vendor API in this environment.

## 18. What has NOT been claimed

"Production-ready" (the phrase does not appear anywhere in this repository, verified by repository-wide grep, M15/M16). "Fully scalable." "Guaranteed" correctness. "100% accurate in production." "Enterprise-ready." Every accuracy/safety figure is explicitly scoped ("on the 300-record synthetic evaluation," "with MockAIProvider," "fixture-mode," "not network-tested").

## 19. Exact commands to reproduce validation

```bash
# Backend full suite
cd backend && python -m pytest -q

# Frontend full suite
cd frontend && npm test

# Browser E2E smoke test (requires both servers running -- see below)
cd frontend && npm run test:e2e

# Competitive evaluation
python scripts/evaluate_competitive_baselines.py

# Dataset audit
python scripts/audit_dataset.py

# Golden/full pipeline demo (terminal output, no UI needed)
python scripts/run_reconciliation.py

# Provider fixture flow
cd backend && python -m pytest tests/adapters/test_end_to_end_fixture_pipeline.py -q

# Performance benchmark
python scripts/benchmark_full_pipeline_m16.py

# Full demo (two terminals)
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev   # then open http://localhost:5173
```

## 20. Test counts

See `CLAUDE.md`'s M16 entry for the exact, final, re-confirmed backend/frontend/E2E test counts as of this milestone.
