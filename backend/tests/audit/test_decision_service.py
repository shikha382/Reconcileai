"""Integration tests for the M6 unified pipeline (app.services.decision_service):
correlation_id threading, and the self-challenge rule (a contradicted
hypothesis must never reach SAFE_TO_RESOLVE)."""
from app.audit.ledger import AuditLedger
from app.policy.schemas import PolicyDecisionType


def test_every_decision_shares_one_correlation_id_across_all_its_events(full_m6_decisions):
    session = full_m6_decisions["session"]
    ledger = AuditLedger(session)

    # Spot-check a sample of results rather than all 300, for speed --
    # this is a structural invariant, not something that should vary by case.
    sample = list(full_m6_decisions["results"].values())[:25]
    for result in sample:
        events = ledger.events_for_correlation(result.correlation_id)
        assert len(events) > 0
        assert all(e.entity_id == result.exception_id for e in events)
        # EXCEPTION_CREATED must always be the first event of its own correlation group.
        assert events[0].event_type == "EXCEPTION_CREATED"


def test_self_challenge_rule_blocks_auto_resolution_whenever_a_contradiction_exists(full_m6_decisions):
    # The invariant that must hold universally: a contradicted hypothesis
    # NEVER reaches SAFE_TO_RESOLVE. Which specific policy rule fired can
    # vary -- if the root-cause verifier_status was already CONTRADICTED,
    # the BLOCK tier's POLICY-VERIFIER-FAIL-001 fires first and REJECTED
    # wins outright (block tier outranks mandatory-approval); otherwise the
    # self-challenge rule's own POLICY-CONFLICT-001 is what fires.
    results = full_m6_decisions["results"]
    checked_any_contradiction = False
    conflict_rule_fired = False
    for result in results.values():
        if any(r.status == "CONTRADICTED" for r in result.contradiction_records):
            checked_any_contradiction = True
            assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE, (
                f"{result.exception_id} had a contradicted hypothesis but still reached SAFE_TO_RESOLVE"
            )
            if "POLICY-CONFLICT-001" in result.policy_decision.rules_passed:
                conflict_rule_fired = True
    assert checked_any_contradiction, "expected at least one real contradiction across the 300-record dataset"
    assert conflict_rule_fired, "expected the self-challenge rule (POLICY-CONFLICT-001) to fire at least once"


def test_policy_evaluated_audit_event_matches_the_returned_policy_decision(full_m6_decisions):
    session = full_m6_decisions["session"]
    ledger = AuditLedger(session)
    from shared.money import loads

    sample = list(full_m6_decisions["results"].values())[:10]
    for result in sample:
        events = ledger.events_for_correlation(result.correlation_id)
        policy_events = [e for e in events if e.event_type == "POLICY_EVALUATED"]
        assert len(policy_events) == 1
        payload = loads(policy_events[0].payload_json)
        assert payload["decision"] == result.policy_decision.decision.value


def test_review_requested_event_exists_only_when_approval_was_required(full_m6_decisions):
    session = full_m6_decisions["session"]
    ledger = AuditLedger(session)

    sample = list(full_m6_decisions["results"].values())[:30]
    for result in sample:
        events = ledger.events_for_correlation(result.correlation_id)
        review_events = [e for e in events if e.event_type == "REVIEW_REQUESTED"]
        if result.policy_decision.required_approval:
            assert len(review_events) == 1
            assert result.review is not None
        else:
            assert len(review_events) == 0
