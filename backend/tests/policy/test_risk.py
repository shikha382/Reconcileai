"""SLA/aging and deterministic prioritization -- must not simply sort by
amount (a large-but-verified case should not automatically outrank a
smaller, riskier/overdue one)."""
from datetime import datetime, timedelta
from decimal import Decimal

from app.engines.root_cause.result import UNEXPLAINED, VERIFIED, RootCauseResult
from app.policy.risk import assess_priority, assess_sla, risk_level_for_score
from app.policy.schemas import RiskLevel, SLAStatus

from ..reconciliation.factories import make_payment


def _root_cause(status: str, unexplained: str = "0.00") -> RootCauseResult:
    return RootCauseResult(
        exception_id="EXC-1", root_cause="x", status=status,
        financial_delta=Decimal(unexplained), explained_amount=Decimal("0.00"), unexplained_amount=Decimal(unexplained),
    )


def test_risk_level_buckets():
    assert risk_level_for_score(Decimal("100.00")) == RiskLevel.LOW
    assert risk_level_for_score(Decimal("2000.00")) == RiskLevel.MEDIUM
    assert risk_level_for_score(Decimal("20000.00")) == RiskLevel.HIGH
    assert risk_level_for_score(Decimal("200000.00")) == RiskLevel.CRITICAL


def test_sla_within_when_fresh():
    payment = make_payment(captured_at=datetime(2026, 1, 1))
    sla = assess_sla(payment, datetime(2026, 1, 1, 12, 0, 0))
    assert sla.sla_status == SLAStatus.WITHIN_SLA


def test_sla_at_risk_near_due_date():
    payment = make_payment(captured_at=datetime(2026, 1, 1))
    sla = assess_sla(payment, datetime(2026, 1, 6, 12, 0, 0))  # 5.5 days into a 7-day window
    assert sla.sla_status == SLAStatus.AT_RISK


def test_sla_breached_past_due_date():
    payment = make_payment(captured_at=datetime(2026, 1, 1))
    sla = assess_sla(payment, datetime(2026, 1, 10))
    assert sla.sla_status == SLAStatus.BREACHED


def test_verified_zero_residual_is_low_priority():
    payment = make_payment(captured_at=datetime(2026, 1, 1))
    root_cause = _root_cause(VERIFIED, "0.00")
    priority = assess_priority(payment, root_cause, datetime(2026, 1, 1, 12, 0, 0))
    assert priority.priority_level == "LOW"


def test_large_unexplained_and_sla_breach_is_high_priority():
    payment = make_payment(captured_at=datetime(2026, 1, 1))
    root_cause = _root_cause(UNEXPLAINED, "600000.00")  # above CRITICAL threshold
    priority = assess_priority(payment, root_cause, datetime(2026, 1, 20))  # well past due
    assert priority.priority_level == "CRITICAL"
    assert any("breach" in r.lower() for r in priority.priority_reasons)


def test_small_well_explained_case_does_not_outrank_a_risky_one_just_by_amount():
    """A verified (fully-explained) case is not prioritized just because
    the underlying amount happens to be large."""
    payment_large_verified = make_payment(payment_id="PAY-00001", amount="900000.00", captured_at=datetime(2026, 1, 1))
    payment_small_unexplained = make_payment(payment_id="PAY-00002", amount="50000.00", captured_at=datetime(2026, 1, 1))

    verified_priority = assess_priority(payment_large_verified, _root_cause(VERIFIED, "0.00"), datetime(2026, 1, 1, 12, 0, 0))
    unexplained_priority = assess_priority(payment_small_unexplained, _root_cause(UNEXPLAINED, "50000.00"), datetime(2026, 1, 1, 12, 0, 0))

    assert verified_priority.priority_level == "LOW"
    assert unexplained_priority.priority_score > verified_priority.priority_score
