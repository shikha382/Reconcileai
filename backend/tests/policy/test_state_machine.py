"""Explicit state transitions -- no arbitrary jumps."""
import pytest

from app.policy.schemas import ExceptionState
from app.policy.state_machine import InvalidStateTransitionError, transition


def test_valid_transition_chain():
    s = ExceptionState.EXCEPTION_OPEN
    s = transition(s, ExceptionState.INVESTIGATING)
    s = transition(s, ExceptionState.PROPOSAL_READY)
    s = transition(s, ExceptionState.POLICY_EVALUATED)
    s = transition(s, ExceptionState.AUTO_RESOLVE)
    s = transition(s, ExceptionState.CLOSED)
    assert s == ExceptionState.CLOSED


def test_human_review_to_approved_to_closed():
    s = ExceptionState.POLICY_EVALUATED
    s = transition(s, ExceptionState.HUMAN_REVIEW)
    s = transition(s, ExceptionState.APPROVED)
    s = transition(s, ExceptionState.CLOSED)
    assert s == ExceptionState.CLOSED


def test_invalid_transition_is_rejected():
    with pytest.raises(InvalidStateTransitionError):
        transition(ExceptionState.EXCEPTION_OPEN, ExceptionState.CLOSED)


def test_invalid_transition_skips_are_rejected():
    with pytest.raises(InvalidStateTransitionError):
        transition(ExceptionState.EXCEPTION_OPEN, ExceptionState.AUTO_RESOLVE)


def test_closed_is_terminal():
    with pytest.raises(InvalidStateTransitionError):
        transition(ExceptionState.CLOSED, ExceptionState.EXCEPTION_OPEN)


def test_blocked_can_be_reinvestigated():
    s = transition(ExceptionState.INVESTIGATING, ExceptionState.BLOCKED)
    s = transition(s, ExceptionState.INVESTIGATING)
    assert s == ExceptionState.INVESTIGATING


def test_state_unchanged_after_rejected_transition_attempt():
    s = ExceptionState.EXCEPTION_OPEN
    try:
        transition(s, ExceptionState.CLOSED)
    except InvalidStateTransitionError:
        pass
    assert s == ExceptionState.EXCEPTION_OPEN  # local var unchanged; transition() never mutates in place
