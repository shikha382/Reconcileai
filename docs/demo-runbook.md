# Demo Runbook (Milestone 13, updated Milestone 15 and 16)

This is the single judge-facing document: what the problem is, what ReconcileAI does about it, how to run the demo, what to say, what the numbers actually mean, and what to do if something goes wrong. Every number below was measured directly against the real 300-record dataset — none is invented, none is carried forward from an earlier milestone without being re-verified. See `docs/evaluation.md` for the full methodology, `docs/three-minute-demo.md` for a timed script, `docs/judge-qa.md` for prepared Q&A, and `docs/final-validation.md` (Milestone 16) for the complete, source-cited judge evidence package.

## 1. What problem exists

Finance teams receive payment, settlement, bank, and refund records from multiple sources that legitimately disagree — because of settlement timing, fee deductions, refunds, partial/aggregated/split settlements, duplicate or missing records, and mangled reference IDs. Manual reconciliation of these disagreements is slow, hard to audit, and risky: a wrong match either misses real money or wrongly clears an exception that should have been investigated.

## 2. What ReconcileAI does

**"ReconcileAI automates the investigation of multi-source payment reconciliation exceptions while keeping financial decision authority behind deterministic verification and policy controls."**

It is not a chatbot, not an anomaly detector, and not "AI that reconciles your books." It is a pipeline: deterministic reconciliation finds and classifies exceptions → AI investigates the ones that are genuinely ambiguous → a deterministic verifier checks the AI's claim against real financial arithmetic → a policy engine — not the AI — decides `auto-resolve` / `human review` / `blocked` / `unresolved` → every step is written to a tamper-evident audit ledger.

## 3. Architecture (verified this milestone)

```
DATA → INGESTION → NORMALIZATION → RECONCILIATION → EXCEPTION DETECTION
     → AI INVESTIGATION → SELF-CHALLENGE → DETERMINISTIC VERIFICATION
     → RISK → POLICY → DECISION → AUDIT → EXPLANATION → PRIORITY
     → API → FRONTEND
```

Every arrow above is a real, tested module boundary (`app.ingestion`, `app.engines.normalization`, `app.engines.reconciliation`, `app.engines.exceptions`, `app.ai`, `app.challenge`, `app.engines.risk`, `app.policy`, `app.audit`, `app.explainability`, `app.prioritization`, `app.api`, `frontend/`) — confirmed by re-reading M1–M12's own architecture addenda in `docs/architecture.md` and re-running the full regression suite before any M13 change (see §14).

## 4. Demo setup

```bash
# terminal 1 — backend (fresh process = fresh in-memory run registry)
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — frontend (proxies /health, /runs, /exceptions to the backend, no CORS config needed)
cd frontend
npm install   # first time only
npm run dev
# open http://localhost:5173
```

After dependencies are installed, no internet access is required — the dataset is local (`data/synthetic/seeds`), and the AI provider used throughout is `MockAIProvider` (fully deterministic, zero network calls). This is stated plainly, not hidden: every demo screen that shows an "AI hypothesis" is showing a real, structured output from this deterministic mock provider, not a live LLM vendor call. See `docs/ai-controller.md`/`docs/ai-design.md` for the real-provider adapters (`GeminiProvider`/`OpenAICompatibleProvider`), which exist but are not exercised in this environment (no API key configured). The topbar's `DEMO · SYNTHETIC DATA` badge (and the System Health page's Data Sources table) make this explicit on every screen, not just here.

**Milestone 16 finding, fixed:** a real bug was found while building this milestone's browser E2E smoke test — navigating (or refreshing) directly to `/runs`, `/health`, or `/exceptions` in a browser returned raw backend JSON instead of the React app, because Vite's dev-server proxy matched those paths as API prefixes even for full-page HTML navigations, not just `fetch()` calls. Fixed in `frontend/vite.config.ts` (a `bypass` check on the `Accept: text/html` header lets a real page load through to `index.html`; a real `fetch()` call, which never sends that header, still proxies normally). Confirmed fixed both via `curl -H "Accept: text/html"` and the full 14-step Playwright E2E test (`frontend/e2e/smoke.spec.ts`, `npm run test:e2e`) passing end-to-end, including a mid-demo page refresh.

### Demo reset (Phase 8)

There is no "Reset Demo" button in the UI, and this was a deliberate choice, not an oversight: the public API has no financial-record mutation, force-resolve, refund, payout, or approval-bypass endpoint. The safest existing reset is an explicit local development operation that deletes only the demo SQLite file:

```bash
# stop uvicorn (Ctrl+C), then:
rm backend/reconcileai.db   # never touches Razorpay or any external system -- purely local SQLite
uvicorn app.main:app --host 127.0.0.1 --port 8000   # fresh process = empty in-memory RunRegistry, clean DB
```

Then click **Start reconciliation** on the Runs page again — a brand-new run against the identical, deterministic dataset.

## 5. Demo golden path (Phase 20's 15-step checklist)

1. **Setup:** `git clone`/open the repo, `cd backend && pip install -r requirements.txt`, `cd frontend && npm install` (first time only).
2. **Start backend:** `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000`.
3. **Start frontend:** `cd frontend && npm run dev`, open `http://localhost:5173`.
4. **Run/reset demo:** Runs page → **Start reconciliation** (or reset per above first, for a guaranteed-clean state).
5. **Open dashboard:** Overview — "300 records processed," the hero **Unsafe Auto-Resolution Rate** metric, the full decision breakdown.
6. **Select the safe-block scenario:** Work Queue → set **Decision** to **Blocked**; the backend returns the rejected fee traps.
7. **Open golden case:** open a `Fee Mismatch` row and confirm its unexplained residual is ₹9.83.
8. **Explain AI hypothesis:** AI Investigation section — read the claim aloud, note the confidence is advisory only.
9. **Show contradiction:** the dedicated contradiction callout — "actual fee rule does not explain the residual."
10. **Show verification:** point out this is independent Decimal arithmetic, not a second AI opinion.
11. **Show policy:** the named BLOCK-tier rule (`POLICY-VERIFIER-FAIL-001`) and its reason.
12. **Show blocked decision:** the Final Decision badge — `BLOCKED`, plainly stated as the policy engine's decision, not the AI's. Explain that no financial action or review request is created for this rejected proposal.
13. **Show audit:** Audit & Provenance section — the real timeline and chain-validity confirmation.
14. **Show competitive advantage:** open **Why ReconcileAI** (`/about`) — the cited M13 baseline table.
15. **Show metrics:** back to Overview, or `docs/evaluation.md` for the full per-layer numbers.

**"IF DEMO BREAKS"** — see §13 below.

## 6. Golden demo case

The adversarial `fee_mismatch` record already named in M6/M10's own documentation: expected settlement value 7673.60, actual bank-confirmed value 7663.77, a **₹9.83** residual. The AI's fee-adjustment hypothesis is deterministically contradicted (the configured fee rule does not produce that residual), so the BLOCK tier returns `REJECTED` via `POLICY-VERIFIER-FAIL-001` — never auto-resolved and with no downstream financial action. Because exception IDs are randomly generated per run, there is no fixed ID to search for. In Work Queue, set **Decision** to **Blocked**, then open a `Fee Mismatch` row and confirm the detail page shows an unexplained residual of ₹9.83. This exact case is synthetic and reproducible; it is not a real merchant transaction.

## 7. Metrics (re-measured 2026-08-29, this milestone)

| Metric | Value | Source | Scope |
|---|---|---|---|
| Records processed | 300 | `run_reconciliation_pipeline` | Full dataset |
| Auto-resolved | 219 | Real run | Full dataset |
| Human review | 67 | Real run | Full dataset |
| Blocked/rejected | 2 | Real run | Full dataset |
| Unresolved | 12 | Real run | Full dataset |
| **Unsafe (false) auto-resolution rate** | **0.0000 (0/300)** | `tests/audit/test_evaluation_m6.py` | Full dataset, this run |
| Contradiction detection rate | 0.2067 (62/300) | Same test | Full dataset |
| Reconciliation precision/recall/F1 | 1.0000 / 1.0000 / 1.0000 | `app.engines.reconciliation.evaluation.evaluate` | Full 300-record set, controlled/synthetic |
| Exception classification accuracy | 1.0000 (macro-F1 1.0000, 14 categories) | `tests/adversarial/test_classification_metrics.py` | Full dataset |
| Root-cause status accuracy | 1.0000 | `app.engines.exceptions.evaluation.evaluate_exceptions` | Full dataset |
| Adversarial safety invariant matrix | 10/10 PASS, 0 critical failures | `tests/adversarial/test_safety_matrix.py` | 10 hand-built adversarial scenarios |
| Audit chain validity | Valid, 3,486 events | `verify_chain` | Every run of the real orchestrator |
| Throughput | 300 records in ~3.9s (~77 records/sec) | Measured this milestone | MockAIProvider — **not production LLM latency** |
| Backend regression | see §14 | pytest | Full suite |
| Frontend regression | 22/22 passing | vitest | Full suite |

**All "100%"/"1.0000" figures above are on this project's own 300-record controlled evaluation dataset** — never claimed as a general production accuracy guarantee. See `docs/evaluation.md` for the full breakdown, including the distinction between matching correctness and decision safety (§13 there).

## 8. Safety story

AI proposes → deterministic verifier checks the claim against real Decimal arithmetic → policy engine (not the AI) decides → human reviews when policy requires it → every step is on an append-only, hash-chained audit ledger. The unsafe/false auto-resolution rate is **0.0000** on the full dataset, re-measured this milestone, not assumed. Two real historical safety defects (documented in `CLAUDE.md`'s M4 and M9 entries) were found and fixed via this exact discipline earlier in the project — the system's safety story is backed by a track record of catching its own gaps, not just a clean test run.

## 9. Competitive differentiation

Only claims that exist in this repository, measured directly this milestone (`scripts/evaluate_competitive_baselines.py`):

| Baseline | Status | Result on this dataset |
|---|---|---|
| A — raw exact-ID matching | Implemented & measured | precision 1.00, **recall 0.89** (misses reference-mismatch/split cases entirely) |
| B — naive amount-only matching | Implemented & measured | precision 0.96, recall 0.83, **10 false matches** (duplicate/aggregate amount collisions) |
| C — naive fuzzy matching, no verification gate | Implemented & measured | auto-resolves all 300, **14.67% unsafe auto-resolution rate (44/300 wrong)** |
| D — LLM-only reconciliation | **Proxy measurement**, not a separate pipeline | see note below |
| E — ReconcileAI (M2 deterministic layer alone) | Implemented & measured | precision/recall/F1 **1.0000**, incorrect-auto-resolution rate **0.0000** |

Baseline D note: there is no second, independent "LLM decides everything" implementation in this repository — building one would itself be the unsafe pattern this project argues against. Instead, this milestone measured a proxy directly from real system output: of the 74 real cases routed to AI investigation, the AI's own self-reported recommendation was never `SAFE_TO_RESOLVE` on this dataset (the M4 triage only routes already-hard residual cases to AI in the first place, so this is not a blanket "AI is always cautious" claim). The real, historical evidence for AI-trust risk is the two dated defects in `CLAUDE.md`'s M4/M9 entries, where a narrower verifier gap (before it was fixed) *did* let an AI-adjacent shortcut produce a false auto-resolution — and Baseline C above shows concretely what "trust a plausible signal with no verification gate" costs on this exact dataset (14.67% wrong).

Eleven other real, repository-backed differentiators beyond raw matching: AI self-challenge, contradiction detection, policy-controlled outcomes, evidence-first explanations, a human-review boundary the AI cannot cross, complete hash-chained audit provenance, a deterministic (never LLM-driven) priority queue, adversarial safety testing (125 M9 tests + this milestone's additions), and reproducible evaluation (§10).

## 10. Reproducibility

The full pipeline was run three independent times against the same dataset this milestone. Results:

- `run_id`, `proposal_id`, `review_id` differ every time (by design — see `CLAUDE.md`'s M7 dated decision on why each run is its own independently-auditable record).
- Every one of the 300 exceptions' **category, final policy decision, and financial impact were byte-identical** across all runs.
- **Audit event count was exactly 3,486 in all three runs** — fully deterministic, not just "close."
- The decision distribution (219 auto-resolved / 67 human review / 2 blocked / 12 unresolved) was identical across all runs.

## 11. Financial invariants (re-verified this milestone)

All of the following are enforced by existing M1–M9 code and re-confirmed passing this milestone (backend regression, §14): payment amounts are never silently altered (Decimal-typed, immutable once ingested); a verified fee always corresponds to its configured `FeeRule`, cross-checked against the actually-confirmed bank credit (the exact M9 fix); settlement net amounts must reconcile mathematically before `MATCHED` is ever declared; two refunds can never claim the same debit transaction twice (the other M9 fix); negative amounts are rejected at the Pydantic schema boundary (M1); currency is allowlist-validated (M1); every residual/decomposition calculation is Decimal-exact end-to-end (no float, anywhere, in a money path).

## 12. Failure injection (re-confirmed this milestone)

| Scenario | Existing coverage | Result |
|---|---|---|
| Missing settlement/bank record | `tests/adversarial/test_missing_data.py` | Routes to `UNRESOLVED`, never a false match |
| Corrupted/duplicated ID | `tests/adversarial/test_identifier_manipulation.py`, `test_duplication_replay.py` | Blocked/human review, never silent accept |
| Wrong amount / wrong fee | `tests/adversarial/test_amount_manipulation.py`, `test_fee_manipulation.py` | Caught by verification, human review or blocked |
| Duplicate refund | `tests/adversarial/test_refund_manipulation.py` | Caught (this is the real M9 refund-double-claim fix) |
| Contradictory evidence | `tests/adversarial/test_contradictory_data.py`, `test_ai_misleading_evidence.py` (5 cases) | Contradiction recorded, never trusted |
| AI provider unavailable | `tests/pipeline/test_pipeline_failure_handling.py::test_provider_failure_degrades_to_human_review_never_auto_resolve` | Degrades safely to human review |
| Ingestion/matching-stage crash | `test_pipeline_failure_handling.py` (2 tests) | Whole run marked `failed`, never a partial false-completed |
| One exception's decision-pipeline crash | Same file | That exception is skipped and warned, never silently counted resolved |
| Malformed API request | `tests/api/test_security.py`, `tests/api/test_m13_security_audit.py` (new, this milestone) | Clean structured 4xx, no stack trace, no leak |
| Audit corruption | `tests/audit/*` (8+ tamper types), `scripts/tamper_demo.py` | Chain reports INVALID with the exact reason |

No scenario above produces a silent incorrect auto-resolution.

## 13. Demo failure fallback

| If this happens | Do this |
|---|---|
| Backend fails to start | Check `backend/reconcileai.db` isn't locked by another process; delete it (it's a fresh-start file, not source data) and retry `uvicorn app.main:app`. |
| Frontend fails to start | `cd frontend && npm install` again; confirm Node ≥18. |
| Browser refreshes mid-demo | Nothing is lost server-side — reopen `/runs`, pick the same run from the dropdown (`RunPicker`), continue. |
| A run takes longer than expected | ~4 seconds is normal for 300 records with MockAIProvider; if it hangs, check the backend terminal for a traceback — the pipeline is fail-safe (marks the run `failed`, never a silent partial success). |
| The "golden" P0 exception can't be found | Filter Work Queue by category `fee_mismatch`; any of the 18 real fee-mismatch cases (or the 2 true adversarial ones) makes the same safety point. |
| No internet access | Not required — dataset is local, AI provider is `MockAIProvider` (zero network calls). |
| API unavailable entirely | Fall back to `python scripts/run_reconciliation.py`, which runs the same real pipeline and prints the full decision/contradiction/policy/audit trail to the terminal — no UI required. |

## 14. Regression (updated Milestone 15, 2026-08-29)

M13: backend 709 → 731 (22 new tests). M14: 731 → 823 (92 new tests: the provider adapter layer). M15: 823 → see `CLAUDE.md`'s M15 entry for the exact final count (a new `GET /runs/{run_id}/safety-metrics` endpoint plus the frontend polish in this milestone). Frontend: 16 → see `CLAUDE.md`'s M15 entry (the hero metric, the new `/about` page, and P0 row emphasis each added their own tests). Zero regressions in either suite across all three milestones.

## 15. Known limitations

Carried forward, unchanged, from M1–M12 (see each milestone's own CLAUDE.md entry): `RunRegistry`/`ApprovalWorkflowStore` are in-memory/process-lifetime; no live LLM provider has been exercised; no approval/review-decision HTTP endpoint or UI exists yet; `X-Actor-Type`/`X-Actor-Id` headers are a test/demonstration authorization seam, not real authentication; the explanation/queue endpoints omit the literal `FeeRule` ID over HTTP since `RunRegistry` doesn't carry raw pipeline context. New from this milestone: Baseline D (§9) is a proxy measurement over this project's own AI output, not an independently-built LLM-only pipeline — building one was deliberately out of scope (it would be the exact unsafe pattern this project argues against); the competitive-baseline script (`scripts/evaluate_competitive_baselines.py`) is a standalone evaluation tool, never wired into the real reconciliation path.

## 16. Why not just use Razorpay reports?

Razorpay's own payment/settlement reports are a real, accurate data source — this project does not claim otherwise. The problem ReconcileAI addresses starts *after* those reports exist: a finance team must reconcile that data against internal orders, bank credits, refunds, and fee rules from multiple systems, and explain every discrepancy defensibly. ReconcileAI is the cross-source investigation and control layer sitting on top of exactly that kind of source data (modeled here as the synthetic Payment/Settlement/BankTransaction/Refund/FeeRule tables) — not a replacement for, or a criticism of, any payment provider's own reporting.

## 17. Live integration decision

No real Razorpay credentials, no production payment data, and no live financial mutation exist anywhere in this codebase (verified directly, §7/§9 of `docs/frontend.md` and `tests/api/test_security.py::test_no_financial_mutation_endpoints_exist`). **Update, Milestone 14:** a read-only Razorpay adapter (`backend/app/adapters/`, see `docs/provider-adapters.md`) was subsequently built — proving the reconciliation/investigation/verification/policy/audit core is source-agnostic, since it operates on the same `Payment`/`Settlement`/`BankTransaction`/`Refund`/`FeeRule` shapes regardless of origin. It defaults to, and every automated test uses, `PROVIDER_MODE=fixture` (realistic synthetic Razorpay-shaped data, never real values); its `live` mode has never been exercised against a real Razorpay API in this environment, and no real credentials are checked in. The demo itself still runs entirely on the deterministic 300-record synthetic dataset — the adapter's existence does not change that. **Synthetic, deterministic data is used throughout for reproducible evaluation** — stated plainly, not hidden.

## Claim vs. proof matrix (Phase 24)

| Claim | Implementation | Test | Evidence |
|---|---|---|---|
| AI cannot bypass policy | `app.policy.engine.evaluate_policy` is the sole decision authority (M5, unified via M6's `decision_service`) | `tests/adversarial/test_ai_misleading_evidence.py` (5 cases), `test_policy_manipulation.py` | 0/300 false auto-resolutions, re-measured this milestone |
| AI confidence never overrides verification | `app.ai.policy`/`app.ai.verifier` never read `AIHypothesis.confidence` for the real decision | `test_policy_manipulation.py::test_ai_confidence_never_affects_the_policy_decision` (parametrized) | Passing |
| A duplicated refund cannot double-claim a debit | `verify_refund_consistency` tracks claimed debit IDs (M9 fix) | `tests/adversarial/test_refund_manipulation.py` | Passing, real historical fix |
| A fee-consistent settlement with a mismatched bank credit is not auto-resolved | `resolve_single_linked_settlement` cross-checks bank credit vs. net amount (M9 fix) | `tests/adversarial/test_fee_manipulation.py`, `test_fuzz.py` (seed 90210) | 0/60 unsafe after the fix (was 7/60 before) |
| Priority/queue building cannot alter a decision | `app.prioritization` never calls `evaluate_policy`/`verify_hypothesis` | `tests/prioritization/test_decision_invariance.py` | 4/4 passing |
| The frontend cannot mutate any financial state | No non-GET route exists except `POST /runs` (starts a new run, mutates nothing existing) | `tests/api/test_security.py::test_no_financial_mutation_endpoints_exist`, `frontend/src/test/ExceptionDetailPage.test.tsx` | Passing both sides |
| An invalid exception-state transition is rejected | `app.policy.state_machine.transition` | `tests/adversarial/test_m13_decision_authority_audit.py` (new, this milestone) | 6/6 invalid transitions rejected |
| The audit chain detects tampering | SHA-256 hash chain, `verify_chain` | `tests/audit/*` (8+ tamper types), `scripts/tamper_demo.py` | All detected |
| Naive automation is measurably less safe | Baselines A–C, implemented standalone | `scripts/evaluate_competitive_baselines.py` | Baseline C: 14.67% unsafe rate vs. ReconcileAI's 0.0000% |
| Results are reproducible | Same pipeline, 3 independent runs | Manual verification, this milestone (§10) | 3,486 audit events and identical decisions across all 3 runs |
| Provider-sourced (adapter) data gets the exact same safety guarantees as file-sourced data | `app.adapters.pipeline.ingest_from_provider` feeds the identical `ingest_records`/M2–M6 path | `tests/adapters/test_m9_regression.py`, `test_end_to_end_fixture_pipeline.py` (Milestone 14) | Both real historical M9 defenses hold; the refunded adapter-sourced payment correctly never reaches `SAFE_TO_RESOLVE` |
| The UI never claims a data source is LIVE unless it actually is | `GET /sources/status` reports mode from real `ProviderSettings`, never hardcoded | `tests/api/test_m14_sources_status.py::test_sources_status_never_reports_live_without_real_credentials` | Passing |
