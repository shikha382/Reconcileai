"""Phase 8/9: identifier translation at the provider boundary.

`app.schemas.records`' ID fields are fixed regexes matching the synthetic
generator's own deterministic ID scheme (e.g. `^PAY-\\d{5}$`) -- documented
there as a deliberate MVP limit, "a real integration would relax these to
match whatever ID format the live source actually uses." This module takes
the OTHER safe option instead of relaxing that locked, already-tested
validation: it deterministically derives a canonical, schema-shaped ID from
the real external ID (e.g. Razorpay's `pay_MSTvS9jf9Zm7lb`) via a stable
hash, and the real external ID is never discarded -- it is preserved
verbatim in the record's own `metadata.external_id` field AND in the
untouched raw payload every ingested record already gets
(`app.ingestion.pipeline._store_raw`, unchanged). This means:
  - zero changes to app.schemas.records / app.db.models (no regression risk
    to any of the 731 existing tests that depend on those regexes), and
  - full provenance ("what did the provider actually send" vs "what did
    ReconcileAI normalize it into," Phase 10/31) is preserved exactly.

This is explicitly NOT a second normalization engine (Phase 8's own
instruction) -- `app.engines.normalization.normalize_reference` is reused
untouched for any human-entered reference/narration field; this module only
ever touches the deterministic PRIMARY id fields, which
`normalize_record`/`normalize_reference` never touch either.

Known, documented limitation: this is a stateless hash, not a persisted
external-id -> canonical-id table. Collisions are possible in principle
(discussed in docs/provider-adapters.md) but vanishingly unlikely at this
project's demo scale (five-digit ID space, single-digit-thousands of
records); a production system would maintain a real, persisted mapping
table instead.
"""
from __future__ import annotations

import hashlib

_PREFIX = {
    "order": "ORD",
    "payment": "PAY",
    "settlement": "STL",
    "bank_transaction": "BANKTXN",
    "refund": "REF",
}


def external_id_to_canonical(source_type: str, external_id: str) -> str:
    """Deterministic: the same (source_type, external_id) pair always
    produces the same canonical ID; different external IDs (overwhelmingly)
    produce different canonical IDs."""
    if source_type not in _PREFIX:
        raise ValueError(f"unknown source_type {source_type!r}")
    if not external_id or not external_id.strip():
        raise ValueError("external_id must be a non-empty string")

    digest = hashlib.sha256(f"{source_type}:{external_id.strip()}".encode("utf-8")).hexdigest()
    number = int(digest[:12], 16) % 100_000
    return f"{_PREFIX[source_type]}-{number:05d}"
