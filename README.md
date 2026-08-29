# ReconcileAI

An explainable, deterministic-gated financial reconciliation agent for Razorpay-style merchant payment data — built for Razorpay AI Buildathon 2026, Track 04: AI Finance Controller.

## Problem

Finance teams reconcile records across multiple sources — payment gateway, settlement export, bank statement, internal orders, and refunds — that legitimately disagree because of fees, timing lag, partial settlements, duplicates, and mangled references. Getting this wrong either misses real money or wrongly clears something that needed a human's judgment, and most reconciliation tools stop at flagging a mismatch without investigating why it happened.

## Solution

```
Payments / Settlements / Bank transactions / Orders / Refunds / Fee rules
  -> deterministic matching (exact / tolerance / fee-adjusted)
  -> exception detection & classification
  -> AI investigation (for the residual, deterministic rules cannot resolve)
  -> deterministic verification (grounds every AI claim in real records)
  -> policy decision (the sole financial authority)
  -> human review (when required) / audit trail (always)
```

Deterministic matching handles the clean majority of records with no AI involved at all. For the genuinely ambiguous residual, an AI investigator proposes a structured hypothesis — never a decision — which is then independently re-verified with exact arithmetic against the real records before a deterministic policy engine decides the outcome.

## Safety Principle

**ReconcileAI does not trust AI with financial decisions.**

- **AI investigates** — it proposes one structured hypothesis from a closed set of possible root causes, citing only evidence it actually retrieved.
- **Verification validates** — an independent, deterministic system re-derives the claim with exact arithmetic against the real records, completely separately from the model that proposed it.
- **Policy decides** — a fixed-precedence policy engine is the only thing that ever decides an outcome, and it never reads the AI's own confidence score or recommended action.
- **Audit proves** — every step is written to a tamper-evident, hash-chained audit trail, reconstructable from a single exception ID.

## Key Results

Measured on a 300-record, ground-truthed synthetic evaluation set:

| Metric | Value |
|---|---|
| Auto-resolved | 219 |
| Human review | 67 |
| Rejected / blocked | 2 |
| Unresolved | 12 |
| Unsafe auto-resolutions | **0 / 300 (0.0000%)** |
| Naive fuzzy-matching baseline (no verification gate), same dataset | 14.67% unsafe auto-resolution rate |
| Backend tests passing | 861 |
| Frontend (Vitest) tests passing | 20 |
| Frontend (Playwright) E2E tests passing | 1 |

No additional metrics beyond these are claimed here. Full methodology, evidence, and per-milestone results are in `docs/final-validation.md` and `docs/final-winning-audit.md`.

## Demo

- **Synthetic fixture mode is the default** for both the reconciliation dataset and the Razorpay provider adapter — the demo runs entirely offline and deterministically.
- **`MockAIProvider` is used throughout** for deterministic, reproducible evaluation and demos.
- **Live Razorpay mode has NOT been exercised** against a real API in this environment (no production credentials exist here) — the adapter code exists and is tested against simulated HTTP responses only.
- **A live LLM provider has NOT been exercised** against a real vendor API in this environment — `GeminiProvider`/`OpenAICompatibleProvider` exist as real code but are untested against a live model.

These are disclosed consistently throughout the documentation, not only here. See `docs/demo-runbook.md` for setup/reset and `docs/three-minute-demo.md` for the exact judge-facing script.

## Architecture

```
Ingest -> Normalize -> Deterministic Match -> Exception Detection
  -> AI Investigation -> Self-Challenge -> Verification
  -> Risk + Policy -> Decision -> Audit + Explanation
  -> Priority Queue -> API -> Frontend
```

The AI/policy boundary is structural: the policy engine's decision function reads only deterministic, independently-computed inputs (verification status, risk level, evidence completeness) — never the AI's own confidence or recommended action. See `docs/architecture.md` for the full design and `docs/final-winning-audit.md` §6 for the traced AI-to-decision data flow.

## Repository Structure

```
backend/        FastAPI application: reconciliation, AI, policy, audit, API (app/), tests (tests/)
frontend/       React + TypeScript + Vite frontend, Vitest + Playwright tests
data/synthetic/ The 300-record ground-truthed dataset, seeds, and provider fixtures
scripts/        Benchmarks, evaluation harnesses, and the terminal demo entry point
docs/           Architecture, safety, demo, and validation documentation (see below)
shared/         Money/taxonomy helpers shared between the generator and the backend
CLAUDE.md       Full project history, architectural decisions, and current status
PROJECT_PLAN.md Milestone-by-milestone build record
```

## Testing

Commands as actually configured in this repository (`pytest.ini`, `frontend/package.json`):

```bash
# Backend — full suite (pytest.ini: testpaths = backend/tests), from the repo root
python -m pytest -q

# Frontend — Vitest unit/component suite
cd frontend && npm test

# Frontend — Playwright browser E2E suite (requires both servers running, see docs/demo-runbook.md)
cd frontend && npm run test:e2e

# Terminal-only full pipeline demo, no UI dependency
python scripts/run_reconciliation.py

# Competitive baseline evaluation
python scripts/evaluate_competitive_baselines.py

# Dataset quality audit
python scripts/audit_dataset.py
```

## Limitations

Stated plainly, not hidden:

- No live LLM provider has ever been exercised against a real vendor API.
- No live Razorpay API call has ever been made against a real endpoint.
- SQLite and in-memory registries — this is a demo-scale architecture, not a production deployment.
- `RunRegistry` and `ApprovalWorkflowStore` are in-memory and process-lifetime only.
- No persisted human review/approval workflow exists over HTTP.
- No deployment, monitoring, backup, or disaster-recovery infrastructure exists.

Full detail in `docs/production-readiness.md` and `CLAUDE.md`'s "Known limitations" section.

## Documentation

- [`docs/demo-runbook.md`](docs/demo-runbook.md) — full setup, golden path, and reset instructions
- [`docs/three-minute-demo.md`](docs/three-minute-demo.md) — the exact timed judge demo script
- [`docs/judge-qa.md`](docs/judge-qa.md) — anticipated judge questions, answered against real code/tests
- [`docs/final-validation.md`](docs/final-validation.md) — the complete, source-cited judge evidence package
- [`docs/final-winning-audit.md`](docs/final-winning-audit.md) — the full requirement/safety/competitive audit
- [`docs/winning-thesis.md`](docs/winning-thesis.md) — the 30-second/60-second/2-minute pitch
- [`docs/presentation-blueprint.md`](docs/presentation-blueprint.md) — recommended slide-by-slide deck structure
- [`docs/demo-failure-plan.md`](docs/demo-failure-plan.md) — live-judging failure modes and recovery
- [`docs/production-readiness.md`](docs/production-readiness.md) — honest READY/PARTIAL/NOT IMPLEMENTED matrix
- [`docs/evaluation.md`](docs/evaluation.md) — the measured evaluation methodology and results
