# End-to-End Pipeline (Milestone 7)

The single orchestrator that turns ReconcileAI's M1–M6 components into one coherent system: `app.services.reconciliation_pipeline.run_reconciliation_pipeline`. Before M7, a full run meant a caller manually invoking M2/M3 and then M6's `run_decision_pipeline` once per exception from a script; M7 is that wiring, done once, reusably.

## What this milestone is not

Not a rewrite of M1–M6. Not a second matching engine, verifier, policy engine, or audit system. `run_reconciliation_pipeline` calls exactly four existing entry points — `ingest_source_directory` (M1), `run_exception_intelligence` (M2+M3), `run_decision_pipeline` (M6, which itself already wires M4's AI investigation, M6's challenge/contradiction check, M2's deterministic verification, M3's risk scoring, and M5's policy/resolution/review) — and adds only sequencing, timing, run/correlation-id bookkeeping, result aggregation, and fail-safe error handling around them.

## Pipeline stages

```
INGEST + NORMALIZE (M1, unchanged)
  -> ingest_source_directory(session, source_dir)
  -> commit
DETERMINISTIC RECONCILIATION + EXCEPTION INTELLIGENCE (M2 + M3, unchanged)
  -> run_exception_intelligence(payments, settlements, bank_txns, refunds, fee_rules)
  -> returns (m2_results, bundles) -- one EvidenceBundle per payment
per exception (each bundle):
  AI INVESTIGATION (M4) -> SELF-CHALLENGE (M6) -> DETERMINISTIC VERIFICATION (M2/M4)
  -> RISK (M3, already computed in the bundle) -> POLICY (M5, the one authority)
  -> RESOLUTION / HUMAN REVIEW (M5) -> AUDIT (M6)
    -> run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, approval_store, run_id=run_id)
AUDIT + PROVENANCE READINESS (M6, unchanged)
  -> ledger.count(), verify_chain(session)
```

There is exactly one decision authority throughout: M5's `evaluate_policy`, called inside M6's `run_decision_pipeline`, called once per exception by this orchestrator. Nothing in `reconciliation_pipeline.py` inspects an AI confidence value, a verifier result, or a risk score to make its own auto-resolve decision — it only reads the `PolicyDecision` each call already produced and tallies it.

## Run ID / correlation ID relationship (Phase 4)

Every call to `run_reconciliation_pipeline` generates one `run_id` (`RUN-{12 hex chars}`). Two audit events bracket the whole run — `RUN_STARTED` and `RUN_COMPLETED` (or `RUN_FAILED`) — with `entity_type="run"`, `entity_id=run_id`, `correlation_id=run_id`, in the *same* `audit_events` table and hash chain as every exception's own events (no second audit system). Every exception processed under that run gets `run_id` threaded into `run_decision_pipeline`'s optional `run_id` parameter (an additive, M7-only extension of M6's `decision_service.py` — its own per-exception `correlation_id` generation and decision logic are unchanged), which stamps `run_id` into that exception's `EXCEPTION_CREATED` audit payload. This preserves exactly the relationship the brief asks for:

```
run (run_id, correlation_id=run_id)
 -> exception (EXCEPTION_CREATED payload carries run_id; own correlation_id=CORR-...)
     -> investigation (AI_INVESTIGATION_* events, same correlation_id)
         -> decision (POLICY_EVALUATED / RESOLUTION_PROPOSED, same correlation_id)
             -> audit (every event above, on one hash chain)
```

Given a `run_id`, `AuditLedger.events_for_correlation(run_id)` returns the run-level bracket; given any exception's `correlation_id`, its own full story is `get_decision_provenance` (M6, unchanged) — and its `EXCEPTION_CREATED` payload's `run_id` field ties it back to the run that produced it.

## Pipeline contract (Phase 3)

`PipelineRunResult` (`app.services.reconciliation_pipeline`), returned by every call:

```json
{
  "run_id": "RUN-...", "status": "completed",
  "started_at": "...", "completed_at": "...", "duration_seconds": 3.7,
  "records_processed": 300, "matched": 219, "exceptions": 300,
  "auto_resolved": 219, "human_review": 67, "blocked": 2, "rejected": 2, "unresolved": 12, "escalated": 0,
  "audit_events": 3486, "provenance_available": true,
  "stage_timings": [{"stage": "ingestion", "seconds": 0.53}, "..."],
  "errors": [], "warnings": []
}
```

Two things worth being explicit about, both real findings from getting this contract right rather than assumed:

- **`exceptions` counts evidence bundles, not "problems."** M3's `build_evidence_bundle` runs once per payment regardless of whether it matched cleanly — this is M3's own existing design (an evidence bundle is useful even for a clean match), not something M7 changed. On the real 300-record dataset, `exceptions == 300` while `matched == 219`; the other 81 aren't a second, uncounted population — they're the same 300 bundles, just filtered by outcome.
- **`blocked` is an explicit alias of `rejected`, not a competing status.** `app.policy.schemas.PolicyDecisionType` has `SAFE_TO_RESOLVE` / `HUMAN_REVIEW` / `REJECTED` / `ESCALATED` / `UNRESOLVED` — no separate `BLOCKED` value. The BLOCK tier's own rules (e.g. `POLICY-VERIFIER-FAIL-001`) produce `REJECTED`. Per the M7 brief's own instruction ("use the repository's actual canonical taxonomy... do not invent competing status values"), `blocked` is computed as exactly the same count as `rejected`, not a second independently-derived bucket. `escalated` is kept in the contract for completeness (the enum value exists) but is not currently reachable from `evaluate_policy`'s logic and is expected to stay `0`.

## Decision authority boundary (Phases 9–14, reaffirmed)

Reused, not re-decided, in this milestone:

- AI (M4) may investigate, retrieve evidence via the fixed tool set, and propose a structured `AIHypothesis` — never approve, override the verifier, override policy, or mark anything resolved by itself.
- The verifier (M2/M4) is authoritative for financial correctness; nothing in `reconciliation_pipeline.py` re-derives or second-guesses a verification result.
- M6's self-challenge rule (a `CONTRADICTED` hypothesis sets `PolicyInput.conflicting_evidence = True`, firing M5's existing `POLICY-CONFLICT-001` rule) is unchanged and still the only path a contradiction takes to influence the outcome.
- M5's `evaluate_policy` is still the single decision authority for every exception, AI-assisted or not — this orchestrator adds no second "if AI confidence > X, auto-resolve" shortcut anywhere.

## Idempotency (Phase 18)

Documented, not assumed — verified via `backend/tests/pipeline/test_pipeline_idempotency.py`:

1. **Ingestion is idempotent** (M1's existing `session.merge`-based upsert, unchanged): re-running against the same source directory never duplicates `Order`/`Payment`/`Settlement`/... rows.
2. **Policy decisions are deterministically reproducible**: given the same (unchanged) input, two full runs produce the identical per-exception `PolicyDecisionType` for every order_id.
3. **Each run is its own, independently-identified run** — the third of the three idempotency behaviors the brief itself allows ("or create a new explicitly identified run with no duplicate financial state"), and the one this architecture actually has: `ResolutionProposal.proposal_id` (`app.policy.schemas`) is randomly generated fresh on every call to `build_resolution_proposal`, so two independent pipeline runs never collide on M5's idempotency key (`exception_id|proposal_id|policy_version`) — each gets its own proposal and its own review request, and both coexist without overwriting one another.

This is safe by construction, not by a dedup check: the pipeline never mutates the source-of-truth financial tables as an *outcome* (they're read-only inputs throughout) and never executes real money movement (CLAUDE.md's explicit non-goal) — so there is no financial state for a rerun to duplicate. Within a *single* run, or across a retry of the *same* `ResolutionProposal` object, M5's own idempotency guarantee is unchanged and still directly tested (`backend/tests/audit/test_adversarial_m6.py::test_12_duplicate_review_request_creation_is_idempotent`, `backend/tests/policy/`).

## Failure handling (Phase 19)

Two failure scopes, handled differently, both fail-safe:

- **Stage-level failure** (ingestion or reconciliation/exception-intelligence raises): the whole run is marked `status="failed"`, a `RUN_FAILED` audit event is recorded (best-effort — if even that append fails, the failure is still reported, never silently swallowed), and `auto_resolved`/`human_review`/etc. all stay at their zero defaults. No partial "completed" result is ever returned for a run that didn't finish its deterministic stages.
- **Per-exception failure** (`run_decision_pipeline` raises for one bundle, e.g. a bug or an unexpected data shape): the session is rolled back, a warning is recorded (`"{exception_id} ({order_id}): decision pipeline failed safely, skipped: {error}"`), and processing continues with the next exception. The failed exception is simply **absent** from `decisions` — never present with a fabricated or default-safe outcome, and certainly never `SAFE_TO_RESOLVE`.
- **AI provider failure** (a `ProviderError` on every call, simulating a total outage): unchanged from M4 — `app.ai.controller.investigate` already degrades to zero hypotheses tested, and `decide_final_outcome([])` already returns `HUMAN_REVIEW`. Verified end-to-end in `test_pipeline_failure_handling.py::test_provider_failure_degrades_to_human_review_never_auto_resolve`: every AI-routed exception under a fully failing provider still reaches a non-`SAFE_TO_RESOLVE` policy decision.
- **Audit persistence failure**: unchanged from M6 (Phase 15) — `AuditLedger.append` rejects a malformed payload before ever touching the session, and a failed `commit()` rolls back whatever was staged in that transaction together.

## Observability (Phase 23)

`PipelineRunResult.stage_timings` records wall-clock seconds for `ingestion`, `reconciliation_and_exception_intelligence`, and `decision_pipeline` (the last one dominates, since it's where all per-exception AI/verification/policy/audit work happens). No distributed tracing infrastructure was added — a plain list of `{stage, seconds}` dicts, per the brief's own "a simple structured run summary is sufficient for MVP" instruction.

## One command, no manual steps (Phase 24)

```
python scripts/run_reconciliation.py [--dataset data/synthetic/seeds] [--db path/to/db]
```

Runs ingestion through audit/provenance readiness in one process, printing the Phase 25 demo output (run summary, decision distribution, processing metrics, audit integrity, then one showcased exception's full AI hypothesis / challenge / contradiction / verifier / policy / decision / provenance trail — preferring a real contradicted-hypothesis case when one exists in the run). Uses an isolated database under `scripts/` by default, never a shared dev DB, and cleans it up on exit.

## What remains for M8

No dashboard (Phase 26, explicit exclusion). No API layer (Phase 27) — but the orchestrator's own function boundary (`run_reconciliation_pipeline(session, source_dir, provider, ledger, approval_store) -> PipelineRunResult`) is already the natural seam a future FastAPI layer would wrap with `POST /api/runs`, `GET /api/runs/{run_id}`, `GET /api/exceptions`, `GET /api/exceptions/{id}`, `GET /api/exceptions/{id}/provenance`, `GET /api/audit/status` — none of which exist yet, since no caller needs them over HTTP until the frontend milestones. No live Razorpay integration. No new AI autonomy — the AI layer's capabilities and boundaries are exactly M4's, unchanged.
