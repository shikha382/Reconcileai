# AI / Agent Design

## Model abstraction layer

All LLM calls go through a single interface so no code is hard-coded to one vendor:

```python
class LLMProvider(Protocol):
    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...
```

Concrete implementations (`OpenAICompatibleProvider`, `GeminiProvider`) are selected at startup via environment variables: `LLM_PROVIDER` (`openai` / `gemini` / …), `LLM_MODEL`, `LLM_API_KEY`. The rest of the codebase depends only on `LLMProvider`, never on a specific SDK.

Every call to `generate_structured` returns a **validated Pydantic model**, not free text — malformed or schema-violating output is a hard error, not something downstream code has to defensively parse.

## Agent tools (evidence-gathering)

The investigation agent orchestrates a fixed, explicit set of tools — no open-ended free-form tool invention:

- `find_candidate_matches(record)` — returns records within amount/date tolerance from the opposite source
- `get_related_refunds(payment_id)` — refunds linked to a payment
- `get_fee_schedule(method, date)` — applicable `FeeRule` for arithmetic checks
- `get_historical_pattern(customer_ref | method)` — prior settlement behavior for this counterpart
- `get_bank_transactions_near(amount, date)` — bank-side candidates within a window

Every tool call and its result is persisted as an `Evidence` row **before** the agent is allowed to reason over it. The agent cannot reference evidence it didn't actually retrieve through a logged tool call.

## Hypothesis generation

The agent produces a single structured `AIHypothesis`:

```json
{
  "exception_id": "...",
  "proposed_category": "fee_mismatch",
  "proposed_resolution": "auto_resolve",
  "cited_evidence_ids": ["ev_1", "ev_7"],
  "explanation": "Settlement amount equals payment amount minus the standard 0.6% MDR fee for UPI, per fee_rule FR-2026-04.",
  "model_self_reported_signals": { "self_assessed_confidence": 0.9 }
}
```

**Validation gate (before this reaches Policy):**
1. Every ID in `cited_evidence_ids` must exist in the `Evidence` table for this `exception_id`. Any hypothesis citing a non-existent evidence ID is rejected outright and the exception is routed to human review with the rejection logged.
2. Any numeric claim in `explanation` that references an amount must be checkable against the cited evidence's `content` field — this is a lightweight cross-check, not full NLP parsing, but it prevents the "invented number" failure mode.
3. `model_self_reported_signals` is stored for audit/comparison purposes only. **It is never used as the system's confidence score.**

## Confidence scoring (deterministic, not LLM-assigned)

The authoritative confidence score is computed by a plain deterministic function over measurable signals, independent of anything the LLM claims:

- reference similarity (string similarity between references, e.g. RapidFuzz score)
- amount consistency (exact / within-fee-tolerance / mismatched)
- date proximity (days between candidate timestamps, scored against a decay curve)
- merchant/counterparty consistency (match / mismatch)
- source consistency (number of independent sources agreeing)
- fee consistency (does the claimed fee arithmetic actually balance, per `FeeRule`)
- historical pattern match (has this counterpart shown this settlement behavior before)
- number of independent supporting evidence sources

The combination formula (e.g. weighted sum, or a small explicit rule table) lives in one configurable module (`engines/confidence.py`) with weights as named constants, not scattered magic numbers — so thresholds can be tuned against `ground_truth.json` without touching the scoring logic itself.

**Thresholds** (configurable, tuned against ground truth, not guessed):
- `confidence >= AUTO_RESOLVE_THRESHOLD` **and** verification passes **and** no policy rule blocks it → `auto_resolve`
- `HUMAN_REVIEW_THRESHOLD <= confidence < AUTO_RESOLVE_THRESHOLD` → `human_review`
- `confidence < HUMAN_REVIEW_THRESHOLD` → `unresolved`

## Deterministic verification (the actual safety gate)

Independent of the LLM, re-derives the claimed relationship using `Decimal` arithmetic against structured records. Examples:
- Fee-mismatch hypothesis → check `settlement.net_amount == payment.amount - fee_rule.compute(payment)` exactly (within a defined rounding tolerance, e.g. ±₹1 for paisa rounding).
- Duplicate hypothesis → check that the two candidate records genuinely share `order_id`/`reference` and that only one has a corresponding bank credit.
- Split/aggregated settlement hypothesis → check that the sum of the proposed group equals the counterpart amount exactly.

**A hypothesis that fails verification is never auto-resolved, regardless of confidence score.** It is either sent to `human_review` (if confidence was otherwise reasonable) or `blocked` with the failure reason recorded (if the proposal was actively unsafe — this is the "AI proposes something plausible but wrong, verification catches it" demo moment).

## "Why NOT Matched?" (first-class negative-evidence feature)

For every rejected candidate considered during matching (not just the accepted one), store a structured `ReconciliationMatch` row with `status = rejected` and explicit reasons, e.g.:

```json
{
  "candidate": "SETTLEMENT_1029",
  "status": "rejected",
  "reasons": [
    { "signal": "amount_difference", "value": "2400.00" },
    { "signal": "date_difference_days", "value": 6 },
    { "signal": "reference_similarity", "value": 0.31 },
    { "signal": "refund_evidence_conflict", "value": true },
    { "signal": "settlement_balance_check", "value": "fails" }
  ],
  "verdict": "NOT_SAFE_TO_AUTO_RECONCILE"
}
```

This is queried and displayed the same way accepted matches are — "why matched" and "why not matched" are two views over the same `ReconciliationMatch` table, not a bolted-on afterthought.

## Policy engine

Sits after verification, before a decision is finalized. Encodes rules beyond raw confidence, e.g.:
- Any exception with `amount_at_risk` above a configured value always requires human review, regardless of confidence.
- Certain categories (e.g. `reversed_transaction`) always require human review at least once per counterpart before auto-resolution is permitted for that pattern again.
- A hypothesis that failed the evidence-grounding validation is always `blocked`, never routed to auto-resolve even manually — it needs a corrected hypothesis, not an override.

Policy rules are declarative and centrally defined (`engines/policy.py`), not scattered `if` statements across the codebase, so the full rule set can be reviewed/audited in one place.
