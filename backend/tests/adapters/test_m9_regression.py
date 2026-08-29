"""Phase 26: re-runs the two real, historical M9 safety defects, but this
time sourcing every record through the adapter/mapping layer instead of
the synthetic file-based generator -- proving both fixes protect
provider-sourced data exactly as they protect file-sourced data (the
verification/matching engines have no idea, and must have no idea, where a
record originally came from).
"""
from __future__ import annotations

from app.adapters.razorpay_mapping import (
    map_bank_transaction,
    map_internal_order,
    map_razorpay_payment,
    map_razorpay_refund,
    map_razorpay_settlement,
)
from app.db.models import BankTransaction, Order, Payment, Refund, Settlement
from app.engines.reconciliation.candidate_generation import build_context
from app.engines.reconciliation.verification import verify_refund_consistency
from app.engines.reconciliation.engine import reconcile_all
from app.ingestion.pipeline import ingest_records
from shared.taxonomy import ReconciliationStatus


def _map_and_ingest(session, canonical_key, raw_records, mapper):
    canonical = [mapper(r).canonical for r in raw_records]
    assert all(c is not None for c in canonical), "test setup itself must produce valid canonical records"
    ingest_records(session, canonical_key, canonical, raise_on_invalid=True)


def test_m9_defect_1_duplicated_refund_cannot_double_claim_a_single_debit(db_session):
    session = db_session
    order = {"order_ref": "order_DUPREFUND1", "customer_ref": "cust_x", "created_at": "2026-08-01T09:00:00+05:30", "status": "created", "amount": "2000.00", "currency": "INR"}
    payment = {"id": "pay_DUPREFUND1", "entity": "payment", "amount": 200000, "currency": "INR", "status": "captured", "order_id": "order_DUPREFUND1", "method": "upi", "captured": True, "created_at": 1785574800, "notes": {}}
    # A single real debit for ONE refund of ₹500.
    debit = {"txn_id": "TXN_DEBIT1", "value_date": "2026-08-01T10:00:00+05:30", "narration": "REFUND-DEBIT", "type": "DR", "amount": "500.00", "currency": "INR"}
    # TWO distinct refund records (different external ids -- e.g. a
    # redelivered webhook that a naive integration created twice) both
    # claiming the SAME ₹500 amount against the SAME payment.
    refund_a = {"id": "rfnd_DUP1_A", "entity": "refund", "amount": 50000, "currency": "INR", "payment_id": "pay_DUPREFUND1", "status": "processed", "created_at": 1785575000, "notes": {}}
    refund_b = {"id": "rfnd_DUP1_B", "entity": "refund", "amount": 50000, "currency": "INR", "payment_id": "pay_DUPREFUND1", "status": "processed", "created_at": 1785575000, "notes": {}}

    _map_and_ingest(session, "order", [order], map_internal_order)
    _map_and_ingest(session, "payment", [payment], map_razorpay_payment)
    _map_and_ingest(session, "bank_transaction", [debit], map_bank_transaction)
    _map_and_ingest(session, "refund", [refund_a, refund_b], map_razorpay_refund)
    session.commit()

    payment_row = session.query(Payment).one()
    bank_txns = session.query(BankTransaction).all()
    refunds = session.query(Refund).all()
    assert len(refunds) == 2  # the duplicate really was ingested -- proving the DEFENSE, not the absence of the attack

    context = build_context([payment_row], [], bank_txns, refunds, [])
    result = verify_refund_consistency(payment_row, context)

    # The M9 fix: only ONE real debit exists, so only one can ever be
    # claimed as evidence -- never two, no matter how many refund records
    # (duplicated or not) claim the same amount.
    assert result is not None
    assert len(result.debit_bank_txn_ids) == 1
    # The second, duplicated refund's ₹500 remains genuinely unexplained --
    # never silently treated as independently confirmed by the same debit.
    from decimal import Decimal

    assert result.unexplained_delta == Decimal("500.00")
    assert result.consistent is False


def test_m9_defect_2_fee_consistent_settlement_with_mismatched_bank_credit_is_not_matched(db_session):
    session = db_session
    order = {"order_ref": "order_FEEBUG1", "customer_ref": "cust_y", "created_at": "2026-08-01T09:00:00+05:30", "status": "created", "amount": "1000.00", "currency": "INR"}
    payment = {"id": "pay_FEEBUG1", "entity": "payment", "amount": 100000, "currency": "INR", "status": "captured", "order_id": "order_FEEBUG1", "method": "upi", "captured": True, "created_at": 1785574800, "notes": {}}
    # Fee-consistent settlement (net_amount = amount - fee - tax, by the
    # mapper's own computation) -- but the bank actually credited LESS than
    # that net_amount (a corrupted/short credit).
    settlement = {"id": "setl_FEEBUG1", "entity": "settlement", "payment_id": "pay_FEEBUG1", "amount": 100000, "fees": 0, "tax": 0, "utr": "UTR_FEEBUG1", "status": "processed", "created_at": 1785575100}
    short_credit = {"txn_id": "TXN_FEEBUG1", "value_date": "2026-08-01T09:15:00+05:30", "narration": "NEFT-UTR_FEEBUG1-SETTLEMENT", "type": "CR", "amount": "900.00", "currency": "INR", "linked_reference": "setl_FEEBUG1"}

    _map_and_ingest(session, "order", [order], map_internal_order)
    _map_and_ingest(session, "payment", [payment], map_razorpay_payment)
    _map_and_ingest(session, "settlement", [settlement], map_razorpay_settlement)
    _map_and_ingest(session, "bank_transaction", [short_credit], map_bank_transaction)
    session.commit()

    payments = session.query(Payment).all()
    settlements = session.query(Settlement).all()
    bank_txns = session.query(BankTransaction).all()

    results = reconcile_all(payments, settlements, bank_txns, [], [])
    result = next(r for r in results if r.payment_id == payments[0].payment_id)

    # The M9 fix: a fee-consistent settlement whose actually-confirmed bank
    # credit does not equal its net_amount must NEVER be declared MATCHED.
    assert result.status != ReconciliationStatus.MATCHED
