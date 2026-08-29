"""Deterministic AI routing/triage -- do not send every exception to the
LLM. VERIFIED (M3) exceptions never need AI at all."""
from app.ai.routing import needs_ai_investigation
from app.engines.root_cause.result import (
    AMBIGUOUS,
    CONTRADICTED,
    PARTIALLY_EXPLAINED,
    UNEXPLAINED,
    VERIFIED,
    RootCauseResult,
)


def _root_cause(status: str) -> RootCauseResult:
    from decimal import Decimal

    return RootCauseResult(exception_id="EXC-1", root_cause="x", status=status, financial_delta=Decimal("0"), explained_amount=Decimal("0"), unexplained_amount=Decimal("0"))


def test_verified_never_needs_ai():
    assert needs_ai_investigation(_root_cause(VERIFIED)) is False


def test_partially_explained_needs_ai():
    assert needs_ai_investigation(_root_cause(PARTIALLY_EXPLAINED)) is True


def test_unexplained_needs_ai():
    assert needs_ai_investigation(_root_cause(UNEXPLAINED)) is True


def test_contradicted_needs_ai():
    assert needs_ai_investigation(_root_cause(CONTRADICTED)) is True


def test_ambiguous_needs_ai():
    assert needs_ai_investigation(_root_cause(AMBIGUOUS)) is True


def test_full_dataset_routing_matches_m3_status_distribution(full_exception_intelligence):
    """Cross-check: the number of records routed to AI should equal
    exactly the non-VERIFIED count from M3's own report (counted directly,
    not back-derived from a rounded rate)."""
    from app.engines.root_cause.result import VERIFIED

    bundles = full_exception_intelligence["bundles"]
    non_verified_count = sum(1 for b in bundles if b.root_cause.status != VERIFIED)
    routed_to_ai = sum(1 for b in bundles if needs_ai_investigation(b.root_cause))
    assert routed_to_ai == non_verified_count
