# Provider Adapters (Milestone 14)

Answers the question M14 exists to answer: **can this system consume realistic external financial-provider data without changing the trusted reconciliation/decision core?** Yes — through an isolated adapter layer (`backend/app/adapters/`) whose only job is data translation. Nothing in this package matches, verifies, scores risk, evaluates policy, reasons with AI, or prioritizes — every one of those remains exactly the existing M2–M11 code, untouched.

## Why this exists (Phase 0 finding)

Before writing any code, the existing ingestion contract was inspected (`backend/app/ingestion/pipeline.py`, `backend/app/schemas/records.py`, `backend/app/engines/normalization.py`). No provider/source adapter abstraction existed yet — M1's `ingest_source_directory` reads JSON files from a directory and feeds them through `normalize_record` → `validate_batch` → `session.merge`. M14 adds a new source *in front of* that exact same path, not a parallel one.

## Architecture

```
External Source (Razorpay / bank export / internal ledger)
      ↓
RazorpayAdapter.fetch_records()        -- retrieval + pagination + retry/error handling ONLY
      ↓
razorpay_mapping.map_*()               -- field translation to the canonical dict shape
      ↓
app.ingestion.pipeline.ingest_records()  -- THE EXISTING M1 PATH: store raw → normalize → validate → persist
      ↓
app.engines.reconciliation / app.engines.exceptions / app.ai / app.policy / app.audit
      -- entirely unmodified; these modules cannot tell where a record came from, by design
```

`app.ingestion.pipeline.ingest_source_directory` (file-based) and `app.adapters.pipeline.ingest_from_provider` (adapter-based) now both call the same shared `ingest_records(session, source_type, raw_records, raise_on_invalid=...)` — a pure extraction, zero behavior change for the pre-existing file-based caller (confirmed: the full M1–M13 regression, 731 tests, stayed green after this refactor).

## Source types (Phase 2)

| `SourceType` | Canonical key | Represents |
|---|---|---|
| `RAZORPAY_PAYMENT` | `payment` | A Razorpay Payment entity |
| `RAZORPAY_SETTLEMENT` | `settlement` | A per-transaction settlement-reconciliation line |
| `BANK_TRANSACTION` | `bank_transaction` | A generic bank-statement-export line |
| `INTERNAL_ORDER` | `order` | A generic internal order-management-system export |
| `REFUND` | `refund` | A Razorpay Refund entity |

`FeeRule` is deliberately NOT provider-sourced — fee rules are the merchant's own configured business rules, not something Razorpay's API returns per-transaction; they continue to be ingested via the existing file-based path only.

## The three provider modes

Selected via `PROVIDER_MODE` (`app.adapters.config`), default **`fixture`**:

- **`fixture`** — reads realistic, clearly-labeled SYNTHETIC JSON from `data/synthetic/provider_fixtures/`. What every automated test and the default demo use. Fully offline, fully deterministic.
- **`mock`** — an in-memory, test-supplied page sequence, used only by `backend/tests/adapters/` to exercise exact pagination/retry/rate-limit scenarios without a fixture file.
- **`live`** — a real, read-only HTTP GET against the configured Razorpay API base URL (HTTP Basic auth, standard library `urllib` only, no vendor SDK — matching this project's existing `LLMProvider` precedent). **Never exercised by any automated test in this repository.** No real credentials are checked in; `PROVIDER_MODE` is never set to `live` in CI or by default.

No mode has a method that creates, updates, captures, refunds, or pays out anything. That surface is structurally absent from `RazorpayAdapter` — the same discipline this project already applies to `AuditLedger` having no update/delete method.

## Fixtures (Phase 4) — SYNTHETIC FIXTURE

`data/synthetic/provider_fixtures/` — entirely synthetic, modeled on Razorpay's public API field *shapes*, never real values. Three linked scenarios sharing external IDs across files the way a real provider's data actually links: `RAZ0000001AA` (clean UPI payment, fully settled, bank-confirmed), `RAZ0000002BB` (a payment later partially refunded — the settlement does not reflect the refund, producing a real, honest `MISMATCH` when reconciled, not an artificially clean dataset), `RAZ0000003CC` (a second clean payment, proving more than one record is handled correctly).

## Canonical mapping (Phase 5)

Every mapper (`app.adapters.razorpay_mapping`) returns a `MappingResult` documenting each field's translation:

**Payment** (`map_razorpay_payment`):

| Source field | Canonical field | Transformation | Validation |
|---|---|---|---|
| `id` | `payment_id` | `external_id_to_canonical` (deterministic hash) | matches `^PAY-\d{5}$` |
| `id` | `gateway_ref` | pass-through (the provider's own ID IS the gateway reference) | non-empty string |
| `order_id` | `order_id` | `external_id_to_canonical` | matches `^ORD-\d{5}$` |
| `amount` | `amount` | `minor_units_to_decimal` (paise → INR Decimal) | Decimal, > 0, ≤ 2dp |
| `currency` | `currency` | strip + upper | must be in `ALLOWED_CURRENCIES` |
| `method` | `method` | pass-through | non-empty string |
| `created_at` | `captured_at` | `normalize_provider_timestamp` (Unix epoch → naive UTC) | plausible date |
| `status` | `status` | pass-through | non-empty string |
| `fee`, `tax`, `notes`, `captured`, `international`, `card_id`, `bank`, `wallet`, `vpa`, `email`, `contact` | — | **unsupported** (not applicable to canonical Payment — fee/tax live on Settlement in this project's model) | recorded, never silently dropped |

**Settlement** (`map_razorpay_settlement`): `id`→`settlement_id`, `payment_id`→`payment_id` (or `unsupported_fields` note if absent — never guessed), `amount`→`amount`, `fees`→`fee` (renamed), `tax`→`tax`, **`net_amount` is computed** (`amount − fee − tax`, matching this project's own established semantics, never a second competing definition), `utr`→`utr_reference`, `created_at`→`settled_at`. `currency` defaults to `"INR"` when absent — Razorpay's real Settlement entity has no currency field at all (Razorpay only ever settles in INR), so this is a documented, always-true default, not a guess about financial content.

**Bank transaction** (`map_bank_transaction`): `txn_id`→`bank_txn_id`, `type` (`CR`/`DR`)→`direction` (`credit`/`debit`), `amount`→`amount` via `_parse_rupee_amount` (**bank exports already use decimal rupees, not paise** — see Money safety below), `linked_reference`→`matched_settlement_id`.

**Internal order** (`map_internal_order`): `order_ref`→`order_id`, `amount` via `_parse_rupee_amount` (internal ledgers already use decimal rupees too).

**Refund** (`map_razorpay_refund`): `id`→`refund_id` and →`reference` (dual use, both legitimate), `payment_id`→`payment_id`, `amount`→`amount` (paise), `created_at`→`initiated_at`; `processed_at` = `initiated_at` **if** `status == "processed"` **else** `null` — Razorpay's refund object has no separate processed-at timestamp, so this is an explicit, documented business rule, not a guess.

## Money safety (Phase 6)

Two real, separately-tested conversion paths, never conflated:

- `minor_units_to_decimal` (`app.adapters.money`) — Razorpay's own Payment/Settlement/Refund objects always use integer minor units (paise). Rejects floats, booleans, non-integer strings, and (Phase 25 hardening) **negative amounts**, at the boundary — defense in depth alongside the existing downstream Pydantic check.
- `_parse_rupee_amount` (`app.adapters.razorpay_mapping`) — bank-statement exports and internal ledgers, in this project's modeling, already give decimal rupee strings, not paise. Documented and tested separately (`test_bank_transaction_maps_correctly`, `test_internal_order_maps_correctly`) — never assumed to be the same representation as Razorpay's own paise convention.

`₹4,970.37` is proven (via `test_round_trip_decimal_to_minor_units_and_back`) to survive provider representation → adapter → canonical `Decimal` → database → API with zero binary-float drift, because no float is ever constructed anywhere on this path.

## Timestamp normalization (Phase 7)

`normalize_provider_timestamp` (`app.adapters.timestamps`) accepts a Unix epoch integer (Razorpay's own convention, unambiguous UTC by construction) or an ISO-8601 string carrying an **explicit** UTC offset. An ISO-8601 string with **no** offset is REJECTED outright — never silently assumed to be local time. A plausibility window (2000–2100) catches corrupted epochs (e.g. a millisecond value mistaken for seconds) without hardcoding a business-specific cutoff.

## Identifier normalization (Phase 8)

Real Razorpay IDs (`pay_MSTvS9jf9Zm7lb`) do not match `app.schemas.records`' locked ID regexes (`^PAY-\d{5}$`, matching the synthetic generator's own scheme — documented there as a deliberate MVP limit). Rather than relax that already-tested validation, `external_id_to_canonical` (`app.adapters.id_mapping`) **deterministically derives** a schema-shaped canonical ID via a stable SHA-256 hash of `(source_type, external_id)`. The real external ID is never discarded — it is preserved verbatim in `metadata.external_id` (every mapped record) and in the untouched raw payload every ingested record already gets (`RawRecord`, unchanged M1 behavior). `app.engines.normalization.normalize_reference` (fuzzy, human-entered reference fields) is reused completely unmodified — this is not a second normalization engine, just a translation of the *primary* ID fields normalization never touches anyway.

**Known limitation:** this is a stateless hash, not a persisted external-id → canonical-id table. Collisions are possible in principle but vanishingly unlikely at this project's demo scale (a five-digit ID space against a handful of records). A production system would maintain a real, persisted mapping table instead.

## Raw payload preservation (Phase 10)

Unchanged M1 behavior: `ingest_records` (formerly the inner half of `ingest_source_directory`) calls `_store_raw` for every record **before** normalization, regardless of whether the record arrived via a file or via the adapter. "What did the provider actually send" (`RawRecord.raw_json`) vs. "what did ReconcileAI normalize it into" (the typed ORM row) are always separately reconstructable.

## Schema drift protection (Phase 11) & adversarial testing (Phase 25)

`backend/tests/adapters/test_mapping.py` — missing required field, additional/renamed/wrong-typed field, null amount, negative amount, fractional-paise amount, malformed/missing/null timestamp, empty ID, unexpected nested object, unknown status value (passed through, never guessed into a known one). Every case is either a safe, explicit rejection (`MappingResult.rejection_reason` set, `canonical=None`) or a safe pass-through — never a crash, never a silent reinterpretation.

## Idempotency (Phase 12)

`backend/tests/adapters/test_idempotency.py` proves the EXISTING M1 idempotency guarantee (`session.merge()` keyed on the deterministic canonical ID) holds when records arrive via the adapter: ingesting the identical fixture twice produces no duplicate rows; a legitimately changed payload for the same external ID (e.g. a status update) updates the existing row in place rather than creating a second one.

## Pagination (Phase 13)

`RazorpayAdapter.fetch_records` bounds total pages fetched by `max_pages_per_fetch` (default 50) — never loads an unbounded stream into memory. In `live` mode, pagination follows Razorpay's real documented convention (`count`/`skip` query parameters; a response returning fewer than the requested page size signals the last page) — tested via monkeypatched HTTP responses, never a real network call.

## Retry safety & rate limits (Phase 14/15)

Bounded retries (`max_retries`, default 3; exponential backoff from `retry_base_delay_seconds`) apply only to transient failures (5xx, timeout) — never infinite. A `429` is surfaced immediately as `ProviderRateLimitError` (with `retry_after_seconds` if the provider supplied one), never blindly retried. `401`/`403` are immediate `ProviderAuthenticationError`s, never retried. No exact Razorpay rate-limit numbers are claimed anywhere — this project has no official documentation of them available, and none is asserted.

## Provider error model (Phase 18)

`app.adapters.errors` — `ProviderAuthenticationError`, `ProviderAuthorizationError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderNetworkError`, `ProviderNotFoundError`, `ProviderResponseError`/`ProviderSchemaMismatchError`, `ProviderPaginationError`. No raw provider internals (response bodies, headers, stack traces) ever reach a caller through these.

## Observability, not a second audit system (Phase 19/20)

`ProviderOperationLog` (`app.adapters.pipeline`) records provider, operation, correlation ID, duration, record count, success/failure, and error category for each fetch — plain, in-memory, structured metadata. It is deliberately **never** written to `app.audit.ledger.AuditLedger`: that ledger's meaning is financial-decision provenance (M6), and a provider-fetch operation is not a financial decision. Mixing the two would blur the ledger's own, carefully-established meaning. When adapter-sourced data flows into a real reconciliation run, that run's own `run_id`/`correlation_id` relationships are completely unaffected — the adapter sits entirely upstream of anything audit-relevant.

## Secret safety (Phase 17)

`RAZORPAY_API_KEY`/`RAZORPAY_API_SECRET` are read from the environment only, never given a real-looking default, never included in `ProviderSettings.__repr__`, never included in any `ProviderError` message (tested directly, including under a simulated auth failure), never returned by `/health` or `/sources/status`, never written into an audit-ledger payload (tested directly against a real run's audit events), and never sent to the frontend (the frontend has no code path that could read them — they are backend-only environment variables).

## API (Phase 21) — `GET /sources/status`

Read-only. Reuses the existing `Capability.VIEW_RUN` (no new capability). Reports each configured source's honest mode (`SYNTHETIC DATA` / `MOCK PROVIDER` / `LIVE READ-ONLY` / `UNAVAILABLE`), whether it's configured/available, and its real record count where knowable — **never** reports `LIVE READ-ONLY` unless real credentials are actually configured (a fixture-mode adapter never claims to be live merely because the `RazorpayAdapter` class exists).

## Frontend (Phase 22/23)

A **Data Sources** section was added to the existing System Health page (`frontend/src/pages/HealthPage.tsx`) — not a new dashboard, not a redesign. Shows all four sources from `GET /sources/status` with a mode badge, configured/available/record-count columns, and an explicit disclaimer that `LIVE READ-ONLY` only ever appears when the backend itself reports it.

## Data provenance (Phase 31)

For any provider-sourced record, the full origin chain is reconstructable: `metadata.external_id` + `metadata.source` (set by the mapper) → the untouched `RawRecord.raw_json` (M1, unchanged) → the normalized/validated canonical row. No new schema field was added to support this — the existing `metadata_json` column (already present on every entity table) carries it, additively and without any migration.

## Live integration decision (Phase 30)

**No.** The hackathon demo does not use live Razorpay, and should not by default. Synthetic, deterministic data provides reproducibility, offline operation, known adversarial cases, and known ground truth — all of which a live integration would either weaken or fail to provide at all (a live account has no "ground truth" to grade against). A read-only Razorpay adapter is fully implemented and testable, and could be demonstrated separately with real credentials if ever desired, but it must never become a dependency for the core demo. See `docs/demo-runbook.md` for the corresponding M13-era decision this one extends.

## Known limitations

- `external_id_to_canonical` is a stateless hash, not a persisted mapping table (see Phase 8 above).
- The `live` mode's pagination/retry logic is exercised only via monkeypatched HTTP responses — it has never made a real call to Razorpay's actual API in this environment.
- `FeeRule` records are never provider-sourced; they remain file-based configuration only.
- `ProviderOperationLog` is in-memory/per-call only, not persisted anywhere — consistent with this project's existing "don't build ahead of an actual need" discipline for infra state the audit ledger doesn't need to carry.
