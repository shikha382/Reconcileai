"""Explicit exception-lifecycle state transitions. No arbitrary state jumps
-- an invalid transition raises, the state is left unchanged."""
from __future__ import annotations

from app.policy.schemas import ExceptionState

ALLOWED_TRANSITIONS: dict[ExceptionState, set[ExceptionState]] = {
    ExceptionState.EXCEPTION_OPEN: {ExceptionState.INVESTIGATING},
    ExceptionState.INVESTIGATING: {ExceptionState.PROPOSAL_READY, ExceptionState.BLOCKED},
    ExceptionState.PROPOSAL_READY: {ExceptionState.POLICY_EVALUATED},
    ExceptionState.POLICY_EVALUATED: {ExceptionState.AUTO_RESOLVE, ExceptionState.HUMAN_REVIEW, ExceptionState.BLOCKED},
    ExceptionState.AUTO_RESOLVE: {ExceptionState.CLOSED},
    ExceptionState.HUMAN_REVIEW: {ExceptionState.APPROVED, ExceptionState.REJECTED},
    ExceptionState.APPROVED: {ExceptionState.CLOSED},
    ExceptionState.REJECTED: {ExceptionState.CLOSED},
    ExceptionState.BLOCKED: {ExceptionState.CLOSED, ExceptionState.INVESTIGATING},  # a blocked case can be re-investigated
    ExceptionState.CLOSED: set(),  # terminal
}


class InvalidStateTransitionError(Exception):
    pass


def transition(current: ExceptionState, target: ExceptionState) -> ExceptionState:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(f"cannot transition from {current.value} to {target.value}")
    return target
