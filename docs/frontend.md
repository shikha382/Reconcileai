# Frontend — Finance Controller Command Center (Milestone 12)

M1–M11 built a complete, safety-gated reconciliation intelligence engine with no window into it beyond raw JSON. M12 builds that window: a judge-facing, finance-controller-grade UI that consumes the existing API (`docs/api.md`) and adds **zero** new financial-decision logic. Every number on screen is read from a live API response; nothing is hardcoded, simulated, or client-computed beyond display formatting and simple counting.

## Why this milestone does not touch the backend's decision logic

Phase 0's own instruction, and the project's standing rule (`CLAUDE.md`'s CORE PRINCIPLE), both forbid a second decision authority. The frontend:

- never re-sorts the priority queue (`GET /exceptions/queue`'s order is rendered as-is — see `WorkQueuePage.tsx`)
- never recomputes risk, exposure, policy, or verification results
- never offers a control that mutates a payment, settlement, bank transaction, refund, or policy decision (Phase 19 — verified directly, see Testing below)
- never lets an AI hypothesis render as an accepted fact — every AI claim is shown next to its deterministic verification result (Phase 10/12)

## Technology chosen

**React 18 + TypeScript + Vite**, matching `docs/architecture.md`'s original sketch. Two deliberate deviations from that original sketch, recorded as dated decisions in `CLAUDE.md`:

- **No Tailwind/shadcn.** A single hand-written CSS file (`src/index.css`) with design tokens (CSS custom properties) gives the same "professional enterprise finance" look with zero build-time CSS tooling and a file a reviewer can read top to bottom.
- **No Recharts.** The one chart this milestone actually needs (Exception Health's category breakdown, Phase 6) is a plain, dependency-free horizontal bar table (`src/components/BarChart.tsx`) — real semantic HTML with a CSS bar overlay, not a charting library pulled in for one bar chart.

**React Router** is the one added navigation dependency — directly justified by the multi-page requirement (Phase 3/7).

No state-management library, no data-fetching library (React Query, SWR, etc.) — a single small hook (`src/lib/useApi.ts`) gives every page identical loading/error/empty handling without one.

## Architecture

```
frontend/
  src/
    api/
      types.ts       TypeScript interfaces mirroring backend/app/api/schemas.py field-for-field
      client.ts      the ONLY place this app calls fetch() -- one function per API endpoint
    components/      shared, reusable presentational pieces (badges, tables, states, timeline, evidence rows)
    context/
      RunContext.tsx the app's one piece of global state -- which run_id is "active" (a UI convenience, not a cache)
    lib/
      format.ts       display-only formatting (INR, dates, title-casing) -- never a financial calculation
      useApi.ts        shared loading/error/ready data-fetching hook
      aggregateExceptions.ts  paginated, bounded client-side COUNTING for the category chart (never a financial sum)
    pages/            one file per route
    test/             Vitest + Testing Library tests, with hand-built fixtures mirroring real API shapes
```

## Routes

| Route | Page | Backend calls |
|---|---|---|
| `/` | Overview | `GET /runs`, `GET /runs/{id}`, `GET /exceptions/queue` (summary only), `GET /exceptions` (paginated, for category counts) |
| `/work-queue` | Work Queue | `GET /runs`, `GET /exceptions/queue` |
| `/exceptions` | Exceptions (list + ID search) | `GET /runs`, `GET /exceptions`, `GET /exceptions/{id}` (search) |
| `/exceptions/:id` | Exception Detail | `GET /exceptions/{id}`, `GET /exceptions/{id}/explanation`, `GET /exceptions/{id}/provenance` |
| `/runs` | Runs (+ Start Reconciliation) | `GET /runs`, `POST /runs` |
| `/audit` | Audit | `GET /runs/{id}/audit`, `GET /runs/{id}/audit/events` |
| `/health` | System Health | `GET /health` |

## The three smallest-additive backend changes this milestone needed

Phase 26 requires the smallest possible additive change when a screen needs something the API doesn't yet expose. Three gaps were found (all in `backend/app/api/`) and closed:

1. **`GET /runs` (list).** `RunRegistry.list_runs()` (M8) already existed; no route exposed it. Added, reusing the exact same `_to_run_response` shaping `GET /runs/{id}` already uses.
2. **`GET /runs/{run_id}/audit/events` (list).** `AuditLedger.events_for_correlation` (M6) already existed; `GET /runs/{run_id}/audit` only ever reduced it to a count + first/last event. Added a paginated listing reusing the identical correlation-id aggregation `get_run_audit_status` already performs.
3. **`ExplanationResponse.priority`.** The internal `ExplanationReport`/`PriorityInfo` (M11) already carried this field in `to_dict()`; the public API DTO simply hadn't been extended to mirror it, and the explanation route never attempted to populate it. Added `PriorityInfoResponse` and wired `get_exception_explanation` to call `build_prioritized_exception`/`attach_priority` when the owning run's `reference_now` and the payment are both resolvable — falls back to `null`, never fabricated, when they aren't.

None of these routes contain matching, verification, risk, policy, or audit logic — each is a pure reshaping of an already-computed M1–M11 object, identical in spirit to every other M8 route. 10 new backend tests (`backend/tests/api/test_m12_additions.py`) cover all three; the full M1–M11 regression suite was re-run afterward and stayed green (see `CLAUDE.md`'s M12 entry for the exact count).

## Design language (Phase 2)

Enterprise finance, not consumer/AI-chatbot: a restrained navy accent, neutral surfaces, semantic colors (green/amber/red) that are **never** the only signal — every status badge pairs a color with a distinct symbol and a text label (✓ / ! / ⛔ / ⚠), per Phase 24. Tabular figures (`font-variant-numeric: tabular-nums`) for every financial column. No gradients, no decorative animation, no chart that doesn't answer a specific finance question.

## AI-is-not-the-decision-maker (Phase 10)

The Exception Detail page renders a strict top-to-bottom flow: **AI Investigation → Deterministic Verification → Policy → Final Decision**, with an explicit "↓" between each stage (`.decision-flow__arrow`). AI confidence is always labeled "advisory only, never authoritative." A contradicted hypothesis renders in a dedicated red callout (`ContradictionCallout.tsx`) showing the AI's claim, the verification's rejection, and the reason — never as accepted fact.

## Safe action boundaries (Phase 19)

There is no button, form, or code path anywhere in `frontend/src` that calls a mutating endpoint — because none exists to call. The only non-GET request the entire frontend makes is `POST /runs` (starting a **new** reconciliation run, not mutating an existing decision). Verified directly: `ExceptionDetailPage.test.tsx`'s "never renders a financial mutation control" test scans every rendered button for force-resolve/approve/override/refund/payout-shaped text.

## Error, loading, and empty states (Phase 22)

`src/lib/useApi.ts` gives every page one of three states (`loading` / `error` / `ready`), rendered by shared `LoadingState` / `ErrorState` / `EmptyState` components (`src/components/StatusStates.tsx`). `ErrorState` renders only the backend's own structured `{code, message, request_id}` — never a stack trace. An `ErrorBoundary` (`src/components/ErrorBoundary.tsx`) wraps every routed page as a last-resort guard against a malformed/unexpected response shape, rendering a generic fallback instead of a blank crashed screen.

## Security (Phase 25)

- No API keys, provider secrets, or environment variables are read or rendered anywhere in the frontend.
- No `dangerouslySetInnerHTML` anywhere in the codebase — every AI-authored or backend-authored string (hypothesis claims, human-readable narrative, audit event payloads) renders through React's normal text nodes, which escape HTML automatically.
- URL parameters (route params, query filters) are only ever used to build API query strings via `URLSearchParams`/`encodeURIComponent`, never interpolated into markup or evaluated.

## Development (dev-server CORS avoidance)

`vite.config.ts` proxies `/health`, `/runs`, and `/exceptions` (every path prefix the API actually serves — see `backend/app/api/router.py`) to `http://127.0.0.1:8000` in dev, so the browser never makes a cross-origin request and no `CORS_ALLOWED_ORIGINS` backend configuration is needed for local demo use.

```
# terminal 1
cd backend && uvicorn app.main:app --port 8000

# terminal 2
cd frontend && npm install && npm run dev
# open http://localhost:5173, go to Runs, click "Start reconciliation"
```

## Demo flow (Phase 27) and golden case (Phase 28)

The demo dataset is the same fixed-seed, 300-record `data/synthetic/seeds` used throughout M1–M11 — nothing was changed to make the demo "look better." The strongest existing case remains the adversarial `fee_mismatch` record already named in M6/M10's own documentation (a synthetic ₹9.83 residual: expected 7673.60, observed 7663.77). It reaches `REJECTED` because the AI's fee-adjustment hypothesis is deterministically contradicted. In the running UI: Overview → Work Queue (filter Blocked + `fee_mismatch`) → Exception Detail shows AI Investigation → Deterministic Verification (CONTRADICTED) → Policy (`POLICY-VERIFIER-FAIL-001`) → Blocked/no action → Audit & Provenance (the real, verifiable chain).

## Testing (Phase 30)

`frontend/src/test/` (Vitest + Testing Library, fixtures shaped exactly like real API responses, `fetch` mocked at the network boundary — no component ever talks to a real server in tests): Overview renders real metrics; Work Queue preserves backend ordering and surfaces reason codes; Exception Detail loads all three real endpoints, renders the AI→Verification→Policy→Decision flow, the contradiction callout, and the provenance timeline, and contains no mutation control; Runs page renders, starts a run, and handles a 503/403 as a structured error, not a crash; shared loading/empty/error states render correctly in isolation; a malformed API response is caught by the `ErrorBoundary` instead of crashing.

Backend: the existing M1–M11 suite plus 10 new tests for the three additive endpoints (`backend/tests/api/test_m12_additions.py`) — see `CLAUDE.md`'s M12 entry for exact counts.

## Known limitations

- The Exceptions list page's "search" (Phase 21) only supports exact `EXC-…` ID lookup against the real API; there is no backend endpoint to search by partial order/payment/settlement ID, so that remains a category/risk/decision filter over the current page rather than a full-text search — documented rather than faked with an unbounded client-side fetch.
- The category-breakdown chart on Overview fetches up to 1,000 exceptions (10 pages × 100) to compute a real client-side count; there is no backend "category counts" aggregate endpoint. Bounded and cheap at this dataset's scale (300 records = 3 requests), but would not scale to a materially larger dataset without a dedicated backend aggregate.
- `RunContext`'s "active run" is a `localStorage` convenience only, scoped to one browser; it is not shared across devices/users and carries no authorization weight (the backend's own authorization boundary, unchanged from M8, is what actually gates every request).
- No real authentication UI — the backend's `X-Actor-Type`/`X-Actor-Id` test/demonstration headers (M8) are not exposed in the frontend at all; every request is the default HUMAN actor, matching the backend's own default.
- Audit event `details` are rendered as raw, collapsed JSON text (Phase 16) rather than a further-parsed, per-field table — a deliberate choice to avoid guessing a schema across every one of M6's many event-payload shapes; still real, complete, and never fabricated.
