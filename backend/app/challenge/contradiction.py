"""The structured CHALLENGE / CONTRADICTION mechanism -- M6's one
technically distinctive feature. NOT free-form chain-of-thought: every
field here is a structured evidence classification, built directly from
M4's already-computed `HypothesisOutcome` (hypothesis + deterministic
verifier result + policy decision) -- nothing here re-derives financial
logic or invents a second verification path. This module answers "what
evidence could prove this hypothesis wrong, and did it?", reusing M3's
evidence/constraint concepts rather than duplicating them.

Bounded and deterministic (Phase 12): this is a straight, one-pass
classification of an already-completed verification result. There is no
loop, no recursive self-reflection, and no second LLM call here -- an LLM
(if used) only ever proposed the ORIGINAL hypothesis (M4); this module
never asks a model anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.policy import HypothesisOutcome
from app.ai.schemas import RecommendedAction

SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class ContradictionRecord:
    hypothesis_id: str
    hypothesis_type: str
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    status: str = INSUFFICIENT_EVIDENCE
    expected_value: str | None = None
    observed_value: str | None = None
    residual: str | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id, "hypothesis_type": self.hypothesis_type,
            "supporting_evidence": self.supporting_evidence, "contradicting_evidence": self.contradicting_evidence,
            "missing_evidence": self.missing_evidence, "status": self.status,
            "expected_value": self.expected_value, "observed_value": self.observed_value,
            "residual": self.residual, "reason": self.reason,
        }


def build_contradiction_record(outcome: HypothesisOutcome, grounding_violations: list[str] | None = None) -> ContradictionRecord:
    hypothesis = outcome.hypothesis
    verifier_result = outcome.verifier_result

    if grounding_violations:
        return ContradictionRecord(
            hypothesis_id=hypothesis.hypothesis_id, hypothesis_type=hypothesis.hypothesis_type.value,
            missing_evidence=list(grounding_violations), status=INSUFFICIENT_EVIDENCE,
            reason="hypothesis cites evidence that was never actually retrieved -- cannot evaluate a claim grounded in nothing",
        )

    evidence_ids = list(verifier_result.evidence_ids) or list(hypothesis.evidence_ids)

    if verifier_result.passed:
        return ContradictionRecord(
            hypothesis_id=hypothesis.hypothesis_id, hypothesis_type=hypothesis.hypothesis_type.value,
            supporting_evidence=evidence_ids, status=SUPPORTED,
            expected_value=verifier_result.expected_value, observed_value=verifier_result.observed_value,
            residual=verifier_result.residual, reason=verifier_result.reason,
        )

    return ContradictionRecord(
        hypothesis_id=hypothesis.hypothesis_id, hypothesis_type=hypothesis.hypothesis_type.value,
        contradicting_evidence=evidence_ids, status=CONTRADICTED,
        expected_value=verifier_result.expected_value, observed_value=verifier_result.observed_value,
        residual=verifier_result.residual, reason=verifier_result.reason,
    )


def has_unresolved_contradiction(records: list[ContradictionRecord]) -> bool:
    """The self-challenge rule (Phase 11): true if ANY tested hypothesis for
    this exception was CONTRADICTED. This does not itself decide anything --
    it is a signal the policy engine (app.policy.engine) consumes via
    PolicyInput.conflicting_evidence, exactly like any other structured
    evidence. The challenge layer never overrides the policy engine."""
    return any(r.status == CONTRADICTED for r in records)
