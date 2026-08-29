"""Policy dry-run / what-if evaluation -- "would this be auto-resolvable
under policy version X?" without affecting any real decision. Useful for
testing a proposed policy change before rolling it out.

Only the auto-resolve exposure threshold is versioned here (the minimum
needed to make the brief's own worked example -- "v1: Rs 5,000 verified fee
mismatch -> SAFE; v2: same input -> HUMAN_REVIEW" -- concretely
demonstrable); the rest of app.policy.engine's rule set is shared across
versions. Extending this to a fuller multi-version rule registry is
straightforward if a real policy change ever needs it, but isn't built
speculatively here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.policy import engine as _engine
from app.policy.schemas import PolicyDecision, PolicyInput

POLICY_VERSIONS: dict[str, Decimal] = {
    "1.0.0": Decimal("100000.00"),  # current production policy (app.policy.engine.MAX_AUTO_RESOLVE_EXPOSURE)
    "2.0.0-stricter-draft": Decimal("3000.00"),  # illustrative draft: a much tighter auto-resolve ceiling
}


@dataclass
class SimulationResult:
    policy_version: str
    decision: PolicyDecision
    would_change_from_current: bool

    def to_dict(self) -> dict:
        return {"policy_version": self.policy_version, "decision": self.decision.to_dict(), "would_change_from_current": self.would_change_from_current}


def simulate(policy_input: PolicyInput, version: str) -> SimulationResult:
    if version not in POLICY_VERSIONS:
        raise ValueError(f"unknown policy version {version!r}; known versions: {sorted(POLICY_VERSIONS)}")

    original_threshold = _engine.MAX_AUTO_RESOLVE_EXPOSURE
    original_version = _engine.POLICY_VERSION
    try:
        _engine.MAX_AUTO_RESOLVE_EXPOSURE = POLICY_VERSIONS[version]
        _engine.POLICY_VERSION = version
        decision = _engine.evaluate_policy(policy_input)
    finally:
        _engine.MAX_AUTO_RESOLVE_EXPOSURE = original_threshold
        _engine.POLICY_VERSION = original_version

    current_decision = _engine.evaluate_policy(policy_input)
    return SimulationResult(policy_version=version, decision=decision, would_change_from_current=(decision.decision != current_decision.decision))
