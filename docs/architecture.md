# Architecture

## Repository state at time of writing

Empty except documentation (`RECONCILEAI_CONTEXT_PACK.md`, `CLAUDE.md`, `PROJECT_PLAN.md`, `docs/`). **Decision: build from scratch.** There is no existing code to reuse or migrate.

## Components

- **Frontend** — React + TypeScript + Vite, Tailwind, shadcn/ui components where they save time, Recharts for the dashboard/VaR charts.
- **Backend API** — Python, FastAPI, Pydantic models for every request/response and every LLM-structured-output schema.
- **Database** — SQLite for development and the hackathon demo (file-based, zero-ops); schema written to be Postgres-compatible so a swap is a connection-string change, not a rewrite, if ever justified.
- **Reconciliation Engine** — normalization + exact + normalized-reference matching (deterministic, no LLM).
- **Candidate Matching Engine** — fuzzy candidate generation (RapidFuzz) + multi-field scoring.
- **Exception Engine** — taxonomy classification + "Why NOT Matched" negative-evidence recording.
- **AI Investigation Agent** — evidence-gathering tool orchestration + structured hypothesis generation, behind the `LLMProvider` abstraction (`docs/ai-design.md`).
- **Verification / Sandbox** — deterministic re-derivation of the AI's claimed relationship using `Decimal` arithmetic; the actual safety gate.
- **Confidence Engine** — deterministic scoring from measurable signals (never LLM-assigned).
- **Policy Engine** — declarative rule set deciding `auto_resolve` / `human_review` / `unresolved` / `blocked`.
- **Audit System** — append-only, SHA-256 hash-chained event log.
- **Metrics / Evaluation Engine** — runs the pipeline against `ground_truth.json`, emits precision/recall/F1 and the safety metrics (`docs/evaluation.md`).
- **Synthetic Data Generator** — fixed-seed, produces the ground-truthed dataset (scaled from a small dev fixture up to 300 records — see `PROJECT_PLAN.md`).

## Data flow (the 8-stage pipeline)

```
INGEST
  → NORMALIZE
  → EXACT MATCH                 (deterministic)
  → FUZZY / CANDIDATE MATCH     (deterministic, RapidFuzz)
  → EXCEPTION DETECTION         (deterministic, taxonomy + Why-Not-Matched)
  → EVIDENCE COLLECTION         (deterministic tool calls, logged)
  → AI HYPOTHESIS GENERATION    (LLM, structured output only)
  → DETERMINISTIC VERIFICATION  (Decimal arithmetic, independent of LLM)
  → CONFIDENCE SCORING          (deterministic, signal-based)
  → POLICY DECISION             (declarative rules)
  → AUTO-RESOLVE | HUMAN REVIEW | UNRESOLVED | BLOCKED
  → AUDIT TRAIL                 (every step above logs an event)
  → FINANCIAL REPORT
```

Only the "AI HYPOTHESIS GENERATION" stage touches an LLM. Every stage before and after it is plain deterministic code, independently testable without any model access.

## Folder structure (design — not yet created on disk)

```
reconcileai/
  backend/
    app/
      main.py
      config.py                 # env-driven settings, incl. LLM_PROVIDER/LLM_MODEL
      db/
        models.py                # SQLAlchemy models per docs/data-model.md
        session.py
      schemas/                   # Pydantic request/response + AI structured-output schemas
      engines/
        normalization.py
        exact_match.py
        candidate_match.py
        scoring.py
        exception_detection.py
        why_not_matched.py
        confidence.py
        policy.py
      ai/
        provider.py               # LLMProvider abstraction + implementations
        tools.py                  # agent evidence-gathering tools
        agent.py                  # orchestration + hypothesis validation gate
      verification/
        verify.py                 # Decimal-based re-derivation checks
      audit/
        audit_log.py
        hash_chain.py
      evaluation/
        metrics.py
        run_eval.py
      api/
        routes_ingest.py
        routes_reconciliation.py
        routes_exceptions.py
        routes_audit.py
        routes_metrics.py
    tests/
      unit/
      integration/
      fixtures/
  data/
    synthetic/
      generator.py
      seeds/
      ground_truth.json
  frontend/
    src/
      routes/
      components/
      lib/
  docs/
  PROJECT_PLAN.md
  CLAUDE.md
```

## API contracts (high level — full request/response schemas defined per-milestone as each is built)

- `POST /api/ingest/batch` — accept the synthetic source files, kick off the pipeline
- `GET /api/reconciliation/summary` — match rate, decision-type counts
- `GET /api/exceptions` — list, filterable/sortable by priority (VaR)
- `GET /api/exceptions/{id}` — evidence, hypothesis, verification result, confidence breakdown, why-matched/why-not-matched, decision
- `POST /api/exceptions/{id}/approve` — human approval action (writes an `Approval` + `AuditEvent`)
- `GET /api/audit` — filterable audit trail, with a hash-chain integrity check endpoint
- `GET /api/metrics/evaluation` — evaluation report against ground truth
- `GET /api/dashboard/var` — value-at-risk summary (total exposure, ranked exceptions)

## Frontend routes

- `/upload` — batch ingestion
- `/dashboard` — match rate + VaR exposure summary
- `/exceptions` — list, sortable by priority
- `/exceptions/:id` — full drill-in (evidence, hypothesis, verification, confidence, why-not-matched, decision, blocked-proposal explanation when applicable)
- `/audit` — audit trail viewer + hash-chain integrity display
- `/evaluation` — metrics report screen

## What was deliberately excluded from this architecture

Vector search / embedding infrastructure is **not** included by default — `docs/ai-design.md`'s tool set and RapidFuzz-based candidate matching are the default path. Only introduce embeddings if a specific case in the actual dataset demonstrably fails without it; do not add it speculatively "because it sounds advanced" (explicit instruction from the project brief).

## Milestone 5 addendum: the control layer

M5 adds `app/policy/` (PolicyEngine, state machine, authorization, approval workflow, risk/SLA, review packet, policy simulation) and `app/services/resolution_service.py`, sitting between M3/M4's already-computed evidence and any notion of a final decision. See `docs/safe-resolution.md`, `docs/policy-engine.md`, and `docs/human-review.md` for full detail — not duplicated here to keep this file the single up-to-date architecture reference rather than two competing descriptions.

## Milestone 6 addendum: the trust ledger

M6 adds `app/audit/` (`hashing.py`, `ledger.py`, `verify.py`, `provenance.py` — the persistent, SHA-256 hash-chained, append-only audit ledger and its reconstruction/verification layer) and `app/challenge/` (`contradiction.py` — the structured SUPPORTED/CONTRADICTED/INSUFFICIENT_EVIDENCE evidence classification, M6's one distinctive feature). `app/services/decision_service.py` is the new unified orchestrator: it is now the single entry point that wires M3's `EvidenceBundle` → M4's AI investigation (when routed) → M6's challenge classification → M5's `evaluate_policy` (the one remaining decision authority for every exception, AI-assisted or not) → M5's resolution proposal/review workflow, with every step recorded on the ledger under one shared `correlation_id`.

Before M6, `app.services.ai_exception_service.resolve_one` computed a final decision independently of `app.policy.engine.evaluate_policy` for AI-assisted exceptions — two separate authorities that happened to agree on the M1 dataset, but were not architecturally unified. `decision_service.py` is the fix, and it is additive: `ai_exception_service`/`resolution_service` themselves are unchanged and still independently correct/tested.

See `docs/audit-ledger.md`, `docs/decision-provenance.md`, and `docs/contradiction-evidence.md` for full detail — not duplicated here.

## Milestone 7 addendum: one end-to-end orchestrator

M7 adds exactly one new file, `app/services/reconciliation_pipeline.py` (`run_reconciliation_pipeline`), which is a pure integration layer over the four existing entry points `ingest_source_directory` (M1) → `run_exception_intelligence` (M2+M3) → `run_decision_pipeline` (M6, per exception) → `verify_chain`/`AuditLedger.count()` (M6). It adds a `run_id` (threaded into M6's `decision_service.run_decision_pipeline` via a new optional parameter, so `run -> exception -> investigation -> decision -> audit` stays reconstructable from the ledger alone), per-stage timing, result aggregation into `PipelineRunResult`, and fail-safe error handling at each stage boundary. It contains no matching, verification, policy, or audit logic of its own — every decision is still made by exactly the same M2/M4/M5/M6 code that made it before M7. `python scripts/run_reconciliation.py` is the one command that runs it end-to-end. See `docs/end-to-end-pipeline.md` for full detail.

## Milestone 8 addendum: the API (transport boundary)

M8 adds `backend/app/api/` (schemas, dependencies, run registry, error handlers, and `routes/{health,runs,exceptions,audit}.py`) plus `backend/app/main.py` (the FastAPI app). This is a pure transport layer: every route calls straight into an existing M1–M7 function (`run_reconciliation_pipeline`, `get_decision_provenance`, `AuditLedger`, `verify_chain`) and reshapes the result into an explicit Pydantic DTO — it performs no matching, verification, risk, policy, or audit logic of its own. Three new `Capability` values (`VIEW_RUN`/`VIEW_PROVENANCE`/`START_RECONCILIATION`) extend M5/M6's existing authorization model (`app.policy.schemas`/`app.policy.authorization`), granted to `HUMAN`/`SYSTEM` but not `AI` — mirroring exactly how M6 added its 3 audit capabilities. No new decision authority, no force-resolve endpoint, no financial-mutation endpoint. See `docs/api.md` for the full endpoint contract, error model, and security notes.

## Milestone 9 addendum: adversarial evaluation

M9 adds `backend/tests/adversarial/` (a reusable mutation framework cloning real M1 records, plus 14 attack-category test files, 10 named safety invariants, a safety matrix, classification metrics, mutation testing, seeded fuzz testing, and a baseline-comparison lock) — an evaluation and hardening pass, not a new engine. It found and fixed two real defects at their root: `verify_refund_consistency` (app.engines.reconciliation.verification) could let a duplicated refund record double-claim a single real debit, corrupting a reported residual (contained by M2's own defense-in-depth, never reaching an unsafe decision); and `resolve_single_linked_settlement`'s `fee_verified` branch (app.engines.reconciliation.matching) never cross-checked the actually-credited bank amount against the fee-verified net figure, which DID produce genuine false auto-resolutions under seeded fuzz testing before being fixed. The clean 300-record baseline distribution (219/67/2/12) is unchanged by both fixes. See `docs/adversarial-evaluation.md` for full detail.

## Milestone 10 addendum: evidence-first explainability

M10 adds `backend/app/explainability/` (`schemas.py`, `builder.py`, `completeness.py`, `provenance_check.py`) — a pure read/trace layer over already-computed M2–M6 objects, never a second decision engine. `build_explanation(decision, context=None, payment=None, settlement=None)` assembles the canonical `ExplanationReport` (decision, financial summary, source records, matching evidence, calculation trace, AI hypotheses explicitly distinguished from verified fact, self-challenge, policy, risk, resolution, audit references, contradictions, missing evidence, a rendered human-readable summary) entirely from `DecisionResult`/`EvidenceBundle`/`RootCauseResult`/`ContradictionRecord`/`PolicyDecision` — the one exception being an optional re-invocation of `verify_fee_consistency` purely to recover display detail (rule ID), never a second implementation of fee math. `check_explanation_completeness` and `validate_provenance` (Phase 14/15) guard against an explanation ever claiming more than the real evidence supports. Exposed via a new `GET /exceptions/{id}/explanation` endpoint reusing M8's existing `Capability.VIEW_PROVENANCE` — no new capability was added. Measured overhead: ~0.08% of pipeline time for building 40 real explanations. See `docs/explainability.md` for full detail.

## Milestone 11 addendum: prioritization & finance work queue

M11 adds `backend/app/prioritization/` (`schemas.py`, `scorer.py`, `queue.py`) — an operational, read-only layer over already-decided exceptions, never a second decision/risk/policy engine. `build_prioritized_exception(decision, payment, reference_now, explanation=None)` reuses M5's existing `assess_priority`/`assess_sla` (`app.policy.risk`, written in M5 but never previously wired into the real pipeline) for the priority tier and SLA status, and reads risk/exposure/decision straight from `DecisionResult`/`EvidenceBundle`, plus M6 contradiction records and M10's `ExplanationReport.missing_evidence` for two additional, transparent reason codes M5's original formula predates. `get_priority_queue`/`summarize_queue` (`queue.py`) provide deterministic ordering (priority → SLA urgency → exposure → risk → age → exception ID) and aggregate metrics — pure sort/aggregation, no financial calculation. `app.prioritization.scorer.attach_priority` integrates with M10's existing `ExplanationReport` (a new `PriorityInfo` field defined in `app.explainability.schemas` itself, to avoid a circular import) rather than building a second explanation system. Exposed via a new `GET /exceptions/queue` endpoint reusing M8's existing `Capability.VIEW_EXCEPTION` — no new capability was added. Explicit, directly-tested invariants confirm priority computation never changes the underlying policy decision, verification result, or financial record. See `docs/prioritization.md` for full detail.

## Milestone 12 addendum: the Finance Controller Command Center (frontend)

M12 adds `frontend/` — a React 18 + TypeScript + Vite application, the first (and only) new component in this project that renders anything visually, and a pure presentation layer over M1–M11: it performs no matching, verification, risk, policy, or audit logic, never recomputes M11's priority queue order client-side, and contains no financial-mutation control anywhere. Deliberately diverges from `docs/architecture.md`'s original sketch (React + TypeScript + Vite, Tailwind, shadcn/ui, Recharts) in two ways, both recorded as dated decisions: no Tailwind/shadcn (a single hand-written `src/index.css` design-token stylesheet instead) and no Recharts (the one chart this milestone needs is a dependency-free bar table, `src/components/BarChart.tsx`). `src/api/client.ts`/`types.ts` mirror `backend/app/api/schemas.py` field-for-field, the same DTO-mirroring discipline M8's own API layer uses against the internal M2–M6 objects.

Three smallest-additive backend changes were needed and made, none touching matching/verification/risk/policy/audit logic: `GET /runs` (listing `RunRegistry.list_runs()`, which existed but had no route), `GET /runs/{run_id}/audit/events` (listing `AuditLedger.events_for_correlation`'s existing per-run aggregation in full, not just the count `GET /runs/{run_id}/audit` already returned), and an `ExplanationResponse.priority` field (the internal `ExplanationReport`/`PriorityInfo` (M11) already carried this in `to_dict()`; the API DTO simply hadn't been extended to mirror it, and the route had never populated it — fixed by having `get_exception_explanation` call `build_prioritized_exception`/`attach_priority` when the owning run's `reference_now` and the payment are both resolvable, `null` otherwise, never fabricated). See `docs/frontend.md` for the full frontend architecture, routes, and demo flow, and `docs/api.md` for the three endpoint additions.

## Milestone 14 addendum: provider adapters (real-world data boundary)

M14 adds `backend/app/adapters/` — an isolated provider/source adapter layer answering "can this system consume realistic external financial-provider data without changing the trusted reconciliation/decision core?" (Yes.) The layer performs ONLY data translation: `RazorpayAdapter.fetch_records()` (retrieval, pagination, bounded retry, three modes — `fixture`/`mock`/`live`, default `fixture`, `live` never exercised in this environment) → `razorpay_mapping.map_*()` (explicit field-by-field mapping into the canonical dict shape, using `app.adapters.money`/`timestamps`/`id_mapping` for Decimal-safe minor-unit conversion, timestamp normalization, and deterministic external-ID→canonical-ID translation) → the EXISTING `app.ingestion.pipeline.ingest_records` (a pure extraction from `ingest_source_directory`, zero behavior change for the file-based caller). Nothing in this package matches, verifies, scores risk, evaluates policy, reasons with AI, or prioritizes — confirmed structurally (`test_the_fixture_pipeline_uses_no_special_decision_path`) as well as behaviorally (the complete fixture set runs through the real, unmodified M2–M6 pipeline end to end).

External IDs (e.g. Razorpay's `pay_MSTvS9jf9Zm7lb`) don't match the locked `app.schemas.records` ID regexes (matching the synthetic generator's own scheme) — rather than relax that already-tested validation, a deterministic hash (`app.adapters.id_mapping.external_id_to_canonical`) derives a schema-shaped canonical ID, with the real external ID preserved in `metadata.external_id` and the untouched raw payload (`RawRecord`, unchanged). A new read-only `GET /sources/status` endpoint (reusing the existing `Capability.VIEW_RUN`) and a small "Data Sources" section on the frontend's existing System Health page report each source's honest mode — never `LIVE READ-ONLY` unless real credentials are actually configured. See `docs/provider-adapters.md` for the full mapping tables, money/timestamp/ID safety detail, and `docs/production-readiness.md` for the honest READY/PARTIAL/NOT IMPLEMENTED assessment this milestone produced.
