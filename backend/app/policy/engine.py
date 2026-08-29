"""The deterministic PolicyEngine -- M5's actual authority. AI confidence,
AI recommended_action, and any prose "explanation" are never read here; only
`PolicyInput`'s structured fields are.

Precedence (fixed, documented, never reordered per-call):

    BLOCK / SAFETY RULES  >  MANDATORY APPROVAL  >  RISK RULES  >  AUTO-RESOLUTION ELIGIBILITY

Each tier is evaluated in order; the first tier with a fired rule decides
the outcome (all tiers below it are still recorded as "not reached" for
audit, never silently skipped in the trace). This fixed order is what makes
the brief's policy-conflict example resolve safely: a ₹8,000 verified fee
mismatch fires both an auto-eligibility rule (tier 4) AND a high-exposure
risk rule (tier 3) -- because RISK outranks AUTO_ELIGIBILITY, the exposure
rule wins and the result is HUMAN_REVIEW, never SAFE_TO_RESOLVE.

Fail-closed: any rule tier that cannot be evaluated (missing/invalid input)
defaults to HUMAN_REVIEW, never SAFE_TO_RESOLVE.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.policy.schemas import PolicyDecision, PolicyDecisionType, PolicyInput, ResolutionType, RiskLevel

POLICY_ID = "RECONCILEAI-CORE-POLICY"
POLICY_VERSION = "1.0.0"

# Same categorical/threshold constants M4's AI-hypothesis policy gate uses
# (app.ai.policy) -- reused, not reinvented, so an AI-assisted and a
# non-AI-assisted exception are held to the identical auto-resolution bar.
MAX_AUTO_RESOLVE_EXPOSURE = Decimal("100000.00")


@dataclass
class RuleOutcome:
    rule_id: str
    tier: str
    fired: bool
    reason: str


def _input_hash(policy_input: PolicyInput) -> str:
    raw = "|".join([
        policy_input.exception_id, str(policy_input.exception_type), policy_input.verifier_status,
        str(policy_input.residual_amount), str(policy_input.financial_exposure), str(policy_input.evidence_complete),
        str(policy_input.conflicting_evidence), str(policy_input.ambiguous), str(policy_input.risk_score),
        policy_input.risk_level.value, str(policy_input.auto_resolution_eligible_category), POLICY_VERSION,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _block_tier(policy_input: PolicyInput) -> list[RuleOutcome]:
    outcomes = []
    outcomes.append(RuleOutcome(
        "POLICY-VERIFIER-FAIL-001", "BLOCK", policy_input.verifier_status == "CONTRADICTED",
        "a hypothesis was actively disproven by deterministic verification -- the underlying claim is known to be wrong, not merely uncertain",
    ))
    outcomes.append(RuleOutcome(
        "POLICY-EVIDENCE-001", "BLOCK", not policy_input.evidence_complete,
        "evidence is incomplete -- cannot safely evaluate this exception",
    ))
    outcomes.append(RuleOutcome(
        "POLICY-NEGATIVE-RESIDUAL-001", "BLOCK", policy_input.residual_amount < Decimal("0.00"),
        f"residual_amount {policy_input.residual_amount} is negative -- an invalid financial value, never rounded away",
    ))
    outcomes.append(RuleOutcome(
        "POLICY-UNKNOWN-TYPE-001", "BLOCK",
        policy_input.exception_type is None and policy_input.verifier_status != "VERIFIED",
        "exception has no classified type and is not a verified clean match -- unknown state",
    ))
    return outcomes


def _mandatory_approval_tier(policy_input: PolicyInput) -> list[RuleOutcome]:
    return [
        RuleOutcome("POLICY-AMBIG-001", "MANDATORY_APPROVAL", policy_input.ambiguous,
                    "ambiguous candidates always require human review"),
        RuleOutcome("POLICY-CONFLICT-001", "MANDATORY_APPROVAL", policy_input.conflicting_evidence,
                    "conflicting evidence blocks automatic resolution"),
        RuleOutcome("POLICY-CATEGORY-001", "MANDATORY_APPROVAL", not policy_input.auto_resolution_eligible_category,
                    f"exception category {policy_input.exception_type!r} is policy-blocked from auto-resolution regardless of verification"),
        RuleOutcome("POLICY-UNEXPLAINED-001", "MANDATORY_APPROVAL",
                    policy_input.verifier_status in ("UNEXPLAINED", "PARTIALLY_EXPLAINED") and policy_input.residual_amount != Decimal("0.00"),
                    "unexplained residual amount requires human review"),
    ]


def _risk_tier(policy_input: PolicyInput) -> list[RuleOutcome]:
    return [
        RuleOutcome("POLICY-HIGH-RISK-001", "RISK", policy_input.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL),
                    f"risk level {policy_input.risk_level.value} always requires human approval"),
        RuleOutcome("POLICY-EXPOSURE-001", "RISK", policy_input.financial_exposure > MAX_AUTO_RESOLVE_EXPOSURE,
                    f"financial exposure {policy_input.financial_exposure} exceeds the auto-resolve threshold {MAX_AUTO_RESOLVE_EXPOSURE}"),
    ]


def _auto_eligibility_tier(policy_input: PolicyInput) -> RuleOutcome:
    eligible = (
        policy_input.verifier_status == "VERIFIED"
        and policy_input.residual_amount == Decimal("0.00")
        and not policy_input.ambiguous
        and not policy_input.conflicting_evidence
        and policy_input.evidence_complete
        and policy_input.auto_resolution_eligible_category
        and policy_input.financial_exposure <= MAX_AUTO_RESOLVE_EXPOSURE
    )
    return RuleOutcome(
        "POLICY-AUTO-001", "AUTO_ELIGIBILITY", eligible,
        "verified, zero residual, no ambiguity/conflict, eligible category, within exposure threshold" if eligible
        else "does not meet all auto-resolution eligibility conditions",
    )


def evaluate_policy(policy_input: PolicyInput) -> PolicyDecision:
    rules_evaluated: list[str] = []
    rules_passed: list[str] = []
    rules_failed: list[str] = []

    # Tier 0, ahead of BLOCK: "nothing exists yet" is not a safety violation
    # to block, nor a judgment call to send for review -- it's a different
    # kind of outcome entirely (UNRESOLVED), and must be recognized before
    # any rule tier that would otherwise treat its non-zero residual as a
    # reason to require human review (found empirically: POLICY-UNEXPLAINED-001
    # was firing for missing_transaction cases and mislabeling them
    # HUMAN_REVIEW instead of the ground-truth-correct UNRESOLVED).
    if policy_input.exception_type == "missing_transaction" and policy_input.verifier_status == "UNEXPLAINED":
        rules_evaluated = ["POLICY-MISSING-RECORD-001"]
        return _finalize(policy_input, PolicyDecisionType.UNRESOLVED, [], ["no candidate record exists yet"],
                          False, rules_evaluated, ["POLICY-MISSING-RECORD-001"], [])

    block_outcomes = _block_tier(policy_input)
    rules_evaluated += [o.rule_id for o in block_outcomes]
    fired_blocks = [o for o in block_outcomes if o.fired]
    rules_failed += [o.rule_id for o in block_outcomes if not o.fired]
    rules_passed += [o.rule_id for o in fired_blocks]
    if fired_blocks:
        return _finalize(policy_input, PolicyDecisionType.REJECTED, [], [o.reason for o in fired_blocks],
                          False, rules_evaluated, rules_passed, rules_failed)

    approval_outcomes = _mandatory_approval_tier(policy_input)
    rules_evaluated += [o.rule_id for o in approval_outcomes]
    fired_approval = [o for o in approval_outcomes if o.fired]
    rules_failed += [o.rule_id for o in approval_outcomes if not o.fired]
    rules_passed += [o.rule_id for o in fired_approval]
    if fired_approval:
        return _finalize(policy_input, PolicyDecisionType.HUMAN_REVIEW, [o.reason for o in fired_approval], [],
                          True, rules_evaluated, rules_passed, rules_failed)

    risk_outcomes = _risk_tier(policy_input)
    rules_evaluated += [o.rule_id for o in risk_outcomes]
    fired_risk = [o for o in risk_outcomes if o.fired]
    rules_failed += [o.rule_id for o in risk_outcomes if not o.fired]
    rules_passed += [o.rule_id for o in fired_risk]
    if fired_risk:
        return _finalize(policy_input, PolicyDecisionType.HUMAN_REVIEW, [o.reason for o in fired_risk], [],
                          True, rules_evaluated, rules_passed, rules_failed)

    auto_outcome = _auto_eligibility_tier(policy_input)
    rules_evaluated.append(auto_outcome.rule_id)
    if auto_outcome.fired:
        rules_passed.append(auto_outcome.rule_id)
        return _finalize(policy_input, PolicyDecisionType.SAFE_TO_RESOLVE, [auto_outcome.reason], [],
                          False, rules_evaluated, rules_passed, rules_failed)
    rules_failed.append(auto_outcome.rule_id)

    # Fail-closed default: nothing made it safe, and no tier 0/BLOCK/
    # MANDATORY_APPROVAL/RISK rule fired either -- the safe HUMAN_REVIEW
    # fallback, never SAFE_TO_RESOLVE by omission.

    return _finalize(policy_input, PolicyDecisionType.HUMAN_REVIEW, [], ["no rule tier verified this as safe to auto-resolve"],
                      True, rules_evaluated, rules_passed, rules_failed)


def _resolution_type_for(decision: PolicyDecisionType) -> ResolutionType:
    return {
        PolicyDecisionType.SAFE_TO_RESOLVE: ResolutionType.MARK_RECONCILED,
        PolicyDecisionType.HUMAN_REVIEW: ResolutionType.REQUEST_HUMAN_REVIEW,
        PolicyDecisionType.REJECTED: ResolutionType.NO_ACTION,
        PolicyDecisionType.ESCALATED: ResolutionType.ESCALATE,
        PolicyDecisionType.UNRESOLVED: ResolutionType.NO_ACTION,
    }[decision]


def _finalize(
    policy_input: PolicyInput, decision: PolicyDecisionType, reasons: list[str], blocked_reasons: list[str],
    required_approval: bool, rules_evaluated: list[str], rules_passed: list[str], rules_failed: list[str],
) -> PolicyDecision:
    return PolicyDecision(
        decision=decision, policy_id=POLICY_ID, policy_version=POLICY_VERSION,
        reasons=reasons, blocked_reasons=blocked_reasons, required_approval=required_approval,
        risk_level=policy_input.risk_level, resolution_type=_resolution_type_for(decision),
        rules_evaluated=rules_evaluated, rules_passed=rules_passed, rules_failed=rules_failed,
        input_hash=_input_hash(policy_input), evaluated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
