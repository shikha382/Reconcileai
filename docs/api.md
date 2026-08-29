# API (Milestone 8)

A typed HTTP window into M1–M7's already-complete reconciliation controller. The API is a **transport boundary only** — it performs no financial matching, fee calculation, AI reasoning, verification, risk calculation, policy evaluation, approval decisions, or audit-chain logic itself. Every route calls straight into the existing M1–M7 service layer and reshapes the result into a public DTO.

```
HTTP Request -> API Route -> Request Schema Validation -> Application Service
             -> Existing M7 Pipeline / M1-M6 Services -> Structured Result
             -> Response Schema -> HTTP Response
```

There is exactly one decision authority throughout: M5's `evaluate_policy`, called inside M6's `run_decision_pipeline`, called by M7's `run_reconciliation_pipeline`. No route reads an AI confidence value, a risk score, or anything else to make its own auto-resolve decision.

## Running it

```
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/docs` for interactive Swagger UI, or `/openapi.json` for the raw schema. `GET /` redirects conceptually to the docs (returns a small pointer JSON, not part of the public API surface).

## Endpoints

| Method | Path | Capability required | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness check |
| POST | `/runs` | `START_RECONCILIATION` | Runs the complete M7 pipeline once, end-to-end |
| GET | `/runs` | `VIEW_RUN` | M12: lists every run this API process has completed, most-recent first |
| GET | `/runs/{run_id}` | `VIEW_RUN` | Returns a previously-completed run's stored summary (never re-runs) |
| GET | `/exceptions` | `VIEW_EXCEPTION` | Paginated, filterable exception list |
| GET | `/exceptions/queue` | `VIEW_EXCEPTION` | M11: the deterministic, prioritized finance work queue for one run |
| GET | `/exceptions/{exception_id}` | `VIEW_EXCEPTION` | One exception's full safe-to-display summary |
| GET | `/exceptions/{exception_id}/provenance` | `VIEW_PROVENANCE` | Calls M6's `get_decision_provenance`/`build_decision_summary` directly |
| GET | `/exceptions/{exception_id}/explanation` | `VIEW_PROVENANCE` | M10 (+M12's `priority` field): the canonical evidence-first explanation (`app.explainability.builder.build_explanation`) |
| GET | `/runs/{run_id}/audit` | `VIEW_AUDIT` | Event count, whole-chain validity, first/last event for the run |
| GET | `/runs/{run_id}/audit/events` | `VIEW_AUDIT` | M12: the full, paginated list of that run's audit events |
| GET | `/sources/status` | `VIEW_RUN` | M14: honest mode/availability/record-count for every configured data source |

### `POST /runs`

Request: `{"dataset": "seeds"}` (optional, defaults to `"seeds"` — the real 300-record M1 dataset). `dataset` names a subdirectory of `app.config.settings.dataset_base_dir` (`data/synthetic/`) — never an absolute path, never a new financial data model. Both the request schema's regex (`^[A-Za-z0-9_\-]+$`, no `.` or `/` characters at all) and a resolved-path containment check in `app.api.routes.runs._resolve_dataset_dir` independently reject any path-traversal attempt.

Calls `app.services.reconciliation_pipeline.run_reconciliation_pipeline` exactly once (verified by `backend/tests/api/test_evaluation_m8.py::test_pipeline_invoked_exactly_once_per_post_runs_call`, which instruments the actual call count, not just reads the code). Response: `RunResponse` — `run_id`, `status`, timestamps, `records_processed`, `matched`, `exceptions`, the real decision-distribution counts (`auto_resolved`/`human_review`/`blocked`/`rejected`/`unresolved`/`escalated`), `audit_event_count`, `audit_chain_valid`, per-stage timings, `errors`, `warnings`.

Two fields worth being explicit about (unchanged from M7, just now visible over HTTP — see `docs/end-to-end-pipeline.md`):
- `exceptions` counts evidence bundles (one per payment, M3's own design), not literally "problems" — `exceptions == 300` while `matched == 219` on the real dataset.
- `blocked` is an exact alias of `rejected`. This codebase's `PolicyDecisionType` enum has no separate `BLOCKED` value; the BLOCK tier's rules produce `REJECTED`. Per the M8 brief's own instruction ("if 'blocked' is only an alias of rejected in the existing taxonomy, do NOT invent a new blocked status merely for the API"), the API does not invent one either.

### `GET /runs`

Milestone 12: the smallest additive change needed for a Runs page. `RunRegistry.list_runs()` (M8) already existed with no route exposing it; this route lists every run the current API process has completed (most-recent-first), reusing the exact same `_to_run_response` shaping `GET /runs/{run_id}` already uses. `RunListResponse` — `{"items": [RunResponse, ...], "total": N}`. In-memory/process-lifetime, same as `RunRegistry` itself (unchanged M8 limitation).

### `GET /runs/{run_id}`

Reads the **stored** `PipelineRunResult` from the in-memory `RunRegistry` (`app.api.run_registry`) — never re-runs the pipeline. Two consecutive `GET`s of the same `run_id` return byte-identical JSON (directly tested).

### `GET /exceptions`

Query parameters, all backed by real domain fields (no fake filters):

- `run_id` — filter to one run (unknown `run_id` returns an empty page, not an error, since it's a legitimate "no matches" filter result)
- `category` — `ExceptionCategory` value (e.g. `fee_mismatch`)
- `risk_level` — `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`
- `decision` — `PolicyDecisionType` value (e.g. `HUMAN_REVIEW`)
- `page` (≥1, default 1), `page_size` (1–100, default 25 — **bounded**, `page_size=100000` is rejected with `422` before touching any data)

Response: `{"items": [...], "page": N, "page_size": N, "total": N}`.

### `GET /exceptions/{exception_id}`

The full safe-to-display summary: category, financial exposure, risk level/score, AI hypotheses (**structured summaries only** — `hypothesis_type`, `claim`, `confidence` — never a raw model prompt or hidden chain-of-thought), challenge/contradiction results, the policy decision (with reasons/blocked_reasons), the final decision, and review state if one exists.

### `GET /exceptions/{exception_id}/provenance`

Calls `app.audit.provenance.get_decision_provenance`/`build_decision_summary` directly — this route contains no provenance-reconstruction logic of its own. Same whole-ledger-verification cost/guarantee documented in `docs/audit-ledger.md` applies unchanged.

### `GET /runs/{run_id}/audit`

`event_count` is this run's own `RUN_STARTED`/`RUN_COMPLETED` bracket plus every one of its exceptions' own events (summed via `AuditLedger.events_for_correlation`, indexed, not a full-table scan). `chain_valid` is the **whole-ledger** `verify_chain` result (M6, unchanged) — a tamper anywhere in the database, not just in this run's own events, makes this `false`. `first_event`/`last_event` are the run's own bracket events (`RUN_STARTED` and `RUN_COMPLETED`/`RUN_FAILED`), not a scan of every event the run touched.

### `GET /runs/{run_id}/audit/events`

Milestone 12: the smallest additive change for a real audit-log viewer (frontend Phase 16). `GET /runs/{run_id}/audit` only ever reduced the ledger to a count + first/last event; this route lists every one of that run's events in full (`event_id`, `sequence`, `event_type`, `timestamp`, `actor_type`, `actor_id`, `entity_type`, `entity_id`, `correlation_id`, and `details` — the event's own stored payload as canonical JSON text, Decimal-safe, never re-derived). Reuses the identical correlation-id aggregation `GET /runs/{run_id}/audit` already performs (this run's own bracket events plus every one of its exceptions' events via `AuditLedger.events_for_correlation`), sorted by the ledger's own gap-free `sequence`. Bounded pagination (1–100, same as every other list route). No second audit mechanism, no independent tamper-check logic — `chain_valid` still only comes from `GET /runs/{run_id}/audit`'s own `verify_chain` call.

### `GET /sources/status`

Milestone 14. Calls `app.adapters.status.get_source_statuses` directly — reads the real `data/synthetic/seeds` dataset, the real `ProviderSettings`, and the real `data/synthetic/provider_fixtures/` files; performs no matching/verification/policy/decision logic. Returns one entry per configured source (`Synthetic Fixture`, `Razorpay Adapter`, `Bank Source`, `Internal Ledger`): `name`, `mode` (`SYNTHETIC DATA` / `MOCK PROVIDER` / `LIVE READ-ONLY` / `UNAVAILABLE`), `configured`, `available`, `record_count` (real, read from disk — `null` when not knowable, e.g. a live source's count without making a network call), and a human-readable `detail`. **Never reports `LIVE READ-ONLY` unless real Razorpay credentials are actually configured** (`app.adapters.config.ProviderSettings.has_live_credentials`) — a fixture-mode adapter never claims to be live merely because the adapter class exists. Reuses the existing `Capability.VIEW_RUN` — no new capability, so an `AI`-labeled actor is refused this route exactly as it already was refused `GET /runs/{run_id}`.

### `GET /exceptions/queue`

Milestone 11. Query parameters: `run_id` (required), `priority`, `risk_level`, `category`, `decision_status`, `sla_status`, `min_age_days`, `min_exposure` (a Decimal string; a malformed value is a clean `400 INVALID_FILTER`, never a crash), plus the standard `page`/`page_size` (bounded 1–100, same as `/exceptions`). Reuses `Capability.VIEW_EXCEPTION` — no new capability, so an `AI`-labeled actor gains nothing new merely because this endpoint exists (it already had `VIEW_EXCEPTION` from M4). Response: `QueueResponse` — a paginated `items` array of `PrioritizedExceptionResponse` (priority, priority_score, risk, exposure, SLA, reason_codes, recommended_action, and `explanation_reference`/`provenance_reference` pointing back at the same exception's `/explanation` and `/provenance` routes) plus a `summary` computed over the *entire* filtered set, not just the current page. Ordering is deterministic (priority tier → SLA urgency → exposure → risk → age → exception ID) and calls no matching, verification, risk, or policy logic itself — see `docs/prioritization.md`.

### `GET /exceptions/{exception_id}/explanation`

Milestone 10. Calls `app.explainability.builder.build_explanation(decision)` directly — this route performs no matching, verification, risk, policy, or audit logic itself, and reruns none of M2–M6's stages. Reuses the existing `Capability.VIEW_PROVENANCE` rather than adding a new capability (see the dated decision in `CLAUDE.md` on why this is a new, dedicated endpoint rather than an extension of `/provenance`: the two contracts serve different concerns — provenance reconstructs the audit-ledger timeline, explanation assembles the full evidence-first decision contract directly from the `DecisionResult` — and the explanation contract is substantially richer, so extending `ProvenanceResponse` in place would have been a breaking change to an already-tested route). Called via the `RunRegistry`, this endpoint does not have access to the raw `ReconciliationContext`/`Payment`/`Settlement` objects, so the fee-verification calculation trace (and the literal `FeeRule` ID) is omitted — never fabricated, just absent; every other section is fully populated. See `docs/explainability.md` for the full contract.

**M12 addition — `priority` field.** The internal `ExplanationReport`/`PriorityInfo` (M11) already carried a `priority` field in `to_dict()`; the public DTO simply hadn't been extended to mirror it, and the route never populated it. Now, when the owning run's `reference_now` (from `RunRegistry`) and the `Payment` (queried from the DB session already injected into this route) are both resolvable, the route calls `build_prioritized_exception`/`attach_priority` (M11, unchanged) and the response's `priority` field is populated with `{priority, priority_score, reason_codes, recommended_action}` — the same values `GET /exceptions/queue` computes for the same exception. When either is unavailable, `priority` is `null` — never fabricated.

## Request/response schemas

Explicit Pydantic DTOs in `app.api.schemas` — `RunCreateRequest`, `RunResponse`, `ExceptionListItem`/`ExceptionListResponse`, `ExceptionDetailResponse` (with nested `HypothesisSummary`/`ChallengeSummary`/`PolicyResultSummary`/`ReviewSummary`), `ProvenanceResponse`, `ExplanationResponse` (M10, mirroring `app.explainability.schemas.ExplanationReport` field-for-field), `QueueResponse`/`PrioritizedExceptionResponse`/`QueueSummaryResponse` (M11, mirroring `app.prioritization.schemas` field-for-field), `AuditStatusResponse`, `HealthResponse`, `ErrorResponse`. No SQLAlchemy model, and no internal dataclass (`EvidenceBundle`, `PolicyDecision`, `ContradictionRecord`, ...) is ever returned directly — every field is explicitly listed and reshaped, so an internal shape can change without silently becoming a public API break, and nothing internal (a raw AI prompt, a filesystem path, a DB credential) can leak through by accident.

## Error model (Phase 7)

Every error response has the same shape:

```json
{"error": {"code": "RUN_NOT_FOUND", "message": "Reconciliation run was not found.", "request_id": "REQ-..."}}
```

| Status | Code | When |
|---|---|---|
| 400 | `INVALID_DATASET` | Unrecognized/unsafe dataset name |
| 400 | `INVALID_ACTOR_TYPE` | Unknown `X-Actor-Type` header value |
| 403 | `FORBIDDEN` | Caller lacks the required capability |
| 404 | `RUN_NOT_FOUND` / `EXCEPTION_NOT_FOUND` | Unknown `run_id`/`exception_id` |
| 422 | `VALIDATION_ERROR` | Pydantic request validation failure (includes field-level `details`) |
| 500 | `INTERNAL_ERROR` | Any unhandled exception — the response body is always generic; the real detail belongs in server logs, never the HTTP response (verified: `backend/tests/api/test_security.py::test_unexpected_internal_error_is_generic_500_no_leak`, which forces a real crash and confirms nothing internal reaches the client) |

409/503 status codes are wired (`ConflictingStateError`, `ServiceUnavailableError` in `app.api.errors`) for future use but no current route raises them — no conflicting-state or dependency-unavailable condition exists yet in this milestone's endpoint set.

## Authorization boundary (Phase 9)

No enterprise IAM. One `Actor` per request (`app.policy.schemas.Actor`, unchanged from M5), resolved by `app.api.dependencies.get_actor`: defaults to `Actor(ActorType.HUMAN, "api-client")`. Every route declares exactly one required `Capability` (`app.policy.authorization.require_authorization`, unchanged from M5/M6) via `require_capability(...)`.

Three new `Capability` values were added (mirroring exactly how M6 added its 3 audit capabilities): `VIEW_RUN`, `VIEW_PROVENANCE`, `START_RECONCILIATION`, granted to `ActorType.HUMAN` and `ActorType.SYSTEM`. `ActorType.AI`'s capability set is **unchanged** by M8 — it still has `VIEW_EXCEPTION`/`INVESTIGATE`/`PROPOSE_RESOLUTION`/`VIEW_AUDIT` from M4/M6, and nothing more. This produces a real, structural boundary, not a cosmetic one: an API caller presenting itself as `ActorType.AI` (via the test-only `X-Actor-Type: AI` header, see below) can call `GET /exceptions` and `GET /exceptions/{id}` (it already had `VIEW_EXCEPTION`) but is refused (`403`) on `POST /runs`, `GET /runs/{id}`, and `GET /exceptions/{id}/provenance` — directly tested in `backend/tests/api/test_authorization.py`.

**`X-Actor-Type`/`X-Actor-Id` headers are not a real authentication mechanism.** They exist only so the authorization boundary is exercisable and testable now, ready for a real auth layer (API keys, OAuth, whatever a later milestone chooses) to plug into the exact same `get_actor`/`require_capability` seam without any route changing.

**No force-resolve endpoint exists.** There is no `POST /exceptions/{id}/force-resolve`, no endpoint that accepts a caller-supplied decision/resolution field and acts on it, and no way for any `Capability` to bypass the verifier, policy, or audit trail — confirmed structurally (`test_no_force_resolve_or_approval_bypass_endpoint_exists`) and behaviorally (extra fields like `force_decision`/`override_policy` in a request body are silently ignored, never acted on).

## Request ID / run ID / correlation ID (Phase 8)

Three distinct identifiers, never confused:

- **`request_id`** — one per HTTP request (`REQ-{16 hex chars}`), generated by `app.main`'s middleware or honored from an incoming `X-Request-ID` header, returned in the `X-Request-ID` response header and in every error body's `request_id` field. Purely an HTTP-layer concern.
- **`run_id`** — one per `POST /runs` call (M7, unchanged), identifies one complete pipeline execution.
- **`correlation_id`** — one per exception (M6, unchanged), threading that exception's own investigation/decision/audit events together; `run_id` is additionally stamped into each exception's `EXCEPTION_CREATED` audit payload (M7), so `run -> exception -> investigation -> decision -> audit` stays traceable end-to-end.

A single HTTP request to `POST /runs` creates exactly one `run_id` (which can have many exceptions, each with its own `correlation_id`) and exactly one `request_id` (the HTTP-layer wrapper around that one call).

## Database session strategy (Phase 14)

One shared SQLite engine/session-factory for the whole API process (`app.api.dependencies`, using `app.config.settings.database_path`, same location M1–M7 already use) — but a **fresh `Session` per request**, opened and closed via a FastAPI dependency (`get_session`), never a global, long-lived session. This is what lets a `POST /runs` call's audit events be visible to a *later*, separate `GET /exceptions/{id}/provenance` request in the same process: they read/write the same database file, each through its own short-lived session.

## Async/sync decision (Phase 15)

Every route is a plain synchronous function. M1–M7 are entirely synchronous (SQLAlchemy's sync API, no async DB driver, no async AI provider call), and FastAPI runs sync route functions in a thread pool automatically — converting the whole system to `async def` throughout would have meant either blocking the event loop on every DB call (wrong) or rewriting SQLAlchemy/`AuditLedger`/`run_decision_pipeline` to be async (a rewrite of "must not touch" M1–M7 code, for no measured benefit at this dataset's scale — see Performance below).

## Pagination (Phase 12)

`page_size` is clamped to `[1, 100]` by the request schema itself (`Query(..., ge=1, le=100)`) — an oversized `page_size` is rejected with `422` before any exception list is even built, not silently truncated after loading everything into memory.

## CORS (Phase 17)

Configuration-driven via `CORS_ALLOWED_ORIGINS` (comma-separated origins in `app.config.settings`). **Empty by default** — no `CORSMiddleware` is even added unless at least one origin is configured, and `allow_origins=["*"]` is never used. A future frontend milestone sets `CORS_ALLOWED_ORIGINS` to its own dev server origin.

## Security (Phase 22)

Verified in `backend/tests/api/test_security.py`: malformed/injection-attempt IDs (`'; DROP TABLE ...`, `<script>...`) resolve to a clean `404`, never a `500` or a reflected value; invalid JSON bodies return `422`, not a crash; unexpected extra request fields (e.g. a smuggled `force_decision`) are silently ignored, never acted on; no financial-mutation endpoint (`/payments`, `/settlements`, `/orders`, ...) exists at all; no force-resolve/bypass/approve/reject endpoint exists; error responses never contain a stack trace, a filesystem path, or a secret-looking string, confirmed even when a route is forced to actually crash.

## Performance (Phase 21)

Measured via `scripts/benchmark_api_overhead.py`: on the real 300-record dataset, HTTP round-trip time and the underlying M7 pipeline's own reported `duration_seconds` differ by roughly **0.6%** — the transport layer (routing, dependency resolution, Pydantic serialization) adds on the order of tens of milliseconds against a multi-second pipeline run. The API does not materially distort the M7 benchmark.

## Local development

```
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/runs -H "Content-Type: application/json" -d '{"dataset": "seeds"}'
curl http://127.0.0.1:8000/runs/RUN-xxxxxxxxxxxx
curl "http://127.0.0.1:8000/exceptions?run_id=RUN-xxxxxxxxxxxx&decision=HUMAN_REVIEW&page_size=5"
curl http://127.0.0.1:8000/exceptions/EXC-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/provenance
curl http://127.0.0.1:8000/runs/RUN-xxxxxxxxxxxx/audit
```

## Known limitations

- **`RunRegistry` is in-memory, process-lifetime only** (same reasoning already established for `ApprovalWorkflowStore` in M5 and `AIInvestigationTrace` in M4) — a process restart loses the ability to `GET /runs/{run_id}`/`GET /exceptions`/`GET /exceptions/{id}` for runs executed before the restart. The durable record of what actually happened still lives in the audit ledger regardless (`GET /runs/{run_id}/audit` and `GET /exceptions/{id}/provenance` both read the real, persistent database) — only the rich in-memory decision objects behind the list/detail endpoints would need re-deriving, and no caller needs cross-restart survival yet.
- No approval/review-decision endpoint exists (Phase 10: "if it is not necessary yet, do not invent it") — the API can observe that a review is required and its state, but cannot submit an approval or rejection through HTTP this milestone.
- The `X-Actor-Type`/`X-Actor-Id` headers are a test/demonstration seam for the authorization boundary, not a real authentication mechanism — a production deployment needs a real identity layer (API keys, OAuth, mTLS, whatever fits) plugged into the same `get_actor` dependency.
- No rate limiting, no request body size limit beyond what FastAPI/Starlette apply by default — acceptable for a synchronous, single-process hackathon demo API, not yet hardened for adversarial internet traffic.
