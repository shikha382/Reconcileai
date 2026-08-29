"""Milestone 13, Phase 6: an explicit decision-authority audit. Most of the
named attack types in the M13 brief are ALREADY covered by exhaustive
existing suites -- this file does not duplicate them; it exercises the
remaining gap (direct exception-state tampering) and documents, in one
place, exactly where the rest of the evidence already lives, so the
claim-vs-proof matrix (docs/demo-runbook.md) has one file to point to.

Attack                          | Where it's already proven
---------------------------------------------------------------------------
AI override (fabricated high-   | tests/adversarial/test_ai_misleading_evidence.py
confidence claim)               | ::test_case_04_extremely_high_ai_confidence_does_not_override_contradiction
Policy bypass (unauthorized     | tests/adversarial/test_policy_manipulation.py
actor approval)                 | ::test_unauthorized_actor_cannot_approve_via_the_policy_authorization_layer
Verification bypass (misleading | tests/adversarial/test_ai_misleading_evidence.py (cases 01-05, all 5)
evidence)                       |
Frontend-style malicious request| tests/api/test_security.py
(extra-field smuggling, no      | ::test_unexpected_extra_fields_in_request_body_are_ignored_not_dangerous
mutation endpoints)             | ::test_no_financial_mutation_endpoints_exist / ::test_no_force_resolve_or_approval_bypass_endpoint_exists
Tampered priority               | tests/prioritization/test_decision_invariance.py (all 4 tests)
Tampered explanation /          | tests/explainability/test_provenance_integrity.py (7 adversarial-reference tests)
forged IDs                      |
Tampered exception state        | THIS FILE (new -- see below)
"""
from __future__ import annotations

import pytest

from app.policy.schemas import ExceptionState
from app.policy.state_machine import InvalidStateTransitionError, transition

INVALID_TRANSITIONS = [
    (ExceptionState.EXCEPTION_OPEN, ExceptionState.CLOSED),  # skipping straight to closed
    (ExceptionState.EXCEPTION_OPEN, ExceptionState.AUTO_RESOLVE),  # skipping investigation/policy entirely
    (ExceptionState.HUMAN_REVIEW, ExceptionState.AUTO_RESOLVE),  # a human-review case cannot silently become auto-resolved
    (ExceptionState.CLOSED, ExceptionState.INVESTIGATING),  # terminal state can never reopen
    (ExceptionState.POLICY_EVALUATED, ExceptionState.EXCEPTION_OPEN),  # no going backwards
    (ExceptionState.BLOCKED, ExceptionState.AUTO_RESOLVE),  # a blocked case cannot be forced through
]


@pytest.mark.parametrize("current,target", INVALID_TRANSITIONS)
def test_invalid_exception_state_transitions_are_rejected(current, target):
    with pytest.raises(InvalidStateTransitionError):
        transition(current, target)


def test_valid_transitions_still_work_the_guard_is_not_overly_strict():
    assert transition(ExceptionState.EXCEPTION_OPEN, ExceptionState.INVESTIGATING) == ExceptionState.INVESTIGATING
    assert transition(ExceptionState.POLICY_EVALUATED, ExceptionState.HUMAN_REVIEW) == ExceptionState.HUMAN_REVIEW
    assert transition(ExceptionState.BLOCKED, ExceptionState.INVESTIGATING) == ExceptionState.INVESTIGATING  # explicit re-investigation path


def test_closed_is_a_true_terminal_state_with_zero_allowed_exits():
    from app.policy.state_machine import ALLOWED_TRANSITIONS

    assert ALLOWED_TRANSITIONS[ExceptionState.CLOSED] == set()
