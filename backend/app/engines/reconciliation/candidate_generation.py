"""Stage 4: candidate generation, with blocking/indexing so the engine never
does a naive O(payments x settlements) comparison.

Complexity: building the context is O(P + S) (one pass over payments and one
over settlements to populate the indices below). Looking up candidates for a
single payment is O(1) for the direct payment_id link, and O(k) for the
amount/date-blocked pool, where k is the (small, bounded) number of
settlements sharing that payment's (currency, date-week, amount-band) bucket
-- not O(S). End-to-end candidate generation across all payments is therefore
O(P + S) for indexing plus O(P * k) for lookups, versus O(P * S) naive. See
backend/tests/reconciliation/test_scoring_and_candidates.py and the
benchmark in scripts/benchmark_reconciliation.py for the measured effect at
300 / 1,000 / 5,000 / 10,000 records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement

AMOUNT_BAND_WIDTH = Decimal("50.00")  # candidates within the same Rs 50 band are blocked together
DATE_BUCKET_DAYS = 7  # one bucket per week


def _amount_band(amount: Decimal) -> int:
    return int((amount / AMOUNT_BAND_WIDTH).to_integral_value(rounding=ROUND_FLOOR))


def _date_bucket(dt) -> int:
    return dt.toordinal() // DATE_BUCKET_DAYS


@dataclass
class ReconciliationContext:
    payments: list[Payment]
    settlements: list[Settlement]
    bank_transactions: list[BankTransaction]
    refunds: list[Refund]
    fee_rules: list[FeeRule]

    settlements_by_payment_id: dict[str, list[Settlement]] = field(default_factory=dict)
    unlinked_settlements: list[Settlement] = field(default_factory=list)
    bank_txns_by_settlement_id: dict[str, list[BankTransaction]] = field(default_factory=dict)
    refunds_by_payment_id: dict[str, list[Refund]] = field(default_factory=dict)
    fee_rule_by_method: dict[str, FeeRule] = field(default_factory=dict)
    _blocked_settlements: dict[tuple, list[Settlement]] = field(default_factory=dict)

    def candidates_for(self, payment: Payment) -> list[Settlement]:
        """Direct-link settlements (via payment_id) plus any unlinked
        settlement sharing this payment's (currency, date-bucket +/-1,
        amount-band) block -- covers the aggregation/ambiguous-match cases
        where no FK exists at all."""
        linked = self.settlements_by_payment_id.get(payment.payment_id, [])

        band = _amount_band(payment.amount)
        bucket = _date_bucket(payment.captured_at)
        blocked: list[Settlement] = []
        seen_ids = {s.settlement_id for s in linked}
        for b in (bucket - 1, bucket, bucket + 1):
            for key_band in (band - 1, band, band + 1):
                key = (payment.currency, b, key_band)
                for s in self._blocked_settlements.get(key, []):
                    if s.settlement_id not in seen_ids:
                        blocked.append(s)
                        seen_ids.add(s.settlement_id)
        return linked + blocked


def build_context(
    payments: list[Payment],
    settlements: list[Settlement],
    bank_transactions: list[BankTransaction],
    refunds: list[Refund],
    fee_rules: list[FeeRule],
) -> ReconciliationContext:
    ctx = ReconciliationContext(
        payments=payments,
        settlements=settlements,
        bank_transactions=bank_transactions,
        refunds=refunds,
        fee_rules=fee_rules,
    )

    for s in settlements:
        if s.payment_id:
            ctx.settlements_by_payment_id.setdefault(s.payment_id, []).append(s)
        else:
            ctx.unlinked_settlements.append(s)
            key = (s.currency, _date_bucket(s.settled_at), _amount_band(s.amount))
            ctx._blocked_settlements.setdefault(key, []).append(s)

    for b in bank_transactions:
        if b.matched_settlement_id:
            ctx.bank_txns_by_settlement_id.setdefault(b.matched_settlement_id, []).append(b)

    for r in refunds:
        ctx.refunds_by_payment_id.setdefault(r.payment_id, []).append(r)

    for fr in fee_rules:
        ctx.fee_rule_by_method[fr.method] = fr

    return ctx
