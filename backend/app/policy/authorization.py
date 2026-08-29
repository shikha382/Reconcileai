"""Minimal authorization layer -- not a full IAM system. Actor TYPE alone
never implies permission: an actor's capability set is checked explicitly,
every time. AI never has APPROVE or CHANGE_POLICY, by construction."""
from __future__ import annotations

from app.policy.schemas import Actor, ActorType, Capability

ACTOR_CAPABILITIES: dict[ActorType, set[Capability]] = {
    ActorType.AI: {Capability.VIEW_EXCEPTION, Capability.INVESTIGATE, Capability.PROPOSE_RESOLUTION, Capability.VIEW_AUDIT},
    ActorType.HUMAN: {
        Capability.VIEW_EXCEPTION, Capability.INVESTIGATE, Capability.PROPOSE_RESOLUTION,
        Capability.APPROVE, Capability.REJECT, Capability.ESCALATE,
        Capability.VIEW_AUDIT, Capability.VERIFY_AUDIT,
        # M8: the default identity for an authenticated API caller (see
        # app.api.dependencies.get_actor) is ActorType.HUMAN -- a person or
        # service operating the controller through its read/trigger API, not
        # a second actor type parallel to HUMAN.
        Capability.VIEW_RUN, Capability.VIEW_PROVENANCE, Capability.START_RECONCILIATION,
    },
    ActorType.SYSTEM: {
        Capability.VIEW_EXCEPTION, Capability.INVESTIGATE, Capability.PROPOSE_RESOLUTION, Capability.ESCALATE,
        Capability.VIEW_AUDIT, Capability.VERIFY_AUDIT, Capability.APPEND_AUDIT,
        Capability.VIEW_RUN, Capability.VIEW_PROVENANCE, Capability.START_RECONCILIATION,
    },
    ActorType.POLICY_ENGINE: {Capability.VIEW_EXCEPTION, Capability.VIEW_AUDIT},
    ActorType.VERIFIER: {Capability.VIEW_EXCEPTION, Capability.VIEW_AUDIT, Capability.APPEND_AUDIT},
}
# No actor type has CHANGE_POLICY in this MVP -- policy changes are a
# deployment/config-review action, not something any runtime actor does.
# Only SYSTEM and VERIFIER can APPEND_AUDIT -- AI and HUMAN actors can view
# and (HUMAN can) verify the ledger, but never write to it directly; every
# real append in this codebase goes through app.services.decision_service's
# own SYSTEM-actor calls to AuditLedger.append.


class AuthorizationError(Exception):
    pass


def is_authorized(actor: Actor, capability: Capability) -> bool:
    return capability in ACTOR_CAPABILITIES.get(actor.actor_type, set())


def require_authorization(actor: Actor, capability: Capability) -> None:
    if not is_authorized(actor, capability):
        raise AuthorizationError(f"actor {actor.actor_type.value}:{actor.actor_id} lacks capability {capability.value}")
