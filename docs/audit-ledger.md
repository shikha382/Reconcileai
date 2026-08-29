# Audit Ledger

The persistent, append-only, SHA-256 hash-chained event log added in Milestone 6. This is what makes "complete auditability" (CLAUDE.md's core differentiator #8) durable across process restarts, not just a run's in-memory trace.

## What it is not

Not a blockchain, not a Merkle tree, not distributed infrastructure. One SQLite table (`audit_events`), one linear hash chain, append-only. "The simplest architecture that satisfies the requirements" (M6 brief) — a single previous-hash pointer per event is sufficient to detect tampering in a single-writer, single-ledger system; anything more is speculative complexity this project explicitly avoids (CLAUDE.md's "never add infrastructure just because it sounds impressive").

Tamper-evident, not a cryptographic non-repudiation system — same honesty boundary the M1 design docs already drew for the hash-chaining concept before it was implemented.

## Schema

`AuditEventRecord` (`backend/app/db/models.py`), table `audit_events`:

| Field | Type | Notes |
|---|---|---|
| `event_id` | `str`, PK | `EVT-{16 hex chars}` |
| `sequence` | `int`, unique, indexed by PK-adjacent uniqueness | explicitly assigned by the ledger (`max(sequence)+1`), **not** a DB autoincrement — `event_id` (a string) is already the primary key, and SQLite/SQLAlchemy autoincrement only applies to a single-column integer PK |
| `event_type` | `str` | e.g. `EXCEPTION_CREATED`, `POLICY_EVALUATED` |
| `timestamp` | `datetime` | UTC, naive (stored without tzinfo, consistent with the rest of the codebase) |
| `entity_type` | `str` | currently always `"exception"` |
| `entity_id` | `str`, **indexed** | the exception_id this event is about |
| `actor_type` | `str` | `SYSTEM` / `AI` / `HUMAN` / `POLICY_ENGINE` / `VERIFIER` |
| `actor_id` | `str`, nullable | e.g. `"reconcileai-decision-service"`, `"ai-controller"` |
| `source` | `str` | which module wrote the event, e.g. `"decision_service"` |
| `correlation_id` | `str`, **indexed** | ties every event of one end-to-end investigation together |
| `payload_json` | `str` | Decimal-safe JSON (`shared.money.dumps`), the event's business content |
| `schema_version` | `str` | the hashing schema version *at the time this event was written* — recomputation always uses the event's own stored version, never the current constant, so an old event under an older schema still reproduces its original hash |
| `previous_event_hash` | `str` | the previous event's `event_hash`, or `GENESIS_HASH` for the first event |
| `event_hash` | `str` | this event's own hash |

`entity_id` and `correlation_id` are indexed — added after the M6 performance benchmark showed `get_decision_provenance`/`events_for_correlation` degrading toward a full table scan as the ledger grew (see Performance below).

## Hash chain

`backend/app/audit/hashing.py`:

```
event_hash = SHA256(canonical_json(hashable_payload) + previous_event_hash)
```

where `hashable_payload` is `{schema_version, event_id, event_type, timestamp, entity_type, entity_id, actor_type, actor_id, source, correlation_id, payload}` and `canonical_json` is `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True)` with `Decimal` values serialized as strings (never Python `repr()`, never float).

Genesis: `GENESIS_HASH = SHA256("RECONCILEAI-AUDIT-GENESIS-v1")`, documented and fixed — the first real event's `previous_event_hash` is always this constant.

## Append-only enforcement

`app.audit.ledger.AuditLedger` is the **only** code path allowed to write to `audit_events`. It has no `update`/`delete` method at all — not merely "unauthorized," structurally absent, the same discipline M4 used for the `test_hypothesis` tool not being offered to the AI. `append()`:

- computes `sequence`/`previous_event_hash`/`event_hash` itself
- rejects (`AuditAppendError`) any caller-supplied `previous_event_hash`, `event_hash`, `sequence`, or `event_id` in the payload dict
- adds the row to the caller's SQLAlchemy `Session` but does **not** commit

## Transaction boundary (Phase 15 — audit failure safety)

`append()` deliberately does not commit. The calling code (`app.services.decision_service.run_decision_pipeline`) commits the session once per exception, after all of that exception's audit events and any other state changes for it have been added. This means: if the commit fails, the audit events for that exception roll back together with whatever else was pending in the same transaction — there is no way for a decision to be recorded as having happened while its audit trail silently failed to persist, or vice versa, **within one commit**.

**Limitation, stated plainly:** this transactional guarantee is scoped to a single `Session.commit()` call. It does not, on its own, guarantee atomicity across two separate systems (e.g., if a future version writes the decision to one database and the audit ledger to another). At this milestone's scope — one SQLite session, one commit per exception — the guarantee holds exactly as described. Two adversarial tests in `backend/tests/audit/test_adversarial_m6.py` (`test_11_*`) confirm: a rejected append never silently creates a row, and a forced commit failure (a duplicate `event_id` collision) rolls back an already-`add()`-ed, legitimate event in the same transaction.

## Verification

`app.audit.verify.verify_chain(session)` walks every event in `sequence` order and checks, per event:

1. **Sequence contiguity** — `sequence` must equal the running expected counter starting at 1. Catches deletion, insertion, and reordering directly, independent of any hash check.
2. **Previous-hash linkage** — `previous_event_hash` must equal the prior event's `event_hash` (or `GENESIS_HASH` for the first event). Catches an attacker who recomputes one event's own hash in isolation without fixing up its neighbor.
3. **Hash recomputation** — payload, timestamp, actor, event_type, entity fields are all rehashed (using the event's own stored `schema_version`) and compared to the stored `event_hash`. Catches any field-level tamper that didn't touch `previous_event_hash` or `sequence`.
4. **Payload parseability** — a payload corrupted into invalid JSON is reported as `PAYLOAD_UNPARSEABLE`, not an unhandled crash (found empirically while building this milestone: `verify_chain` originally raised `JSONDecodeError` on this exact input, which is precisely the fail-safe gap Phase 15/18 warns about).

Returns a `ChainVerificationResult(valid, events_checked, first_invalid_event_id, reason, details)`. `reason` is one of `SEQUENCE_GAP_OR_REORDER`, `PREVIOUS_HASH_MISMATCH`, `HASH_MISMATCH`, `PAYLOAD_UNPARSEABLE`, or `EMPTY_LEDGER` (a chain with zero events is valid by definition).

An empty ledger is valid. A chain with events is valid only if every one of the four checks above passes for every event.

## CLI

`python scripts/verify_audit_ledger.py [path/to/database.db]` — prints event count and `Chain: VALID` or `Chain: INVALID` with the offending event, reason, and details. Exit code `0` valid, `1` invalid, `2` database not found.

## Isolated tamper demo

`python scripts/tamper_demo.py` — builds its own isolated database (`scripts/_tamper_demo.db`, deleted before and after the run — **never the real dev database**), runs 30 real exceptions through the full M6 pipeline, shows the chain VALID, tampers one event's payload, shows the chain INVALID with the correct offending `event_id` and `HASH_MISMATCH` reason, then asserts both outcomes and cleans up.

## Performance (Phase 22)

Measured via `scripts/benchmark_audit_ledger.py` at 1,000 / 10,000 / 100,000 synthetic events (direct `AuditLedger` calls, not a full decision-pipeline run — this benchmarks ledger mechanics specifically):

| Events | Append throughput | `verify_chain()` (full pass) | `events_for_correlation()` (mean) | `get_decision_provenance()` (mean) |
|---|---|---|---|---|
| 1,000 | ~1,800/sec | 0.033s | 0.55ms | 22ms |
| 10,000 | ~1,650/sec | 0.146s | 0.21ms | 157ms |
| 100,000 | ~2,230/sec | 1.60s | 0.26ms | 1,525ms |

`events_for_correlation()` stays flat across scale (the `correlation_id` index does its job). `get_decision_provenance()` does **not** stay flat — it scales with total ledger size, because it calls `verify_chain(session)` internally, and that verification deliberately re-walks the **entire** ledger every time, not just the one exception's events. This is a considered choice, not an oversight: `audit_chain_valid` is meant to answer "is the whole trust chain intact," and a tamper anywhere else in the ledger should make every single decision's provenance report `audit_chain_valid=False`, not just the tampered one's. The cost of that guarantee is a full-ledger scan per provenance lookup.

**Known limitation:** at 100,000 events this makes per-exception provenance lookups too slow for a UI rendering many of them in sequence (~1.5s each). A future optimization — periodic checkpointing (verify once, cache the "known-valid up to sequence N" boundary, only re-verify newer events) or an incremental verifier — would fix this without weakening the guarantee, but is out of scope for this milestone; documented here rather than silently left unmeasured.
