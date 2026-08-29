# PROJECT_PLAN.md — ReconcileAI Milestones

Status legend: `NOT STARTED` / `IN PROGRESS` / `DONE`. Update the status line for a milestone the moment it's complete and reviewed — never mark `DONE` before its tests pass and its acceptance criteria are met.

**Reuse-vs-scratch decision:** repository was empty at planning time (only documentation existed). **Building from scratch** — no legacy code to migrate or reconcile with.

**Priority key:** CORE MVP (the one finance-ops loop doesn't work without this) / IMPORTANT (strengthens it materially) / OPTIONAL (only if time remains) / DEMO POLISH (cosmetic, last).

Ordering follows: problem statement → core workflow → data shape (Razorpay-mirrored) → core AI → verification/reliability → demo → polish. Every milestone below is small enough to implement, test, and review independently — do not start the next one until the current one is approved.

---

### M0 — Project Foundations & Scaffolding
**Status:** DONE — `backend/app/main.py` (this milestone's own named deliverable) was built as part of M8's "Milestone 8" note below, once a real caller (the HTTP API) actually needed it; the frontend (`Vite` scaffold) was built as part of M12's "Milestone 12" note below, once a real judge-facing UI need existed.
**Priority:** CORE MVP
**Goal:** Stand up the actual repo skeleton (backend/frontend/data folders, dependency manifests, config loading, empty-but-runnable FastAPI app and Vite app) matching `docs/architecture.md`'s folder structure — no business logic yet.
**Features:** `backend/app/main.py` boots and returns a health-check; `frontend` boots and renders a placeholder page; `config.py` reads `LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY`/DB path from environment with no hardcoded secrets; `.gitignore` covers `.env`, `__pycache__`, `node_modules`, DB files.
**Files/components:** `backend/app/main.py`, `backend/app/config.py`, `backend/requirements.txt` (or `pyproject.toml`), `frontend/` (Vite scaffold), `.env.example`, `.gitignore`.
**Dependencies:** none (first milestone).
**Acceptance criteria:** `uvicorn app.main:app` serves a 200 on a health endpoint; `npm run dev` serves the placeholder frontend; no secret is committed; folder layout matches `docs/architecture.md`.
**Tests:** one smoke test hitting the health endpoint.
**Demo outcome:** nothing user-visible yet — this is pure scaffolding.
**Estimated complexity:** Small.
**Must NOT change:** nothing yet exists to break; this milestone must not include any engine/matching/AI logic.

---

### M1 — Data Model & Dev Fixture Generator
**Status:** DONE (2026-08-25) — **scope expanded at implementation time** to also cover the data-foundation portions of M2 (ingestion + normalization) and M14 (300-record scale-up + adversarial cases) in a single consolidated pass, per explicit instruction. M2's and M14's *remaining* scope (an HTTP-exposed ingest endpoint, and anything beyond dataset generation) is still open and now effectively folded into whichever later milestone first needs it — see the note at the end of this entry.
**Priority:** CORE MVP
**Goal:** Implement every entity in `docs/data-model.md` as SQLAlchemy models + Pydantic schemas, plus a small (10–20 record) hand-verifiable synthetic fixture for engine development — full 300-record scale-up is deferred to M14.
**Features:** all tables created via migration/`create_all`; a small fixture generator with a fixed seed producing a handful of each easy case (exact match, one fee deduction, one refund) with a matching `ground_truth.json`.
**Files/components:** `backend/app/db/models.py`, `backend/app/schemas/*.py`, `data/synthetic/generator.py` (v1, small scale), `data/synthetic/seeds/`, `data/synthetic/ground_truth.json`.
**Dependencies:** M0.
**Acceptance criteria:** all entities from `docs/data-model.md` exist with correct field types (`Decimal` for money, enums for taxonomy/status); fixture loads without error; `ground_truth.json` validates against every fixture record.
**Tests:** model creation/round-trip tests; fixture-generator determinism test (same seed → identical output).
**Demo outcome:** none yet.
**Estimated complexity:** Medium.
**Must NOT change:** the taxonomy enum values in `docs/data-model.md` — downstream milestones depend on exact string values.

**As actually delivered (2026-08-25):** `shared/taxonomy.py` (canonical enums), `shared/money.py` (Decimal-only quantization + Decimal-safe JSON codec), `backend/app/db/models.py` (Order/Payment/Settlement/BankTransaction/Refund/FeeRule/RawRecord — the reconciliation-result entities are deliberately deferred to the milestones that produce them), `backend/app/db/session.py`, `backend/app/schemas/records.py` (Pydantic validation), `backend/app/engines/normalization.py`, `backend/app/engines/validation.py`, `backend/app/ingestion/pipeline.py` (plain importable pipeline, not yet an HTTP endpoint), `data/synthetic/generator.py` (full 300-record generator, not just a 10–20 record fixture), `data/synthetic/seeds/*.json` (the generated dataset itself), `data/synthetic/README.md`, and 38 passing tests across 5 test files. No LLM, no dashboard, no AI reasoning — confirmed out of scope and not touched.

---

### M2 — Ingestion + Normalization
**Status:** PARTIALLY DONE (2026-08-25) — normalization engine and the ingestion pipeline itself were built as part of M1's consolidated scope (`backend/app/engines/normalization.py`, `backend/app/ingestion/pipeline.py`). **Remaining for this milestone:** exposing ingestion over an HTTP endpoint (`POST /api/ingest/batch`) — deliberately deferred since no caller needs it over HTTP yet (see M1's file notes and `docs/architecture.md`'s API contracts section). Pick this up when M16 (frontend) or an earlier API need arises.
**Priority:** CORE MVP
**Goal:** Load the fixture's source files into the DB and normalize fields (currency formatting, date/timezone alignment, reference/ID format alignment) — no matching logic yet.
**Features:** `POST /api/ingest/batch` accepts source files and persists raw + normalized records.
**Files/components:** `backend/app/engines/normalization.py`, `backend/app/api/routes_ingest.py`.
**Dependencies:** M1.
**Acceptance criteria:** ingesting the M1 fixture produces normalized records with consistent date/currency/reference formats; re-ingesting is idempotent (no duplicate rows).
**Tests:** unit tests per normalization rule (currency, date, reference); one ingestion integration test against the fixture.
**Demo outcome:** none yet (no UI).
**Estimated complexity:** Small–Medium.
**Must NOT change:** raw ingested records are preserved unmodified alongside normalized versions — never overwrite the source-of-truth raw value.

---

### Note: "Milestone 2" as actually implemented (2026-08-25)

The user's second implementation session defined "Milestone 2: Deterministic Reconciliation Engine" as one consolidated pass covering exact/normalized matching, fuzzy candidate generation, multi-field scoring, financial verification (fee/refund/split/aggregate), one-to-many and many-to-one relationships, the non-negotiable ambiguity rule, deterministic explanation strings, a `ReconciliationMatch` result model, an evaluation harness against the real 300-record dataset, an 18-scenario test suite, and a 300/1,000/5,000/10,000-record performance benchmark — explicitly excluding the LLM/AI agent, dashboard, and any autonomous financial decision. This maps onto this plan's original M3, M4, and (partially) M6/M9/M13, which are updated in place below rather than re-numbered, so the plan doesn't silently drift from what actually happened. No LLM/AI/dashboard code was added; M5 (category-level exception taxonomy), M7 (agent evidence tools), M8 (AI agent), M10/M11 (confidence/policy engine), M12 (hash-chained audit), M14 (already done early, see its own entry), M15-M18 remain as originally scoped and NOT started here.

Key results (full detail in CLAUDE.md's M2 entry): 72/72 tests pass (38 M1 + 34 M2). Against the real 300-record dataset: precision 1.0000, recall 1.0000, F1 1.0000, **incorrect-auto-resolution rate 0.0000 (0 of 300)**, all 5 M1 adversarial cases correctly rejected, 0 disagreements between engine status and ground truth's expected action across all 300 records. Performance: an initial O(k²) bottleneck in the many-to-one aggregation search was identified via the 10,000-record benchmark (throughput fell from ~54k records/sec at 1,000 to ~3,950 at 10,000) and fixed with an O(k) two-sum hash lookup (throughput at 10,000 records recovered to ~37,350 records/sec).

### M3 — Exact & Normalized-Reference Matching
**Status:** DONE (2026-08-25) — delivered as part of the consolidated "Milestone 2: Deterministic Reconciliation Engine" pass (see note at the end of this milestone and CLAUDE.md's M2 architectural decision). `backend/app/engines/reconciliation/matching.py` implements exact-reference (raw, byte-identical containment) and normalized-reference (via M1's `normalize_reference`) matching, gated by a tight date-tolerance window and an exact bank-confirmed-amount check — not reference alone, per the safety requirement that "same reference alone should NOT automatically mean financially reconciled if amount/balance contradicts."
**Priority:** CORE MVP
**Goal:** Stage 1–2 of the pipeline: deterministic exact matching, then normalized-reference matching for mangled-but-recognizable IDs.
**Features:** `engines/exact_match.py` producing `ReconciliationMatch` rows (`status=verified`) for clean matches; a match rate is now computable.
**Files/components:** `backend/app/engines/exact_match.py`.
**Dependencies:** M2.
**Acceptance criteria:** on the M1 fixture, every intended exact-match case is matched, and no case designed as *not* a clean match is force-matched.
**Tests:** unit tests against `ground_truth.json` for the exact-match subset; boundary tests (near-identical-but-not-matching references must NOT match here).
**Demo outcome:** internal only — a match-rate number can now be printed to a script/log.
**Estimated complexity:** Small–Medium.
**Must NOT change:** exact matching must remain conservative — do not let this stage absorb fuzzy logic; that belongs in M4.

---

### M4 — Fuzzy Candidate Matching & Multi-Field Scoring
**Status:** DONE (2026-08-25) — delivered as part of the consolidated Milestone 2 pass. `candidate_generation.py` blocks candidates by (currency, date-week, amount-band) instead of a full cross-product; `scoring.py` implements the transparent 6-signal scorer (reference/amount/date/fee/merchant/link, RapidFuzz used for partial-credit reference similarity) with every component stored, never just the total.
**Priority:** CORE MVP
**Goal:** Stage 3–4: generate fuzzy candidates (RapidFuzz) for records exact matching left unresolved, and score each candidate across multiple fields (amount, date proximity, reference similarity, merchant).
**Features:** `engines/candidate_match.py`, `engines/scoring.py`; candidates are stored (accepted or not) — this is the foundation for M6's "Why NOT Matched."
**Files/components:** `backend/app/engines/candidate_match.py`, `backend/app/engines/scoring.py`.
**Dependencies:** M3, RapidFuzz dependency added.
**Acceptance criteria:** for every fixture record that has a genuine fuzzy counterpart, at least one correct candidate is generated with a higher multi-field score than any incorrect candidate.
**Tests:** unit tests on known candidate sets (correct candidate scores higher than distractors); an ambiguous-case fixture (two similarly-scored candidates) is preserved as ambiguous, not force-resolved.
**Demo outcome:** none yet (no UI).
**Estimated complexity:** Medium.
**Must NOT change:** candidate generation must not silently discard rejected candidates — every one persists with its score breakdown for M6.

---

### M5 — Exception Detection & Taxonomy
**Status:** DONE (2026-08-25) — delivered as part of the consolidated "Milestone 3: Exception Intelligence & Negative Evidence Engine" pass (see the note at the end of M9 and CLAUDE.md's M3 architectural decisions). `backend/app/engines/exceptions/classifier.py` classifies every M2 result into M1's canonical `ExceptionCategory` (no second taxonomy created); `classify_exception()` returns `None` for a genuinely clean match. Classification accuracy against the real 300-record dataset: **1.0000 (0 mismatches)**.
**Priority:** CORE MVP
**Goal:** Classify every record that didn't get a clean exact match into one of the fixed taxonomy categories (`docs/data-model.md`), creating `Exception` rows.
**Features:** `engines/exception_detection.py` assigning `category` deterministically where the category is mechanically inferable (e.g., "amount exactly equals payment minus a known fee" → `fee_mismatch` candidate; "identical reference twice" → `duplicate` candidate) — ambiguous cases are left as `ambiguous_match` / `unexplained_difference` pending AI investigation (M8).
**Files/components:** `backend/app/engines/exception_detection.py`.
**Dependencies:** M4.
**Acceptance criteria:** every non-exact-match fixture record gets exactly one `Exception` row with a category from the fixed taxonomy; category assignment matches `ground_truth.json` for the mechanically-obvious cases.
**Tests:** unit test per taxonomy category present in the fixture.
**Demo outcome:** none yet (no UI).
**Estimated complexity:** Medium.
**Must NOT change:** the taxonomy enum itself (frozen at M1) — do not add ad-hoc categories here.

---

### M6 — "Why NOT Matched?" Negative Evidence Engine
**Status:** SUBSTANTIALLY DONE (2026-08-25) — the M2 pass produced structured `why_not_matched` reasons for the ambiguous/duplicate/candidate-scoring paths only; the M3 pass generalized this into a full engine: `backend/app/engines/evidence/candidates.py`'s `why_not_matched()` now gathers **every** plausible candidate for **every** payment (not just ones M2's simpler path already considered multiple candidates for), runs the complete constraint battery (`app.engines.evidence.constraints`) against each, and returns a ranked `NegativeEvidenceReport` with explicit `ACCEPTED`/`REJECTED` verdicts and machine-readable `reason_code`s — plus the worked SETTLEMENT_1029-style example from `docs/ai-design.md` is now reproduced almost verbatim in `docs/why-not-matched.md`. What's still NOT done: persisting rejected candidates as their own queryable DB rows across sessions (they exist in-memory per run, via `NegativeEvidenceReport`/`EvidenceBundle`, not yet in a table) — still a follow-up.
**Priority:** CORE MVP
**Goal:** Turn M4's rejected-candidate data into the structured, explained rejection records this project treats as a first-class feature.
**Features:** `engines/why_not_matched.py` producing the reasons payload (amount difference, date difference, reference similarity, conflicting evidence, balance-check result) and a verdict string for every rejected candidate of every exception.
**Files/components:** `backend/app/engines/why_not_matched.py`.
**Dependencies:** M5.
**Acceptance criteria:** every exception with more than one considered candidate has a "why not matched" explanation for every candidate it didn't choose, matching the structure in `docs/ai-design.md`.
**Tests:** unit test reproducing the exact worked example in `docs/ai-design.md` (SETTLEMENT_1029-style rejection).
**Demo outcome:** internal only — this becomes UI-visible in M17.
**Estimated complexity:** Small–Medium.
**Must NOT change:** rejection reasons must reference actual computed signal values, never a placeholder string.

---

### M7 — Cross-Source Evidence Collection Tools
**Status:** DONE (2026-08-27) — the M3 pass built the underlying deterministic evidence primitives; the M4 pass completed this milestone by wrapping them as the fixed, agent-callable tool interface originally scoped here: `backend/app/ai/tools.py` — 10 allow-listed tools (`get_exception_context`, `get_record`, `get_related_records`, `get_candidate_matches`, `get_negative_evidence`, `get_fee_rule`, `get_refunds`, `get_settlement`, `calculate_balance`, `compare_candidates`), each with a strict Pydantic input/output schema, each wrapping an existing M2/M3 function rather than re-deriving logic, validated via the single `invoke_tool()` entry point (`TOOL_REGISTRY` allow-list + schema validation before any tool body runs).
**Priority:** CORE MVP
**Goal:** Stage 5: implement the fixed tool set the AI agent will call, each returning structured `Evidence` rows, logged before any reasoning happens.
**Features:** `find_candidate_matches`, `get_related_refunds`, `get_fee_schedule`, `get_historical_pattern`, `get_bank_transactions_near` — no LLM call yet, just the deterministic data-gathering layer.
**Files/components:** `backend/app/ai/tools.py`.
**Dependencies:** M6.
**Acceptance criteria:** for every open exception in the fixture, calling the relevant tools produces the correct, complete evidence set an investigator would need (verifiable by hand against the fixture).
**Tests:** unit test per tool against known fixture exceptions.
**Demo outcome:** none yet.
**Estimated complexity:** Medium.
**Must NOT change:** tools must only read structured records — no tool may fabricate or infer a value; that's the agent's job (heavily gated in M8).

---

### M8 — AI Investigation Agent (Hypothesis Generation)
**Status:** DONE (2026-08-27) — delivered as part of the consolidated "Milestone 4: AI Exception Controller" pass (see the note at the end of M11). `backend/app/ai/provider.py` implements the `LLMProvider` abstraction exactly as named in `docs/ai-design.md` (`MockAIProvider` — deterministic, zero network, what all tests/evaluation run against; `GeminiProvider`/`OpenAICompatibleProvider` — real REST implementations, not exercised live here) and `backend/app/ai/controller.py` implements the bounded investigation loop (tool selection → hypothesis generation → grounding validation) in place of the originally-scoped `ai/agent.py`. Every `AIHypothesis.hypothesis_type` is a closed 12-value enum; grounding validation (`app.ai.verifier.validate_grounding`) rejects any hypothesis citing an ID never retrieved via a logged tool call this session.
**Priority:** CORE MVP
**Goal:** Stage 6: wire the `LLMProvider` abstraction and the agent orchestration loop that calls M7's tools, then produces a structured `AIHypothesis`, gated by the evidence-grounding validator from `docs/ai-design.md`.
**Features:** `ai/provider.py` (env-configured, at least one working implementation), `ai/agent.py` (tool selection + hypothesis generation + grounding validation, rejecting any hypothesis citing evidence that doesn't exist).
**Files/components:** `backend/app/ai/provider.py`, `backend/app/ai/agent.py`, `backend/app/schemas/hypothesis.py`.
**Dependencies:** M7. Requires an `LLM_API_KEY` in the environment (never committed).
**Acceptance criteria:** on the fixture's open exceptions, the agent produces a hypothesis for each; every `cited_evidence_ids` entry is verified to exist; a deliberately-malformed/ungrounded model response (tested via a stub provider) is correctly rejected, not silently accepted.
**Tests:** unit tests using a stub/mock `LLMProvider` (no real API calls in CI) covering: valid hypothesis accepted; hypothesis citing a nonexistent evidence ID rejected; malformed JSON rejected.
**Demo outcome:** none yet (backend-only capability).
**Estimated complexity:** Large (this is the first genuinely novel component).
**Must NOT change:** the agent must never write directly to `Order`/`Payment`/`Settlement`/`BankTransaction`/`Refund` tables — it only produces an `AIHypothesis` row.

---

### M9 — Deterministic Verification Engine
**Status:** SUBSTANTIALLY DONE for the matching-stage scope (2026-08-25), delivered early as part of the consolidated Milestone 2 pass — `verification.py` implements fee-rule verification (`verify_fee_consistency`, the exact check that rejects the M1 adversarial fee_mismatch cases), refund consistency, settlement self-consistency (internal fee/tax/net_amount arithmetic), and bank-confirmed-amount derivation, all independent of any LLM (there is no LLM import anywhere in the `reconciliation` package). **Extended in Milestone 3** with formal deterministic counterfactual hypothesis testing (`app.engines.root_cause.hypotheses`: H1 refund, H2 fee, H3 timing, H4 duplicate, H5 aggregation — each explicitly labeled NOT an AI hypothesis) and discrepancy decomposition (`app.engines.root_cause.decomposition`), both built strictly on top of M2's existing verification functions, never re-deriving them. **M9's original brief is now DONE as of Milestone 4:** `app.ai.verifier.verify_hypothesis` dispatches every `AIHypothesis` type to these same M2/M3 checkers (never a parallel implementation), plus two new guards added specifically for verifying an AI-proposed (as opposed to M3's own hand-derived) hypothesis safely: grounding validation, and the single-settlement-selection conflict guard (blocks a hypothesis about one settlement in isolation when a reversed status, a duplicate sibling, or an unresolved rival candidate exists) — see CLAUDE.md's M4 architectural decision for the two real false-auto-resolution bugs this guard was added to fix.

**Note on "Milestone 3" as actually implemented (2026-08-25):** the user's third implementation session defined "Milestone 3: Exception Intelligence & Negative Evidence Engine" as one consolidated pass covering exception classification into M1's taxonomy, the full multi-candidate "Why NOT Matched" engine, a cross-source evidence graph, deterministic hypothesis testing, discrepancy decomposition, a root-cause result model, financial exposure/risk scoring, an `EvidenceBundle` boundary for a future AI layer, a 20-scenario test suite (plus the brief's own 8 adversarial cases, including malicious-memo-text), a 10-example explainability test, and a 300/1,000/5,000/10,000-record benchmark — explicitly excluding any LLM/AI agent/vector DB/dashboard. This maps onto this plan's M5, M6, and portions of M7/M9, updated in place above. Key results: 130/130 tests pass (72 M1+M2, 58 M3); against the real 300-record dataset, exception-classification accuracy 1.0000, root-cause status accuracy 1.0000, **false-explanation rate 0.0000**, all 5 M1 adversarial cases correctly reach a non-VERIFIED root-cause status. Full detail, including the confirmed `reversed_transaction`/policy-vs-root-cause divergence to carry into M10/M11, is in `CLAUDE.md`'s M3 entry.
**Priority:** CORE MVP
**Goal:** Stage 7: independently re-derive the arithmetic/relationship each hypothesis claims, using `Decimal`, without trusting the LLM's explanation text.
**Features:** `verification/verify.py` implementing checks per category (fee-balance check, duplicate-conflict check, split/aggregate-sum check, etc.).
**Files/components:** `backend/app/verification/verify.py`.
**Dependencies:** M8.
**Acceptance criteria:** every hypothesis in the fixture is independently confirmed or refuted correctly against `ground_truth.json`; the adversarial-style test case (a plausible but wrong hypothesis) is correctly refuted.
**Tests:** unit test per verification check type, including at least one designed-to-fail case.
**Demo outcome:** none yet.
**Estimated complexity:** Medium–Large (this is the core safety component — do not rush it).
**Must NOT change:** verification logic must never call the LLM or depend on `model_self_reported_signals` — it is 100% independent of the AI layer.

---

### M10 — Confidence Scoring Engine
**Status:** PARTIALLY DONE (2026-08-27) — M4's `app.ai.policy` implements the authoritative gate that decides whether an AI hypothesis's own (never-trusted) confidence/recommended_action can become a real decision, exactly per this milestone's non-negotiable rule ("`model_self_reported_signals` must never be summed into this score"). M5's `app.policy.risk` adds the risk-level/SLA-status buckets that feed the RISK tier of `app.policy.engine`, itself built on M3's `risk_score` formula. **Not done as originally scoped:** a standalone `engines/confidence.py` producing a general-purpose numeric confidence score from measurable signals (reference similarity, historical pattern, etc.) for use beyond AI-hypothesis gating — M2's `scoring.py`, M3's `risk_score`, and M5's `policy.py` together substantially cover this need via separate signal-specific modules rather than one blended-confidence component; a unified module has still not been built as its own thing.
**Priority:** CORE MVP
**Goal:** Compute the authoritative confidence score from measurable signals (`docs/ai-design.md`), completely independent of anything the LLM self-reports.
**Features:** `engines/confidence.py` with named, configurable weights per signal.
**Files/components:** `backend/app/engines/confidence.py`.
**Dependencies:** M9 (verification result is itself one strong input signal, alongside the raw matching-stage signals).
**Acceptance criteria:** confidence scores on the fixture correlate sensibly with ground-truth correctness (correct/clean cases score high, ambiguous/adversarial cases score low) — this is checked qualitatively now and formally in M13's evaluation harness.
**Tests:** unit tests on hand-picked signal combinations verifying the formula behaves monotonically (more agreement → higher score).
**Demo outcome:** none yet.
**Estimated complexity:** Small–Medium.
**Must NOT change:** `model_self_reported_signals` must never be summed into this score — it's a display/audit field only.

---

### Note: "Milestone 4" as actually implemented (2026-08-27)

The user's fourth implementation session defined "Milestone 4: AI Exception Controller" as one consolidated pass covering the `LLMProvider` abstraction (mock + two real, untested-live implementations), a 10-tool allow-listed interface wrapping M2/M3's existing functions, a closed-enum `AIHypothesis` schema, a bounded tool-calling investigation loop, a deterministic verifier reusing M2/M3's checkers, an authoritative policy gate, deterministic AI routing/triage, an auditable structured trace, prompt-injection and hallucination defense, provider-failure safe-fallback handling, and a 300-record evaluation with false-auto-resolution-rate as the critical (0%) metric — explicitly excluding ledger mutation, the dashboard, and the final hash-chained audit ledger. This maps onto this plan's M7 (remainder), M8, and portions of M10/M11, updated in place above/below. Key results: 220/220 tests pass (130 M1–M3, 90 M4); against the real 300-record dataset, **false-auto-resolution rate 0.0000**, only 74/300 (24.7%) records routed to AI, AI-assisted final-decision distribution exactly matching M2/M3's own safe-auto-resolution count. Two real false-auto-resolution bugs were found and fixed via this milestone's own evaluation (not merely asserted safe) — full detail in `CLAUDE.md`'s M4 entry.

### M11 — Policy Engine & Decision Routing + Basic Audit Logging
**Status:** DONE (2026-08-27) — delivered as the consolidated "Milestone 5: Safe Resolution, Policy Gate & Human Approval Engine" pass (see the note below). `app.policy.engine.evaluate_policy` is the full deterministic policy engine this milestone originally scoped: configurable thresholds, declarative rules in a fixed four-tier precedence (BLOCK > MANDATORY_APPROVAL > RISK > AUTO_ELIGIBILITY), producing exactly one `PolicyDecision` (`SAFE_TO_RESOLVE`/`HUMAN_REVIEW`/`REJECTED`/`ESCALATED`/`UNRESOLVED`) per exception, end-to-end on the full 300-record dataset. `app.policy.audit.make_event` is the first-pass `AuditEvent` writer (chaining still deferred to M12, unchanged). **Still not done, same reasoning as M2's HTTP endpoint:** `Decision`/`Approval`/`ResolutionProposal`/`ReviewRequest` are in-memory dataclasses, not persisted DB rows/tables — no caller (API/UI) exists yet that needs them to survive a process restart.
**Priority:** CORE MVP
**Goal:** Stage 8: apply configurable thresholds (`AUTO_RESOLVE` / `HUMAN_REVIEW` / `UNRESOLVED`) plus declarative categorical rules to produce a final `Decision`, and write a plain (not yet hash-chained) audit log entry for every decision.
**Features:** `engines/policy.py`, `Decision`/`Approval` persistence, a first-pass `AuditEvent` writer (chaining added in M12).
**Files/components:** `backend/app/engines/policy.py`, `backend/app/audit/audit_log.py` (v1).
**Dependencies:** M10.
**Acceptance criteria:** end-to-end on the fixture: every exception reaches exactly one `Decision`; the adversarial case is blocked or routed to human review (never auto-resolved); every decision has a corresponding audit entry.
**Tests:** end-to-end pipeline test on the full fixture, asserting decision-type distribution matches expectations from `ground_truth.json`.
**Demo outcome:** **first full end-to-end run is now possible** — this is the milestone where "the one finance-ops loop" first genuinely closes, even with no UI yet.
**Estimated complexity:** Medium.
**Must NOT change:** thresholds must remain configuration values, not hardcoded literals scattered in code — the whole point is later tuning in M13/M14.

---

### Note: "Milestone 5" as actually implemented (2026-08-27)

The user's fifth implementation session defined "Milestone 5: Safe Resolution, Policy Gate & Human Approval Engine" as one consolidated pass covering the deterministic `PolicyEngine` with a fixed four-tier precedence, policy versioning/dry-run simulation, a closed `ResolutionProposal` schema (no dangerous generic action types), the human approval workflow (states, structured reason codes, dual control, idempotency), a minimal actor/authorization model, risk-level/SLA/priority assessment (built on M3's existing risk-score formula, never replaced), a structured (not yet hash-chained) audit event model, the explicit exception-lifecycle state machine, 10 demo scenarios, and a 300-record evaluation with false-auto-resolution-rate and unsafe-approval-rate both required at 0% — explicitly excluding real financial mutation, the dashboard, and the final audit ledger. This maps onto this plan's M11 (now DONE) and part of M10, updated in place above. Key results: 307/307 tests pass (220 M1–M4, 87 M5); against the real 300-record dataset, **policy-decision accuracy 1.0000**, **false-auto-resolution rate 0.0000**, **unsafe-approval rate 0.0000**, all 5 M1 adversarial cases blocked. Two real bugs (both about `missing_transaction` being mis-routed to `HUMAN_REVIEW` instead of `UNRESOLVED`) were found and fixed via this milestone's own evaluation — full detail in `CLAUDE.md`'s M5 entry.

---

### M12 — Tamper-Evident Audit Trail (Hash Chaining) & Audit API
**Status:** DONE (2026-08-27) — delivered as part of the consolidated "Milestone 6: Trusted Decision Ledger, Provenance & Self-Challenging Evidence" pass (see the note at the end of this milestone). `app.audit.hashing`/`app.audit.ledger`/`app.audit.verify` implement exactly this milestone's original scope — SHA-256 hash chaining, append-only enforcement (no UPDATE/DELETE code path exists), and a `verify_chain()` that detects payload/timestamp/actor/event-type modification, deletion, insertion, reordering, and forged previous-hash, each confirmed via a dedicated adversarial test. **Not done as originally scoped:** an HTTP `GET /api/audit` endpoint — same reasoning as M2's ingest endpoint, deferred until a caller (frontend/API) actually needs it; `scripts/verify_audit_ledger.py` is the CLI-level equivalent for this milestone's scope.
**Priority:** IMPORTANT
**Goal:** Upgrade M11's plain audit log to the SHA-256 hash-chained model (`docs/data-model.md`), plus an API to fetch and verify the chain.
**Features:** `audit/hash_chain.py`; `GET /api/audit` with a chain-integrity check.
**Files/components:** `backend/app/audit/hash_chain.py`, `backend/app/api/routes_audit.py`.
**Dependencies:** M11.
**Acceptance criteria:** recomputing the chain from genesis matches every stored `hash`; deliberately corrupting one stored event (in a test) is detected by the integrity check.
**Tests:** hash-chain integrity test, including a tamper-detection test.
**Demo outcome:** the audit screen's "chain verified" indicator (UI wired in M17).
**Estimated complexity:** Small–Medium.
**Must NOT change:** do not present this as more than tamper-evidence for a demo — no claim of cryptographic non-repudiation in any user-facing copy.

---

### Note: "Milestone 6" as actually implemented (2026-08-27)

The user's sixth implementation session defined "Milestone 6: Trusted Decision Ledger, Provenance & Self-Challenging Evidence" as one consolidated pass covering: a persistent SHA-256 hash-chained append-only audit ledger (this plan's M12, now DONE above); `get_decision_provenance`/`build_decision_summary` full-story reconstruction from only an exception_id and the ledger (a capability not separately named anywhere else in this plan); a structured SUPPORTED/CONTRADICTED/INSUFFICIENT_EVIDENCE challenge/contradiction mechanism built on M4's hypothesis outcomes and M3's evidence concepts, with a self-challenge rule that feeds a detected contradiction into M5's existing `PolicyInput.conflicting_evidence` field (no new policy logic added); a new `app.services.decision_service.run_decision_pipeline` orchestrator unifying M4's AI-assisted path and M5's `evaluate_policy` into one authority for every exception (previously two independent decision paths that happened to agree on this dataset); 3 new audit-specific `Capability` values (`VIEW_AUDIT`/`VERIFY_AUDIT`/`APPEND_AUDIT`, with no `UPDATE_AUDIT`/`DELETE_AUDIT` value existing at all); 12 numbered adversarial tests; an isolated tamper demo and CLI verifier; a 1,000/10,000/100,000-event performance benchmark; and a 300-record evaluation with false-auto-resolution-rate required at 0% — explicitly excluding a dashboard, production Razorpay integration, blockchain, and any unrestricted/multi-agent AI. This maps onto this plan's M12 (now DONE) plus new capability not previously scoped as its own milestone. Key results: 377/377 tests pass (307 M1–M5, 70 M6); against the real 300-record dataset, **false-auto-resolution rate 0.0000**, audit chain valid across 3,485+ events in every full-dataset run, the self-challenge rule (`POLICY-CONFLICT-001`) confirmed firing on real contradicted cases, and the exact ₹9.83 fee-mismatch residual example from the brief's own "winning demo" narrative reproduced against real data (`ORD-`-series `unexplained_difference` archetype: expected 7673.60, observed 7663.77). One real performance/architecture finding (not a correctness bug): `get_decision_provenance` re-verifies the *entire* ledger on every call by design (a tamper anywhere should invalidate every decision's provenance, not just the tampered one), which does not scale flatly with ledger size — documented in `docs/audit-ledger.md` rather than silently left unmeasured. Full detail in `CLAUDE.md`'s M6 entry.

---

### Note: "Milestone 7" as actually implemented (2026-08-27)

The user's seventh implementation session defined "Milestone 7: End-to-End Reconciliation & Unified Decision Pipeline" as a pure INTEGRATION milestone — not a new numbered milestone in this plan's original 19, but an explicit instruction to make all of M1–M6's already-completed capabilities operate as ONE coherent system rather than a collection of independently-callable modules. Delivered as `app.services.reconciliation_pipeline.run_reconciliation_pipeline`, one orchestrator that calls `ingest_source_directory` (M1) → `run_exception_intelligence` (M2+M3) → `run_decision_pipeline` (M6, per exception, itself already wiring M4's AI investigation → M6's challenge/contradiction check → M2/M4's deterministic verification → M3's risk scoring → M5's policy/resolution/review) → `verify_chain`/`AuditLedger.count()` (M6), with a `run_id` threaded through (an additive, optional parameter added to M6's `decision_service.run_decision_pipeline`, not a rewrite of it) so `run -> exception -> investigation -> decision -> audit` stays reconstructable from the ledger alone. `python scripts/run_reconciliation.py` is the one command that runs the whole thing end-to-end — no manual per-milestone script execution required. This maps most closely onto this plan's original M16 ("the one finance-ops loop closes end-to-end," minus any UI) without actually being M16 — M7 explicitly excludes the dashboard/frontend, which remains fully unscoped-until-later per M16/M17/M18 below. It also overlaps partially with M13's original "evaluation/metrics engine" scope (M7's own 300-record end-to-end evaluation lives as pytest assertions in `backend/tests/pipeline/test_evaluation_m7.py`, not as a standalone reusable `evaluation/run_eval.py` module) — M13 itself is left at its prior PARTIALLY DONE status, since no new dedicated evaluation module was built here.

Key results: 399/399 tests pass (377 M1–M6, 22 M7), zero regressions. Against the real 300-record dataset, run through the ONE orchestrator call (not assembled from separately-run engines): **false-auto-resolution rate 0.0000**, 219 auto-resolved / 67 human review / 2 rejected(blocked) / 12 unresolved (exactly matching M4/M5/M6's own prior per-milestone numbers — the orchestration layer changes nothing about the actual decisions), audit chain valid, 3,486 audit events for this run, ~81 records/sec (MockAIProvider, no network latency). All 5 Phase-22 golden end-to-end cases pass (clean exact match auto-resolves; adversarial fee-mismatch never auto-resolves; ambiguous match always reaches human review; a HIGH/CRITICAL-risk case always requires approval; a contradicted AI hypothesis can never force a resolution). One real, documented finding from Phase 18 (idempotency): `ResolutionProposal.proposal_id` is randomly generated fresh on every call, so two independent full pipeline runs of the identical input do NOT collide on M5's existing idempotency key and each produces its own, separately-auditable review request — the correct, verified answer turned out to be "each run is a new, explicitly identified run" (one of the three behaviors the brief itself allowed), not "recognize the existing run," since nothing in this system ever executes real financial movement for there to be duplicate state of in the first place. Full detail in `CLAUDE.md`'s M7 entry and `docs/end-to-end-pipeline.md`.

---

### Note: "Milestone 8" as actually implemented (2026-08-27)

The user's eighth implementation session defined "Milestone 8: Production-Style API / Application Service Layer" as a pure TRANSPORT-boundary milestone — expose M1–M7's already-complete capabilities through a typed HTTP API, without becoming a second decision authority. This is the "caller" every prior milestone's own dated decision was waiting for before building an HTTP layer (M1/M2's ingest endpoint, M6's `GET /api/audit`, M7's API-layer seam) — none of those deferred endpoints were built as originally sketched; M8 instead built the actual, real API surface a caller needs today. Delivered: `backend/app/main.py` (the FastAPI app named in M0's original file list, built here instead, 8 milestones later, once a real need existed) and `backend/app/api/` (`schemas.py`, `dependencies.py`, `run_registry.py`, `errors.py`, `router.py`, `routes/{health,runs,exceptions,audit}.py`). Seven endpoints: `GET /health`, `POST /runs` (calls `run_reconciliation_pipeline`, M7, exactly once), `GET /runs/{run_id}`, `GET /exceptions` (paginated, filtered by run_id/category/risk_level/decision), `GET /exceptions/{exception_id}`, `GET /exceptions/{exception_id}/provenance` (calls M6's `get_decision_provenance` directly), `GET /runs/{run_id}/audit` (calls M6's `AuditLedger`/`verify_chain` directly). Three new `Capability` values (`VIEW_RUN`/`VIEW_PROVENANCE`/`START_RECONCILIATION`) extend M5/M6's existing authorization model exactly as M6 extended it for its own 3 audit capabilities — granted to `HUMAN`/`SYSTEM`, deliberately withheld from `AI`. No new decision authority, no force-resolve endpoint, no financial-mutation endpoint, no dashboard/frontend (that remains M16/M17's scope).

Key results: 442/442 tests pass (399 M1–M7, 43 M8), zero regressions. The real 300-record dataset run end-to-end through `HTTP -> POST /runs -> M7 -> M1-M6 -> HTTP response`: **false-auto-resolution rate 0.0000** (verified via the API's own paginated exception listing, not by reading internal state), audit chain valid, decision distribution exactly matching the underlying `PipelineRunResult` (219/67/2/12, unchanged from M7). API overhead measured separately from pipeline processing: ~0.6% of total HTTP round-trip time. One real, worth-recording finding (not a bug): `backend/app/main.py` needed the same repo-root/`backend` `sys.path` bootstrap every `scripts/*.py` entry point already does before importing `app.*`/`shared` — `uvicorn app.main:app` has no pytest `conftest.py` to have set that up first, and would otherwise crash with `ModuleNotFoundError: No module named 'shared'` on a fresh process; fixed in `app/main.py` itself, consistent with the existing per-entry-point convention.

---

### Note: "Milestone 9" as actually implemented (2026-08-28)

The user's ninth implementation session defined "Milestone 9: Adversarial Evaluation, Robustness & Financial Safety Validation" as an EVALUATION + HARDENING milestone — not a new engine, a deliberate attempt to break M1–M8 before a judge does. Delivered: `backend/tests/adversarial/` — a reusable mutation framework (`helpers.py`: a generic `clone()` over any M1 SQLAlchemy model, `Dataset`/`Scenario`/`DecisionEnvironment`, `analyze()`/`decide_one()` runners) plus 14 attack-category test files (identifier manipulation, amount manipulation, fee manipulation, settlement manipulation, refunds, timing manipulation, ambiguous matching, duplication/replay, missing data, contradictory data, AI misleading-evidence, policy manipulation, audit tampering, API-level attacks — each mapped to the brief's own lettered categories A–N), plus `test_invariants.py` (10 named safety invariants), `test_safety_matrix.py` (the required scenario/expected/actual/pass-fail matrix and decision-safety metrics), `test_classification_metrics.py` (exception-category confusion matrix, precision/recall/F1 — computed only because that task genuinely is a classifier), `test_mutation_testing.py` (3 controlled constant/logic mutations via `monkeypatch`, proving the real tests are sensitive to them), `test_fuzz.py` (60 seeded, deterministic randomized cases, seed 90210), and `test_baseline_comparison.py` (re-locks the exact clean-dataset distribution).

Two real, genuine safety defects were found empirically — exactly the outcome this milestone exists to produce — and fixed at their root, per the brief's own "stop, root-cause, fix the smallest layer, add a regression test, rerun everything" instruction:

1. **`verify_refund_consistency` (`app.engines.reconciliation.verification`)** matched each refund against *any* same-amount debit without tracking which debits were already claimed, so a duplicated refund record could double-claim a single real debit and corrupt `decompose_discrepancy`'s reported residual (found via `test_refund_manipulation.py`). Traced end-to-end and confirmed this was **contained by M2's own defense-in-depth** (`VERIFIED` status is gated by M2's independently-computed match status, never by this decomposition) — a real explainability defect, never an unsafe auto-resolution. Fixed by tracking claimed debit IDs in a set.
2. **`resolve_single_linked_settlement`'s `fee_verified` branch (`app.engines.reconciliation.matching`)** verified only that a settlement's own claimed fee arithmetic was internally consistent with its `FeeRule` — it never cross-checked the actually-confirmed bank credit against that claimed net figure. Seeded fuzz testing (`test_fuzz.py`, seed 90210) found this **did** produce genuine false auto-resolutions (7 of 60 randomized bank-credit mutations on real `fee_mismatch` records reached `SAFE_TO_RESOLVE` with a real, multi-thousand-rupee shortfall reported as `financial_impact=0.00`). Fixed by requiring `bank_amount == settlement.net_amount` before declaring `MATCHED` via `fee_verified`; a fee-math-consistent-but-credit-mismatched case now correctly falls to `MISMATCH` with the real residual reported.

Key results: 442/442 pre-existing tests still pass after both fixes (zero regressions), plus 125 new M9 tests, all passing — 567/567 total. **Unsafe auto-resolution rate 0.0000, critical safety failure count 0**, both measured directly (not assumed). The clean 300-record baseline distribution is **unchanged** (219 auto-resolved / 67 human review / 2 rejected(blocked) / 12 unresolved) after both fixes — re-confirmed via `test_baseline_comparison.py`, since every real record in the dataset already satisfies the newly-added bank-credit cross-check. Exception-category classification remains 100% accurate (macro-F1 1.0000) on the real dataset. Full detail in `CLAUDE.md`'s M9 entry and `docs/adversarial-evaluation.md`.

---

### Note: "Milestone 10" as actually implemented (2026-08-29)

The user's tenth implementation session defined "Milestone 10: Evidence-First Explainability & Financial Decision Trace" as a pure READ/TRACE layer over M2–M6 — not a new decision engine, and explicitly not "making the AI sound intelligent." Delivered: `backend/app/explainability/` (`schemas.py`'s canonical `ExplanationReport` contract — 17 sections per the brief's own Phase 2 list, built by adapting M3's existing `ConstraintResult` into `EvidenceItem` rather than inventing a competing evidence shape; `builder.py`'s `build_explanation()`, reading every field from an already-computed `DecisionResult`/`EvidenceBundle`/`RootCauseResult`/`ContradictionRecord`/`PolicyDecision`, with the one deliberate exception of re-invoking `verify_fee_consistency` purely to recover display detail, never a second fee implementation; `completeness.py`'s per-decision-type required-evidence checker; `provenance_check.py`'s cross-check of every claimed ID against the real decision object and, when supplied, the real audit ledger). A new `GET /exceptions/{exception_id}/explanation` API endpoint reuses M8's existing `Capability.VIEW_PROVENANCE` (no new capability added, so AI actors gain nothing new). `scripts/demo_scenarios_m10.py` delivers the 3 Phase-25 judge demo scenarios through the real pipeline, reproducing the project's own documented ₹9.83 adversarial residual case exactly.

Two real findings surfaced while building this layer, both fixed at the explanation layer only (never touching M2/M3's own business logic, per the brief's explicit "do not duplicate M2–M9 logic" boundary):

1. **M2's authoritative `bundle.reconciliation_status` and M3's independently-computed `NegativeEvidenceReport.accepted_settlement_id` can legitimately disagree** on an ambiguous case, since M3's `evaluate_candidate()` accepts on hard-constraint-passing alone without M2's own score-margin ambiguity rule. Found via a real `ambiguous_match` case. Fixed by having the explanation defer to M2's authoritative status.
2. **`NO_FEE_RULE_APPLICABLE`/`NO_REFUND_ON_RECORD` reason codes collapse two different situations** (genuinely nothing configured/claimed vs. nothing to check because no gap/refund existed) — found via the Phase-25 demo showing a spurious "missing fee rule" line on an otherwise-clean auto-resolved case. Fixed by distinguishing the two using `context.fee_rule_by_method` when available, and excluding `NO_REFUND_ON_RECORD` from the missing-evidence vocabulary entirely.

Key results: 567/567 pre-existing tests still pass (zero regressions), plus 67 new M10 tests across 11 files in `backend/tests/explainability/`, all passing — **634/634 total**. Unsupported-claim rate 0%, provenance validity 100% (verified adversarially — forged IDs, fabricated hypothesis references, broken ledger references all correctly detected, not merely asserted), decision/evidence consistency 100%, calculation consistency 100% (the real ₹9.83 residual reproduced exactly against real data), AI hypothesis/fact distinction 100% (no AI claim ever renders as accepted unless the real verifier passed it AND the real policy decision was `SAFE_TO_RESOLVE`). Performance: building explanations for 40 real exceptions took ~0.08% of the underlying pipeline's own time for those same 40 exceptions, and a dedicated test confirms zero additional calls to `run_exception_intelligence`. Full detail in `CLAUDE.md`'s M10 entry and `docs/explainability.md`.

---

### Note: "Milestone 11" as actually implemented (2026-08-29)

The user's eleventh implementation session defined "Milestone 11: Intelligent Exception Prioritization & Finance Work Queue" as an OPERATIONAL, read-only layer over already-decided exceptions — explicitly not a second decision/policy/risk/approval engine, and not allowed to alter any financial outcome. Phase 1's own repository search (before writing anything) found that `app.policy.risk` (M5) already implements `assess_sla`/`assess_priority` (SLA status, priority tier, priority score, priority reasons, built on M3's own risk-score formula) — written in M5 but **never wired into the real pipeline** (`resolution_service.py` imports both but calls neither; `review_packet.py`'s only consumer was its own test file). M11's job was to finish wiring this existing, tested logic into a real queue and API, extending it with newer M6/M10 signals (contradictions, missing evidence) M5's original formula predates, rather than invent a second priority/SLA formula.

Delivered: `backend/app/prioritization/` (`schemas.py`'s `PrioritizedException`/`QueueSummary`/`ReasonCode`/`RecommendedAction`; `scorer.py`'s `build_prioritized_exception()` — calling M5's `assess_priority`/`assess_sla` verbatim and reading risk/exposure/decision straight from already-computed M3/M5/M6 objects, plus `attach_priority()` integrating with M10's `ExplanationReport` via a new `PriorityInfo` field placed in `app.explainability.schemas` itself to avoid a circular import; `queue.py`'s `get_priority_queue()`/`summarize_queue()`/`QueueFilters` — a deterministic 5-level tie-break sort: priority tier → SLA urgency → exposure → risk → age → exception ID). Two minimal, additive fields on existing objects: `PipelineRunResult.reference_now` (M7) and `ExplanationReport.priority` (M10). A new `GET /exceptions/queue` API endpoint (M8) reuses the existing `Capability.VIEW_EXCEPTION` — no new capability. `scripts/demo_priority_queue.py` delivers the Phase 18 finance-work-queue demo through the real pipeline. `docs/prioritization.md` is the technical explainer.

No new safety defects were found — this milestone reused M5's already-hardened formula rather than writing new financial-decision logic. The main empirical corrections were to two adversarial test assumptions (not real bugs): a "huge amount, low risk" test initially failed to account for M5's own `MAX_AUTO_RESOLVE_EXPOSURE` cap and SLA-breach escalation, both confirmed as correct, intended safety behavior once isolated properly.

Key results: 634/634 pre-existing tests still pass (zero regressions), plus 65 new M11 tests across 8 files in `backend/tests/prioritization/`, all passing — **699/699 total**. Decision invariance proven directly (building or tampering with priority never changes the real `PolicyDecision`, review state, AI outcomes, or contradiction records); 15 numbered adversarial prioritization cases and 10 golden cases all pass; queue ordering is fully deterministic (same inputs → same order, no randomness, no LLM). Performance: prioritizing 40 real exceptions (with M10 explanations) took ~0.09% of the underlying pipeline's own time for those same 40 exceptions; the pure sort/summary layer processes 10,000 synthetic records in well under a second. Full detail in `CLAUDE.md`'s M11 entry and `docs/prioritization.md`.

---

### Note: "Milestone 12" as actually implemented (2026-08-29)

The user's twelfth implementation session defined "Milestone 12: Finance Controller Command Center" as building the judge-facing frontend M1–M11 never had — explicitly NOT permission to rewrite any backend architecture, and explicitly required to visualize/operate M1–M11's existing intelligence rather than add a second one. This maps onto this plan's M0 (frontend scaffold, never done), M16 (Frontend Core Screens), and most of M17 (VaR/why-not-matched/blocked-proposal views, audit viewer) in one consolidated pass — updated in place above.

Delivered: `frontend/` — a React 18 + TypeScript + Vite app (no Tailwind/shadcn/Recharts; see the M12 dated decisions in `CLAUDE.md` for why) with 7 routes (Overview, Work Queue, Exceptions, Exception Detail, Runs, Audit, System Health), a typed API client (`src/api/client.ts`/`types.ts` mirroring `backend/app/api/schemas.py` field-for-field), shared loading/empty/error-state handling, and an `ErrorBoundary` guarding against malformed API responses. Three smallest-additive backend changes were needed and made (`GET /runs` list, `GET /runs/{run_id}/audit/events` list, `ExplanationResponse.priority`) — all pure reshapings of already-computed M1–M11 objects, none touching matching/verification/risk/policy/audit logic; 10 new backend tests cover them (`backend/tests/api/test_m12_additions.py`).

No new safety defects were found or needed fixing — this milestone added a read-only presentation layer over an already-hardened decision pipeline, never new financial-decision code. The frontend contains no financial mutation control anywhere (verified directly by a dedicated test scanning every rendered button), never recomputes the M11 priority queue's order client-side, and always shows AI hypotheses next to their deterministic verification result, never as accepted fact on their own.

Key results: the full M1–M11 backend regression (699 tests) stayed green after the three additive API changes, plus 10 new backend tests (`test_m12_additions.py`) — **709/709 backend tests passing**. Frontend: 14 Vitest/Testing-Library tests across 6 files, all passing, covering Overview/Work Queue/Exception Detail/Runs rendering real API data, structured error/empty/loading states, a 403/503 handled gracefully, malformed-response fallback, and the no-mutation-control invariant. Full detail, including the exact demo flow and golden case, in `CLAUDE.md`'s M12 entry and `docs/frontend.md`.

---

### Note: "Milestone 13" as actually implemented (2026-08-29)

The user's thirteenth implementation session defined "Milestone 13: Competitive Evaluation, Demo Hardening & Winning Validation" as an EVALUATION + HARDENING pass over the complete M1–M12 system — explicitly not permission to add random features, and explicitly required to re-run and re-verify every "current verified" number rather than assume it. This closes out this plan's own M13 (Evaluation/Metrics Engine, updated in place above) plus cross-cutting hardening/documentation work with no single prior milestone number of its own.

Delivered: `scripts/evaluate_competitive_baselines.py` (Baselines A/B/C implemented and measured standalone against the real dataset; Baseline D a labeled proxy over the real system's own AI output, never a second independent pipeline; Baseline E reusing M2's own harness), `scripts/audit_dataset.py` (dataset ID-uniqueness/archetype/adversarial/referential-integrity audit), `backend/tests/api/test_m13_security_audit.py` (14 tests closing the security-audit gap M12's two new endpoints opened), `backend/tests/adversarial/test_m13_decision_authority_audit.py` (8 tests, the one genuine gap in decision-authority coverage — direct exception-state-machine tampering — plus a documented map of where every other named attack type is already proven), `docs/demo-runbook.md` (new — the single judge-facing document: problem, product, demo golden path/setup/failure-fallback, golden case, metrics, safety story, competitive differentiation, reproducibility, financial invariants, failure injection, "why not just Razorpay reports," the live-integration decision, and the full claim-vs-proof matrix), `docs/evaluation.md` (rewritten from a pre-implementation sketch into an actually-measured report).

One real API-consistency defect was found and fixed via this milestone's own Phase 7 security audit: an unmatched route/wrong-HTTP-method request fell through to FastAPI's own default `{"detail": ...}` 404/405 handler instead of this API's structured `{"error": {...}}` contract — not a security leak, but a real inconsistency, fixed with a five-line additive `StarletteHTTPException` handler in `app.api.errors` (full API/adversarial regression, 192 tests, confirmed still green afterward).

Reproducibility was verified empirically, not assumed: three independent full-pipeline runs produced byte-identical category/policy-decision/financial-impact fields for every one of the 300 exceptions and exactly 3,486 audit events every time, while `run_id`/`proposal_id`/`review_id` correctly differed per run (the existing, intentional M7 design).

Key results: 709/709 pre-existing tests still pass (zero regressions), plus 22 new M13 tests, all passing — **731/731 backend tests total**; frontend unchanged at 14/14 (no frontend code touched this milestone). Unsafe/false auto-resolution rate re-confirmed at **0.0000 (0/300)** on the full dataset. The measured competitive baseline contrast: naive fuzzy matching with no verification gate (Baseline C) produces a **14.67% (44/300) unsafe auto-resolution rate** on the identical dataset ReconcileAI resolves at 0.0000%. Full detail, including the complete claim-vs-proof matrix and the ranked test-gap analysis, in `CLAUDE.md`'s M13 entry and `docs/demo-runbook.md`.

---

### Note: "Milestone 14" as actually implemented (2026-08-29)

The user's fourteenth implementation session defined "Milestone 14: Real-World Data Adapters, Production-Readiness & Integration Hardening" as answering whether the system can consume realistic external financial-provider data without changing the trusted reconciliation/decision core — explicitly NOT permission to introduce production financial mutations, use real payment credentials, bypass existing validation, or rewrite the reconciliation engine. This is new scope this plan's original 19 milestones didn't separately name (closest conceptually to a "real-world integration" concern implied but never scoped by M1–M18); recorded here as its own milestone rather than forced into an unrelated existing entry.

Delivered: `backend/app/adapters/` — an isolated provider/source adapter layer (`base.py`, `errors.py`, `config.py`, `money.py`, `timestamps.py`, `id_mapping.py`, `razorpay_mapping.py`, `razorpay_adapter.py`, `pipeline.py`, `status.py`) whose only job is translating realistic Razorpay-shaped (and generic bank/internal-ledger-shaped) external payloads into the EXISTING canonical dict shape `app.ingestion.pipeline.ingest_records` (a non-breaking extraction from `ingest_source_directory`) already validates/normalizes/persists. `data/synthetic/provider_fixtures/` (SYNTHETIC FIXTURE, clearly labeled) — 3 linked scenarios including a payment with a refund the settlement deliberately doesn't reflect, producing a real, honest `MISMATCH` rather than an artificially clean dataset. A new `GET /sources/status` endpoint and a small frontend "Data Sources" section (added to the existing System Health page, not a new dashboard) report each source's honest mode (`SYNTHETIC DATA`/`MOCK PROVIDER`/`LIVE READ-ONLY`/`UNAVAILABLE`) — never claiming LIVE without real, configured credentials.

Three real bugs were found and fixed empirically while building this milestone: (1) the settlement mapper initially required a `currency` field Razorpay's real Settlement entity never actually provides (Razorpay only settles in INR) — fixed with a documented, always-true default. (2) The live-mode pagination heuristic initially compared "items returned == items returned" (trivially always true, would loop forever) — caught by this milestone's own retry test before shipping, fixed to use Razorpay's real, documented `count < requested page size` termination signal. (3) A genuinely flaky new frontend test (`HealthPage.test.tsx`) that `waitFor`'d on a heading present during the loading state instead of the actual data table — reproduced (not a one-off), fixed, and re-confirmed stable across 5 consecutive full test-suite runs.

Both real historical M9 safety defects (duplicated-refund double-claim, fee-consistent-but-bank-credit-mismatched settlement) were re-proven to hold for adapter-sourced data specifically, not just file-sourced data — the verification/matching engines have no way to know (and must have no way to know) where a record originated.

Key results: 731/731 pre-existing backend tests still pass (zero regressions), plus 92 new M14 tests — **823/823 backend tests total**; frontend 14/14 pre-existing plus 2 new — **16/16 total**. The complete provider fixture set was run through the real, unmodified M2–M6 pipeline end to end (adapter → mapping → validation → normalization → ingestion → reconciliation → exception intelligence → AI investigation → self-challenge → verification → risk → policy → decision → audit) with no special fixture-only decision path anywhere (confirmed structurally). Full detail, including the field-by-field mapping tables and the honest production-readiness matrix, in `CLAUDE.md`'s M14 entry, `docs/provider-adapters.md`, and `docs/production-readiness.md`.

---

### Note: "Milestone 15" as actually implemented (2026-08-29)

The user's fifteenth implementation session defined "Milestone 15: Judge-Ready Product Polish, Demo Experience & Winning Demonstration Hardening" as a UX/documentation/demo-experience pass over the complete M1–M14 system — explicitly not permission to add backend complexity, weaken financial safety, or replace deterministic logic with LLM logic. This is a continuation of M12's frontend scope and M13's demo-hardening scope, not a new PROJECT_PLAN.md milestone number of its own — the closest original entries are this plan's M16/M17 (frontend screens), both already substantially superseded by M12's actual delivery.

Delivered: `backend/app/services/safety_metrics.py` + a new `GET /runs/{run_id}/safety-metrics` endpoint — the real, live, ground-truth-compared source for the Overview page's new "impossible to miss" hero metric (Unsafe Auto-Resolution Rate), reporting `available=false` rather than a fabricated number when a run's dataset has no `ground_truth.json`. `frontend/src/components/AiAuthorityDiagram.tsx` (new, reusable "AI investigates → Verification challenges → Policy decides → Audit proves" visual). `frontend/src/pages/AboutPage.tsx` (new, route `/about`, "Why ReconcileAI" in nav) — competitive differentiation (the real, cited M13 baseline numbers), architecture pipeline, security story, and a data-source pointer. Work Queue's P0 rows now get a distinct visual treatment in addition to their existing badge text. `docs/three-minute-demo.md` and `docs/judge-qa.md` (both new). `docs/demo-runbook.md`'s golden path rewritten into the brief's exact 15-step checklist, plus a new Demo Reset subsection.

A repository-wide claim-vs-proof audit (grepping every doc, `CLAUDE.md`, `PROJECT_PLAN.md`, and every frontend page/component for unqualified overclaims) found zero genuine violations — every existing "100%"/"1.0000" claim was already correctly scoped, and the phrase "production ready" does not appear anywhere in the repository even loosely. No fix was needed.

No in-UI "Reset Demo" button was built — documented instead as a two-command local file-delete + restart, since a real button would need the first mutation-shaped endpoint this project has ever had, contradicting the standing "no mutation endpoint anywhere" invariant re-tested every milestone since M8.

Key results: 823/823 pre-existing backend tests still pass (zero regressions), plus 6 new M15 tests — **829/829 backend tests total**; frontend 16/16 pre-existing plus 4 new — **20/20 total**, re-confirmed stable across repeated runs. The 300-record baseline distribution (219/67/2/12) and the real ₹9.83 golden case's full CONTRADICTED→HUMAN_REVIEW→audited path are both unchanged and re-verified — now also confirmed live through the new safety-metrics endpoint itself, not only the pre-existing pytest harness. Honest self-scored judge review (10-point scale): strongest at Financial Safety (10), Technical Depth/Explainability/Measurability (9 each); weakest, honestly, at Scalability (6 — deliberately scoped to a 300-record demo, not something a UI-polish milestone should paper over) and Innovation (7 — the differentiator is disciplined composition, not a single novel algorithm). Full detail, including the complete scoring rationale, in `CLAUDE.md`'s M15 entry.

### Note: "Milestone 16" as actually implemented (2026-08-29)

The user's sixteenth implementation session defined "Milestone 16: Final Winning Hardening, Demo Reliability & Judge-Ready Validation" as a closing hardening/validation pass over the complete M1–M15 system, explicit that it must not redesign the product, replace existing architecture, or add features — only make the existing system more reliable and judge-defensible. This is not a distinct milestone number in this plan's original list; it supersedes and closes out the plan's own scattered M18/"final validation" intent with one concrete pass.

Delivered, across 14 phases: a formal, EXECUTABLE 20-item final financial-safety invariant suite (`backend/tests/adversarial/test_m16_final_safety_invariants.py`, 16 tests, plus `backend/tests/api/test_m16_final_safety_invariants_api.py`, 4 tests, for the items needing `api_client` fixtures) covering every named invariant (AI never final authority, no verification/policy/contradiction/currency/mutation bypass, no forced auto-resolution via confidence or "small amount," no refund double-claims, no bank-credit-mismatch slip-through, no credential/stack-trace leaks, priority/frontend cannot alter backend authority, provider adapter uses the identical validation path). Concurrency/replay/idempotency hardening (`backend/tests/api/test_m16_concurrency_and_replay.py`, 7 tests, real `ThreadPoolExecutor` concurrency against FastAPI's `TestClient`) confirming repeated ingestion/pipeline runs/API run requests and concurrent reads never corrupt state or the audit chain, while preserving the existing "each `POST /runs` is its own new, independently-auditable run" design (no new dedup/mutation machinery invented). Provider failure simulation strengthening (`backend/tests/adapters/test_m16_provider_failure_simulation.py`, 5 tests: 502/503 retry-then-fail, malformed JSON, missing/short-page schema drift) — proving a provider failure never becomes fabricated financial data, one real bug found and fixed in the process (below). A performance benchmark (`scripts/benchmark_full_pipeline_m16.py`, reusing `scripts/benchmark_reconciliation.py`'s existing generator, never duplicated) at 300/1,000/5,000/10,000 records for the deterministic stages and 300/1,000/2,000 for the full AI+verification+policy+audit pipeline, confirming roughly-linear scaling with no new O(n²) bottleneck. A minimal, real browser E2E suite (`frontend/playwright.config.ts`, `frontend/e2e/smoke.spec.ts`, Playwright/Chromium) — a genuinely new capability, not previously present, exercising the full 14-step judge demo journey in an actual browser and confirming no mutation-shaped control exists anywhere in the UI. `docs/final-validation.md` — the single, complete, 20-section judge-evidence package, every numerical claim naming its exact source. A repository-wide final consistency/overclaim re-audit (banned phrases re-confirmed absent). `CLAUDE.md` updated with the full M16 record, three new dated architectural decisions, and the final test counts.

Two real, non-cosmetic bugs plus one smaller test-tooling collision were found and fixed empirically, none by test-writing alone but by first building the new capability and then having it surface a genuine gap, consistent with this project's whole history:

1. A real Vite dev-server proxy/SPA-route collision (`frontend/vite.config.ts`): a full-page navigation to `/runs` (a real client-side route AND a proxied API path prefix) returned raw backend JSON instead of the React app shell — found only because Playwright performs a real browser navigation with a real `Accept: text/html` header, something Vitest's jsdom-based component tests never exercise. This meant a judge refreshing the Runs/Health/Exceptions page mid-demo would see a blank JSON page, not the app. Fixed with a `bypass(req)` function on the proxy config that serves `index.html` for real page loads while still proxying genuine `fetch()` calls.
2. `RazorpayAdapter._fetch_live_page` (`backend/app/adapters/razorpay_adapter.py`) let a malformed-JSON HTTP response raise a raw, uncaught `json.JSONDecodeError`, bypassing the module's entire typed `ProviderError` taxonomy — found via the new provider-failure-simulation suite. Fixed by isolating the JSON parse into its own try/except, raising `ProviderResponseError` immediately (not retried, since malformed JSON is not a transient network condition).
3. A smaller finding: adding `frontend/e2e/` caused Vitest's own `npm test` to try to execute the new Playwright spec file (a different test API entirely), failing immediately. Fixed by excluding `e2e/**` from Vitest's own test discovery (`vite.config.ts`), confirmed by re-running both suites independently afterward.

Key results: 829/829 pre-existing backend tests still pass (zero regressions), plus 32 new M16 tests — **861/861 backend tests passing**. Frontend Vitest: 20/20 unchanged. Frontend Playwright E2E: 1/1 passing, stable across repeated runs. The 300-record baseline distribution (219/67/2/12), the real ₹9.83 golden case's full path, and the 0.0000% unsafe-auto-resolution rate are all unchanged and re-verified. Full detail, including exact test names, the third bug's description, and the complete final report, in `CLAUDE.md`'s M16 entry and `docs/final-validation.md`.

### Note: "Milestone 17" as actually implemented (2026-08-29)

The user's seventeenth session defined "Milestone 17: Final Winning Audit & Razorpay Buildathon Readiness" as a forensic, judge-facing audit pass over the complete M1–M16 system — explicitly not a coding milestone, with repeated instructions not to code until the audit was complete, not to touch working business logic, and to say plainly if the repository was already strong enough rather than inventing work to justify the milestone. This is not a numbered milestone in this plan's original list; it is the closing readiness review the whole 16-milestone build has been building toward.

Delivered: a full re-verification (not a re-citation) of the AI/verification/policy safety boundary directly from code this session — `app.policy.engine.evaluate_policy` and `app.ai.verifier` were read in full, confirming the fixed 4-tier precedence, the fail-closed default, and the real grounding-validation mechanics; `scripts/evaluate_competitive_baselines.py` and `scripts/audit_dataset.py` were re-run fresh (not reused from a prior run) and reproduced the 300-record distribution and the A–E baseline table exactly; a repository-wide claim-vs-proof grep was re-run fresh and found zero violations, a third independent confirmation after M15's and M16's own passes. Four new documents: `docs/final-winning-audit.md` (the Track 04 requirement table, a 20-criteria winning-readiness score with no inflated values, a ~32-question judge-attack-surface Q&A, the AI-value trace with the honest 75%-hypothesis-rejection-rate flag, the competitive-positioning re-verification, the golden-demo screen audit, and the final P0/P1/P2/P3 action list), `docs/demo-failure-plan.md` (11 named failure modes with detection/recovery/fallback), `docs/presentation-blueprint.md` (a full slide-by-slide structure, since no PPT/deck file exists anywhere in the repository), and `docs/winning-thesis.md` (30-second/60-second/2-minute/one-line versions).

**The single largest finding of this milestone was not a code defect: the repository has never been placed under version control at all** (`git status` returns "fatal: not a git repository," no `.git` directory exists anywhere). Since the Buildathon's own submission format is a public repo plus a pitch video, this is a genuine P0 gap, ranked above every code-level finding — and it was deliberately not fixed unilaterally (see `CLAUDE.md`'s dated 2026-08-29 decision) since initializing version control and deciding what/how to commit ~200 files for the first time is the user's own call (repo name, visibility, license, whether to preserve the 16-milestone history as commits).

No code was changed in this milestone. Every software-facing Track 04 requirement (the agent, the 300-record batch — 6x the 50-record minimum, the honest match-rate/exception reporting, multi-source scope, the safety gate, the audit trail) is a genuine, freshly-re-verified PASS. The only two honestly-low scores in the 20-criteria review (Scalability 6, Innovation 7) were deliberately left as-is rather than "fixed" with infrastructure or a gimmick, consistent with this milestone's own explicit prohibition against adding complexity or fake AI-heaviness purely for appearance.

Key results: 861/861 backend tests, 20/20 frontend Vitest tests, 1/1 Playwright E2E test — all unchanged from M16's closing state, since no code was touched this milestone. Fresh re-runs this session: Baseline C (naive fuzzy, no verification gate) unsafe_auto_resolution_rate=0.1467 (44/300); ReconcileAI's own deterministic layer precision=1.0000/recall=1.0000/incorrect_auto_resolution_rate=0.0000; dataset audit confirmed 300 records, 0 dangling references. Full detail in `CLAUDE.md`'s M17 entry and `docs/final-winning-audit.md`.

---

### M13 — Evaluation / Metrics Engine
**Status:** DONE (2026-08-29) — the "not yet done" items below were closed by the user's thirteenth implementation session ("Milestone 13: Competitive Evaluation, Demo Hardening & Winning Validation") — see its own note at the end of this entry. `evaluation.py` (in the `reconciliation` package) implements the harness for the deterministic engine's own output: precision/recall/F1 (scoped to auto-resolvable cases — see CLAUDE.md's M2 decision on this), false-match rate, incorrect-auto-resolution rate (0 across all 300 records, 5/5 adversarial cases correctly blocked), auto-resolution/human-review/unresolved/ambiguous rates, and the financial totals (correctly/incorrectly-reconciled/unresolved/ambiguous amounts). Root-cause/category accuracy is covered by M3's own `evaluate_exceptions` harness (1.0000 accuracy); full-pipeline decision-safety metrics are covered by `tests/audit/test_evaluation_m6.py` (false-auto-resolution rate 0.0000/300, re-confirmed this milestone). `docs/evaluation.md` was rewritten this milestone from a pre-implementation sketch into an actually-measured report.
**Priority:** CORE MVP
**Goal:** Build the harness (`docs/evaluation.md`) that runs the full pipeline against `ground_truth.json` and reports every metric, honestly, with no suppression of failures.
**Features:** `evaluation/run_eval.py`, machine-readable + human-readable report output.
**Files/components:** `backend/app/evaluation/metrics.py`, `backend/app/evaluation/run_eval.py`.
**Dependencies:** M11 (needs a full pipeline run to evaluate).
**Acceptance criteria:** report includes every metric listed in `docs/evaluation.md`; `incorrect_auto_resolution_rate` and `financial_amount_incorrectly_reconciled` are both `0` on the current fixture — if not, this milestone is not done, the upstream engines are.
**Tests:** the report itself is asserted against known fixture ground truth in CI; this becomes the regression gate for all future milestones.
**Demo outcome:** the `/evaluation` screen's data source (UI wired in M17).
**Estimated complexity:** Medium.
**Must NOT change:** the harness must never filter out or average away a bad result — every case counts individually in the report.

---

### M14 — Synthetic Dataset Scale-Up to 300 + Adversarial Cases
**Status:** DONE (2026-08-25) — delivered early, as part of M1's consolidated scope, since the generator was built at full 300-record scale from the start rather than a small dev fixture (see M1). All acceptance criteria below were met at that time: deterministic generation (verified via `test_generation_is_deterministic_for_a_fixed_seed`), every taxonomy category present multiple times, 5 adversarial cases across `fee_mismatch`/`duplicate`/`ambiguous_match`. Note: M13 (the evaluation harness proper) does not exist yet, so "M13's harness run against this dataset shows 0 incorrect auto-resolutions" below is **not yet verified end-to-end** — only the generator-level tests confirming adversarial cases are internally inconsistent with their fee rule (i.e., correctly *not* mathematically reconcilable) have run so far. Re-verify this milestone's full acceptance criteria once M9/M11/M13 exist.
**Priority:** IMPORTANT
**Goal:** Grow the M1 dev fixture into the full ≥300-record, fixed-seed, ground-truthed dataset covering every taxonomy category multiple times, plus deliberate adversarial cases for M9/M11's safety gates to catch.
**Features:** `data/synthetic/generator.py` v2 (full scale), regenerated `ground_truth.json`.
**Files/components:** `data/synthetic/generator.py`, `data/synthetic/seeds/`.
**Dependencies:** M13 (need the eval harness ready to validate the bigger dataset immediately).
**Acceptance criteria:** 300+ records generated deterministically (same seed → identical dataset); every taxonomy category present multiple times; at least 2–3 adversarial cases specifically designed to tempt an incorrect auto-resolution; M13's harness run against this dataset still shows `0` incorrect auto-resolutions and `0` incorrectly-reconciled amount.
**Tests:** determinism test (re-running the generator with the same seed produces byte-identical output); full-dataset evaluation run.
**Demo outcome:** this is the actual dataset the live demo uses.
**Estimated complexity:** Medium–Large.
**Must NOT change:** the generator must remain seeded/deterministic — no dataset randomness that isn't reproducible.

---

### M15 — Value-at-Risk Prioritization
**Status:** NOT STARTED
**Priority:** IMPORTANT
**Goal:** Compute `Exception.priority_score` from amount at risk, confidence, anomaly severity, frequency, and business impact, and expose an aggregate exposure summary.
**Features:** priority scoring function; `GET /api/dashboard/var`.
**Files/components:** `backend/app/engines/` (priority scoring, colocated with confidence engine or its own module), `backend/app/api/routes_ingest.py`/new route file.
**Dependencies:** M14 (needs the full-scale dataset to be a meaningful ranking, not just a handful of cases).
**Acceptance criteria:** the API returns total ₹ exposure across unresolved exceptions and a ranked list; ranking is stable and explainable (each factor's contribution is visible, not a black-box single number).
**Tests:** unit tests on hand-constructed priority orderings.
**Demo outcome:** the "₹X exposure across N unresolved exceptions" dashboard statement from the demo script.
**Estimated complexity:** Small–Medium.
**Must NOT change:** priority scoring must remain a separate, transparent function from confidence scoring — don't conflate "how sure are we" with "how much money is at stake."

---

### M16 — Frontend Core Screens
**Status:** DONE — delivered as part of M12's "Milestone 12" note below (Overview/Work Queue/Exceptions/Exception Detail), at expanded scope relative to this entry's original `/upload`+`/dashboard` sketch — see the M12 note for what was actually built and why.
**Priority:** CORE MVP
**Goal:** Build `/upload`, `/dashboard`, `/exceptions`, `/exceptions/:id` — enough UI to run the core loop end-to-end visually, without which the product literally cannot be demoed.
**Features:** upload flow calling `POST /api/ingest/batch`; dashboard showing match rate and decision counts; exception list; drill-in showing evidence, hypothesis, verification result, and confidence breakdown.
**Files/components:** `frontend/src/routes/*`, `frontend/src/components/*`, `frontend/src/lib/api.ts`.
**Dependencies:** M11, M13 (needs the backend endpoints those milestones expose).
**Acceptance criteria:** a user can upload the fixture, watch it process, see the match rate, open an exception, and see its full evidence/hypothesis/verification/confidence trail — no placeholder/mock data in the UI layer itself.
**Tests:** at minimum, component smoke tests for each route; one manual end-to-end walkthrough recorded/confirmed before marking done.
**Demo outcome:** the product is now demoable end-to-end for the first time.
**Estimated complexity:** Large.
**Must NOT change:** the UI must not compute or "clean up" any numbers itself — it only displays what the backend already decided; keeps the deterministic/AI boundary honest all the way to the screen.

---

### M17 — Frontend VaR Dashboard, Why-Not-Matched & Blocked-Proposal Views, Audit Viewer
**Status:** PARTIALLY DONE — M12 delivered the audit trail viewer (`/audit`, real event listing + chain-validity), the "why is this prioritized"/exposure view (folded into Work Queue + Exception Detail rather than a separate VaR dashboard route), and the blocked-proposal explanation (Exception Detail's Policy/Final Decision sections render `REJECTED` exactly like every other decision, with its real blocked reasons). **Not built:** a dedicated Recharts VaR dashboard route — M12 deliberately used a plain dependency-free bar chart instead (see the M12 note's design-language section) and folded exposure/risk views into existing pages rather than adding a parallel dashboard route no other screen needed.
**Priority:** IMPORTANT
**Goal:** Add the remaining differentiator-specific screens: VaR exposure view, the "Why NOT Matched" panel per exception, an explicit "blocked" state explanation, and the audit trail viewer with chain-integrity indicator.
**Features:** VaR dashboard (Recharts); why-not-matched panel; blocked-proposal explanation component; `/audit` route.
**Files/components:** `frontend/src/routes/dashboard-var.tsx` (or integrated into `/dashboard`), `frontend/src/routes/audit.tsx`, related components.
**Dependencies:** M12, M15, M16.
**Acceptance criteria:** every screen named in `docs/demo-script.md` steps 10–13 exists and shows real backend data, not mock placeholders.
**Tests:** component smoke tests; manual walkthrough against the M14 dataset confirming the designated adversarial case renders correctly as "blocked" with its specific reason shown.
**Demo outcome:** the full 13-step demo script is now literally walkable end-to-end.
**Estimated complexity:** Medium–Large.
**Must NOT change:** nothing from M16 should need to change to add these — if it does, that's a sign M16 under-scoped its data contracts; flag and fix rather than silently patching around it.

---

### M18 — Demo Script & Polish
**Status:** NOT STARTED
**Priority:** DEMO POLISH
**Goal:** Rehearse and tighten the exact 13-step flow from `docs/demo-script.md` into a real 5-minute walkthrough; visual polish only, no new functionality.
**Features:** final visual styling pass; a scripted/recorded run-through; confirmation that the "wow moment" (M14's adversarial case being blocked) reads clearly on screen and in narration.
**Files/components:** frontend styling only; no backend/engine changes expected.
**Dependencies:** M17.
**Acceptance criteria:** a full run-through completes within 5 minutes and hits all 13 steps; the honest match-rate + unresolved-count are stated together, never one without the other, per `docs/demo-script.md`.
**Tests:** a full manual dry run, timed.
**Demo outcome:** this **is** the final demo.
**Estimated complexity:** Small–Medium.
**Must NOT change:** no engine/policy/threshold logic should be touched during this milestone purely to "make the demo look better" — if a number looks bad, the fix belongs in an earlier milestone with proper review, not a cosmetic patch here.

---

## Summary table

| # | Milestone | Priority | Complexity |
|---|---|---|---|
| M0 | Project foundations & scaffolding | CORE MVP | Small |
| M1 | Data model & dev fixture generator | CORE MVP | Medium |
| M2 | Ingestion + normalization | CORE MVP | Small–Medium |
| M3 | Exact & normalized-reference matching | CORE MVP | Small–Medium |
| M4 | Fuzzy candidate matching & scoring | CORE MVP | Medium |
| M5 | Exception detection & taxonomy | CORE MVP | Medium |
| M6 | "Why NOT Matched" engine | CORE MVP | Small–Medium |
| M7 | Cross-source evidence tools | CORE MVP | Medium |
| M8 | AI investigation agent | CORE MVP | Large |
| M9 | Deterministic verification engine | CORE MVP | Medium–Large |
| M10 | Confidence scoring engine | CORE MVP | Small–Medium |
| M11 | Policy engine + decision routing + audit v1 | CORE MVP | Medium |
| M12 | Hash-chained audit trail + API | IMPORTANT | Small–Medium |
| M13 | Evaluation/metrics engine | CORE MVP | Medium |
| M14 | Dataset scale-up to 300 + adversarial cases | IMPORTANT | Medium–Large |
| M15 | Value-at-Risk prioritization | IMPORTANT | Small–Medium |
| M16 | Frontend core screens | CORE MVP | Large |
| M17 | Frontend VaR/why-not-matched/audit views | IMPORTANT | Medium–Large |
| M18 | Demo script & polish | DEMO POLISH | Small–Medium |

**Critical path:** M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11 → M13 → M16. This is the minimum chain that produces a demoable, safety-gated end-to-end loop. M12, M14, M15, M17 strengthen it; M18 polishes it.

**Highest-risk milestones:** M8 (AI Investigation Agent — the first genuinely novel component, and the one most likely to need iteration) and M9 (Deterministic Verification — the actual safety guarantee the whole positioning depends on). Budget the most review time here.

**Emergency demo cutoff (if time runs out):** a working demo is possible as early as **M11** (full backend loop, no UI — could be shown via API calls/logs in a pinch) and is genuinely presentable at **M16** (core UI). M12/M14/M15/M17/M18 are what take it from "presentable" to "the differentiated pitch in §8 of the context pack." If forced to cut, cut in reverse order starting from M18, then M17, then M15 — never cut M9 or M11's safety gating to save time.
