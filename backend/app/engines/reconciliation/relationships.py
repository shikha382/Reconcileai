"""Stages 4 (candidate-scored resolution), 7 (one-to-many / split) and 8
(many-to-one / aggregated) -- everything matching.py's single-linked-
settlement path doesn't cover: multiple settlements linked to one payment,
multiple payments aggregated into one settlement, and payments with no
direct link at all (resolved via the blocked candidate pool + scoring).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.models import Payment, Settlement
from app.engines.reconciliation import explanation
from app.engines.reconciliation.candidate_generation import ReconciliationContext, _date_bucket
from app.engines.reconciliation.config import (
    AMBIGUITY_MARGIN,
    AUTO_RESOLVE_SCORE_THRESHOLD,
    ENGINE_VERSION,
    MIN_PLAUSIBLE_CANDIDATE_SCORE,
)
from app.engines.reconciliation.scoring import score_candidate
from app.engines.reconciliation.types import CandidateExplanation, ReconciliationResult
from app.engines.reconciliation.verification import bank_credited_amount
from shared.taxonomy import ReconciliationStatus, RelationshipType

# Bounded to pairs -- the only many-to-one shape actually represented in the
# M1 dataset (see data/synthetic/generator.py's gen_aggregated_settlement).
# A larger K would need a combinatorial search that isn't justified without
# a real case to support it (project rule: don't add complexity speculatively).
MAX_AGGREGATION_GROUP_SIZE = 2


def _base_kwargs(payment: Payment, relationship: RelationshipType) -> dict:
    """Common fields only -- deliberately excludes `candidates` and
    `matched_bank_txn_ids` so every call site passes them explicitly (values
    differ per branch); including them here too would collide with an
    explicit override at the call site."""
    return dict(
        reconciliation_id=str(uuid4()),
        payment_id=payment.payment_id,
        order_id=payment.order_id,
        matched_refund_ids=[],
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        engine_version=ENGINE_VERSION,
        relationship=relationship,
    )


def resolve_multiple_linked_settlements(payment: Payment, settlements: list[Settlement], context: ReconciliationContext) -> ReconciliationResult:
    """More than one settlement is directly linked to this payment. First
    checks whether they form a genuine SPLIT (their confirmed bank-credited
    amounts sum exactly to the payment amount) -- if so, that's a clean
    one-to-many match. Otherwise, per the non-negotiable ambiguity rule,
    multiple settlements that each individually look like a full-amount
    candidate for the same payment must NOT be auto-resolved by picking one,
    even if only one has a confirmed bank credit -- the existence of an
    unexplained duplicate settlement record is itself something a human
    should look at, regardless of which one actually paid out."""
    credited = {s.settlement_id: bank_credited_amount(s, context) for s in settlements}
    confirmed = {sid: amt for sid, amt in credited.items() if amt is not None}

    total_confirmed = sum(confirmed.values(), Decimal("0.00"))
    if confirmed and total_confirmed == payment.amount and len(confirmed) >= 2:
        settlement_ids = list(confirmed.keys())
        return ReconciliationResult(
            **_base_kwargs(payment, RelationshipType.ONE_TO_MANY),
            status=ReconciliationStatus.MATCHED,
            method="split_settlement_sum",
            matched_settlement_ids=settlement_ids,
            matched_bank_txn_ids=[
                b.bank_txn_id
                for sid in settlement_ids
                for b in context.bank_txns_by_settlement_id.get(sid, [])
                if b.direction == "credit"
            ],
            score=Decimal("1.00"), candidates=[],
            why_matched=[f"✓ {len(settlement_ids)} settlements sum exactly to the payment amount (₹{total_confirmed})"],
            why_not_matched=[], differences=[], financial_impact=Decimal("0.00"),
        )

    # Not a clean split -- multiple plausible, non-summing candidates for one
    # payment. Ambiguous by design, regardless of bank confirmation.
    candidates = [
        CandidateExplanation(
            settlement_id=s.settlement_id,
            score=score_candidate(payment, s, context),
            accepted=False,
            why_not_matched=[
                explanation.duplicate_candidates_line(len(settlements)),
                "✓ confirmed bank credit" if s.settlement_id in confirmed else "✗ no confirmed bank credit",
            ],
        )
        for s in settlements
    ]
    base = _base_kwargs(payment, RelationshipType.NONE)
    base["candidates"] = candidates
    return ReconciliationResult(
        **base,
        status=ReconciliationStatus.AMBIGUOUS,
        method="none",
        matched_settlement_ids=[],
        matched_bank_txn_ids=[],
        score=None,
        why_matched=[],
        why_not_matched=[explanation.duplicate_candidates_line(len(settlements))],
        differences=[explanation.duplicate_candidates_line(len(settlements))],
        financial_impact=payment.amount,
    )


def find_aggregations(context: ReconciliationContext) -> dict[str, ReconciliationResult]:
    """Global (not per-payment) pass over the unlinked settlement pool:
    for each unlinked settlement, looks for a pair of no-direct-link
    payments (same currency, nearby date bucket) whose amounts sum exactly
    to the settlement's amount.

    Complexity note: an earlier version of this function used
    itertools.combinations(pool, 2) to search for a summing pair, which is
    O(k^2) per settlement where k is the per-date-bucket pool size. Since k
    itself grows with the total record count N for a fixed calendar-day
    range (more records -> more per bucket, not more buckets), that made the
    whole function effectively cubic in N and was the dominant bottleneck at
    10,000 records in scripts/benchmark_reconciliation.py (throughput
    dropped from ~54k records/sec at 1,000 records to ~4k at 10,000).
    Replaced with an O(k) two-sum hash lookup per settlement (bounded to
    MAX_AGGREGATION_GROUP_SIZE=2, the only shape the M1 dataset actually
    represents), making this function O(S_unlinked * k) overall.
    """
    # NOTE: deliberately blocked by (currency, date bucket) ONLY -- not also
    # by amount band like candidate_generation.py's default blocking. An
    # aggregated settlement's amount is the SUM of its constituent payments,
    # so it lands in a completely different amount band than any one of
    # them; banding by amount here would make aggregation undiscoverable by
    # construction. Date bucketing alone still bounds the search to a small
    # per-week pool.
    linked_payment_ids = {s.payment_id for s in context.settlements if s.payment_id}
    unlinked_payments = [p for p in context.payments if p.payment_id not in linked_payment_ids]

    by_block: dict[tuple, list[Payment]] = {}
    for p in unlinked_payments:
        key = (p.currency, _date_bucket(p.captured_at))
        by_block.setdefault(key, []).append(p)

    results: dict[str, ReconciliationResult] = {}

    assert MAX_AGGREGATION_GROUP_SIZE == 2, "the two-sum hash lookup below is specifically a pairwise (2-way) search"

    for settlement in context.unlinked_settlements:
        bucket = _date_bucket(settlement.settled_at)
        pool: list[Payment] = []
        for b in (bucket - 1, bucket, bucket + 1):
            pool.extend(by_block.get((settlement.currency, b), []))

        credit_amount = bank_credited_amount(settlement, context)
        target = credit_amount if credit_amount is not None else settlement.amount

        # Two-sum via hash lookup: O(k) instead of O(k^2). amount_index maps
        # each amount to the payments sharing it (a plain list handles the
        # rare same-amount-twice case correctly without extra bookkeeping).
        amount_index: dict[Decimal, list[Payment]] = {}
        for p in pool:
            amount_index.setdefault(p.amount, []).append(p)

        found_combo: tuple[Payment, ...] | None = None
        for p in pool:
            if p.payment_id in results:
                continue
            complement = target - p.amount
            for candidate in amount_index.get(complement, []):
                if candidate.payment_id == p.payment_id or candidate.payment_id in results:
                    continue
                found_combo = (p, candidate)
                break
            if found_combo:
                break

        if found_combo:
            combo = found_combo
            if sum((p.amount for p in combo), Decimal("0.00")) == target:
                bank_txn_ids = [
                    b.bank_txn_id
                    for b in context.bank_txns_by_settlement_id.get(settlement.settlement_id, [])
                    if b.direction == "credit"
                ]
                note = (
                    f"✓ {len(combo)} payments ({', '.join(p.payment_id for p in combo)}) "
                    f"sum exactly to settlement {settlement.settlement_id} (₹{target})"
                )
                for p in combo:
                    results[p.payment_id] = ReconciliationResult(
                        **_base_kwargs(p, RelationshipType.MANY_TO_ONE),
                        status=ReconciliationStatus.MATCHED,
                        method="aggregated_settlement_sum",
                        matched_settlement_ids=[settlement.settlement_id],
                        matched_bank_txn_ids=bank_txn_ids,
                        score=Decimal("0.95"), candidates=[],
                        why_matched=[note], why_not_matched=[], differences=[],
                        financial_impact=Decimal("0.00"),
                    )
                # settlement is now claimed by this combo; the outer loop
                # moves on to the next settlement.

    return results


def resolve_unlinked_payment(payment: Payment, context: ReconciliationContext) -> ReconciliationResult:
    """No direct payment_id link, and not part of a discovered aggregation.
    Falls back to scored candidates from the blocked/unlinked pool. Applies
    the non-negotiable ambiguity rule: the top candidate must both clear the
    auto-resolve threshold AND beat the runner-up by at least the configured
    margin, or the result is AMBIGUOUS (if multiple candidates are at least
    plausible) or UNRESOLVED (if none are)."""
    settlement_candidates = [s for s in context.candidates_for(payment) if s.payment_id is None]

    if not settlement_candidates:
        return ReconciliationResult(
            **_base_kwargs(payment, RelationshipType.NONE),
            status=ReconciliationStatus.UNRESOLVED, method="none",
            matched_settlement_ids=[], matched_bank_txn_ids=[], score=None, candidates=[],
            why_matched=[], why_not_matched=["✗ no candidate settlement found for this payment"],
            differences=["no candidate settlement found"], financial_impact=payment.amount,
        )

    scored = sorted(
        (
            CandidateExplanation(settlement_id=s.settlement_id, score=score_candidate(payment, s, context), accepted=False)
            for s in settlement_candidates
        ),
        key=lambda c: c.score.total,
        reverse=True,
    )

    top = scored[0]
    runner_up_score = scored[1].score.total if len(scored) > 1 else Decimal("0.00")
    margin = top.score.total - runner_up_score

    if top.score.total >= AUTO_RESOLVE_SCORE_THRESHOLD and margin >= AMBIGUITY_MARGIN:
        top.accepted = True
        top.why_matched.append(f"✓ top candidate score {top.score.total} clears auto-resolve threshold with margin {margin}")
        settlement = next(s for s in settlement_candidates if s.settlement_id == top.settlement_id)
        return ReconciliationResult(
            **_base_kwargs(payment, RelationshipType.ONE_TO_ONE),
            status=ReconciliationStatus.MATCHED, method="candidate_scoring",
            matched_settlement_ids=[top.settlement_id],
            matched_bank_txn_ids=[b.bank_txn_id for b in context.bank_txns_by_settlement_id.get(top.settlement_id, []) if b.direction == "credit"],
            score=top.score.total, candidates=scored,
            why_matched=[f"✓ matched via candidate scoring (score {top.score.total})"],
            why_not_matched=[], differences=[], financial_impact=Decimal("0.00"),
        )

    # Not safe to auto-resolve, either because the top score didn't clear the
    # bar, or because it did but a rival was too close behind (the
    # non-negotiable ambiguity-margin rule) -- either way, if there's a
    # genuinely plausible candidate, this is AMBIGUOUS (human review), not a
    # flat "nothing found" UNRESOLVED.
    if top.score.total >= MIN_PLAUSIBLE_CANDIDATE_SCORE:
        for c in scored:
            c.why_not_matched.append(f"score {c.score.total} -- not confident enough to auto-resolve (margin {margin})")
        return ReconciliationResult(
            **_base_kwargs(payment, RelationshipType.NONE),
            status=ReconciliationStatus.AMBIGUOUS, method="none",
            matched_settlement_ids=[], matched_bank_txn_ids=[], score=None, candidates=scored,
            why_matched=[],
            why_not_matched=[f"✗ top candidate scored {top.score.total} (runner-up {runner_up_score}) -- not confident enough to auto-resolve"],
            differences=["ambiguous candidates"], financial_impact=payment.amount,
        )

    for c in scored:
        c.why_not_matched.append(f"score {c.score.total} -- below the minimum plausible-candidate floor {MIN_PLAUSIBLE_CANDIDATE_SCORE}")
    return ReconciliationResult(
        **_base_kwargs(payment, RelationshipType.NONE),
        status=ReconciliationStatus.UNRESOLVED, method="none",
        matched_settlement_ids=[], matched_bank_txn_ids=[], score=None, candidates=scored,
        why_matched=[], why_not_matched=[f"✗ best candidate score {top.score.total} is too low to act on"],
        differences=["no sufficiently strong candidate"], financial_impact=payment.amount,
    )
