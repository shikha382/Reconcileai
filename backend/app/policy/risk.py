"""SLA/aging classification and deterministic prioritization -- built on
top of M3's existing `app.engines.risk.scoring` (risk_score, confidence
deficit, aging factor), never a second risk formula. This module adds the
M5-specific framing: risk LEVEL buckets, SLA status, and a priority queue
ranking that combines both, with reasons, so risk always prioritizes human
attention rather than silently gating decisions on its own (see
app.policy.engine -- risk is a tier in policy precedence, not a bypass).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from app.db.models import Payment
from app.engines.risk.scoring import compute_risk_score
from app.engines.root_cause.result import RootCauseResult
from app.policy.schemas import RiskLevel, SLAStatus

# Thresholds are configurable constants, not scattered magic numbers --
# tuned qualitatively against the real 300-record dataset's exposure range
# (see docs/policy-engine.md).
RISK_SCORE_LOW_MAX = Decimal("500.00")
RISK_SCORE_MEDIUM_MAX = Decimal("5000.00")
RISK_SCORE_HIGH_MAX = Decimal("50000.00")
# above HIGH_MAX -> CRITICAL

SLA_DUE_DAYS = 7  # an exception is "due" for review within this many days of its payment date
SLA_AT_RISK_FRACTION = Decimal("0.70")  # >=70% of the SLA window elapsed, not yet breached


def risk_level_for_score(risk_score: Decimal) -> RiskLevel:
    if risk_score <= RISK_SCORE_LOW_MAX:
        return RiskLevel.LOW
    if risk_score <= RISK_SCORE_MEDIUM_MAX:
        return RiskLevel.MEDIUM
    if risk_score <= RISK_SCORE_HIGH_MAX:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


@dataclass
class SLAAssessment:
    created_at: datetime
    due_at: datetime
    age_seconds: int
    age_days: int
    sla_status: SLAStatus


def assess_sla(payment: Payment, reference_now: datetime, due_days: int = SLA_DUE_DAYS) -> SLAAssessment:
    created_at = payment.captured_at
    due_at = created_at + timedelta(days=due_days)
    age = reference_now - created_at
    age_seconds = max(int(age.total_seconds()), 0)
    age_days = age_seconds // 86400

    window_seconds = due_days * 86400
    if reference_now > due_at:
        status = SLAStatus.BREACHED
    elif window_seconds > 0 and Decimal(age_seconds) / Decimal(window_seconds) >= SLA_AT_RISK_FRACTION:
        status = SLAStatus.AT_RISK
    else:
        status = SLAStatus.WITHIN_SLA

    return SLAAssessment(created_at=created_at, due_at=due_at, age_seconds=age_seconds, age_days=age_days, sla_status=status)


@dataclass
class PriorityAssessment:
    priority_score: Decimal
    priority_level: str  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    priority_reasons: list[str] = field(default_factory=list)


def assess_priority(payment: Payment, root_cause: RootCauseResult, reference_now: datetime) -> PriorityAssessment:
    """Deterministic prioritization -- never a plain amount sort. Combines
    M3's risk_score (amount x confidence-deficit x aging, already computed)
    with the SLA status, since a large-but-well-understood exception is not
    automatically more urgent than a smaller one that's about to breach."""
    risk_score = compute_risk_score(payment, root_cause, reference_now)
    sla = assess_sla(payment, reference_now)
    level = risk_level_for_score(risk_score)

    reasons = []
    if level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
        reasons.append(f"financial exposure risk_score={risk_score} ({level.value})")
    if sla.sla_status == SLAStatus.BREACHED:
        reasons.append(f"SLA breached ({sla.age_days} days old)")
    elif sla.sla_status == SLAStatus.AT_RISK:
        reasons.append(f"SLA at risk ({sla.age_days} days old)")
    if not reasons:
        reasons.append(f"low exposure ({risk_score}), within SLA")

    if level == RiskLevel.CRITICAL or sla.sla_status == SLAStatus.BREACHED:
        priority_level = "CRITICAL" if (level == RiskLevel.CRITICAL and sla.sla_status == SLAStatus.BREACHED) else "HIGH"
    elif level == RiskLevel.HIGH or sla.sla_status == SLAStatus.AT_RISK:
        priority_level = "HIGH" if level == RiskLevel.HIGH else "MEDIUM"
    elif level == RiskLevel.MEDIUM:
        priority_level = "MEDIUM"
    else:
        priority_level = "LOW"

    # Priority score for ranking: risk_score weighted by an SLA multiplier,
    # so a near-breach case can outrank a similarly-risky-but-fresh one.
    sla_multiplier = {SLAStatus.BREACHED: Decimal("2.0"), SLAStatus.AT_RISK: Decimal("1.3"), SLAStatus.WITHIN_SLA: Decimal("1.0")}[sla.sla_status]
    priority_score = (risk_score * sla_multiplier).quantize(Decimal("0.01"))

    return PriorityAssessment(priority_score=priority_score, priority_level=priority_level, priority_reasons=reasons)
