"""Milestone 11: deterministic ordering, filtering, and aggregate summary
over a list of already-built `PrioritizedException` records. Pure sorting/
grouping logic -- no financial calculation, no policy, no risk formula.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.prioritization.schemas import PRIORITY_CODE_RANK, PrioritizedException, QueueSummary

# Phase 7's own explicit tie-break order: SLA breach/urgency first, so a
# near-breach LOW-exposure case still outranks a similarly-tiered but fresh
# one within the same priority band.
_SLA_URGENCY_RANK = {"BREACHED": 0, "AT_RISK": 1, "WITHIN_SLA": 2}


def _sort_key(item: PrioritizedException) -> tuple:
    return (
        PRIORITY_CODE_RANK[item.priority],
        _SLA_URGENCY_RANK.get(item.sla_status, 3),
        -Decimal(item.financial_exposure),  # ranking-only normalization; the stored string stays Decimal-exact
        -Decimal(item.risk_score),
        -item.age_days,
        item.exception_id,  # final, stable tie-break -- guarantees a total order regardless of input order
    )


@dataclass
class QueueFilters:
    priority: Optional[str] = None
    risk_level: Optional[str] = None
    category: Optional[str] = None
    decision_status: Optional[str] = None
    sla_status: Optional[str] = None
    min_age_days: Optional[int] = None
    min_exposure: Optional[Decimal] = None


def _matches(item: PrioritizedException, filters: QueueFilters) -> bool:
    if filters.priority is not None and item.priority != filters.priority:
        return False
    if filters.risk_level is not None and item.risk_level != filters.risk_level:
        return False
    if filters.category is not None and item.exception_category != filters.category:
        return False
    if filters.decision_status is not None and item.decision_status != filters.decision_status:
        return False
    if filters.sla_status is not None and item.sla_status != filters.sla_status:
        return False
    if filters.min_age_days is not None and item.age_days < filters.min_age_days:
        return False
    if filters.min_exposure is not None and Decimal(item.financial_exposure) < filters.min_exposure:
        return False
    return True


def get_priority_queue(items: list[PrioritizedException], filters: Optional[QueueFilters] = None) -> list[PrioritizedException]:
    """Deterministic: same inputs always produce the same ordering. No
    randomness, no LLM involvement -- a plain, total-order sort."""
    filtered = [i for i in items if filters is None or _matches(i, filters)]
    return sorted(filtered, key=_sort_key)


def summarize_queue(items: list[PrioritizedException]) -> QueueSummary:
    counts_by_priority = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    total_exposure = Decimal("0.00")
    sla_breached = 0
    sla_at_risk = 0
    highest_exposure_id: Optional[str] = None
    highest_exposure_value = Decimal("-1")
    category_counter: Counter = Counter()

    for item in items:
        counts_by_priority[item.priority] = counts_by_priority.get(item.priority, 0) + 1
        exposure = Decimal(item.financial_exposure)
        total_exposure += exposure
        if exposure > highest_exposure_value:
            highest_exposure_value = exposure
            highest_exposure_id = item.exception_id
        if item.sla_status == "BREACHED":
            sla_breached += 1
        elif item.sla_status == "AT_RISK":
            sla_at_risk += 1
        if item.exception_category is not None:
            category_counter[item.exception_category] += 1

    most_common = category_counter.most_common(1)
    return QueueSummary(
        total=len(items), counts_by_priority=counts_by_priority, total_financial_exposure=str(total_exposure),
        sla_breached_count=sla_breached, sla_at_risk_count=sla_at_risk,
        highest_exposure_exception_id=highest_exposure_id if items else None,
        most_common_category=most_common[0][0] if most_common else None,
    )
