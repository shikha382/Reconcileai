"""M10 Phase 16: hallucination prevention. The explanation layer is built
entirely from structured fields (never free-form LLM prose), so these
tests confirm the four brief-numbered scenarios directly: an explanation
must never claim something the underlying structured facts don't support.
"""
from app.explainability.builder import build_explanation
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype


def test_no_refund_exists_explanation_never_blames_a_refund(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert explanation.source_records.refund_ids == []
    text = explanation.human_readable.lower()
    assert "refund caused" not in text
    assert "refund explains the difference." not in text  # only ever appears quoted alongside its rejection, if at all


def test_no_fee_rule_exists_explanation_never_claims_fee_explains_it(get_decision, mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context

    order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0, not_adversarial=True)
    payment = find_payment_by_order(mutated_dataset, order_id)
    mutated_dataset.fee_rules = [f for f in mutated_dataset.fee_rules if f.method != payment.method]
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    # No fee_verification trace can exist -- there is no rule to verify against.
    assert not any(t.label == "fee_verification" and t.verification_result == "PASSED" for t in explanation.calculation_evidence)
    assert explanation.decision != "SAFE_TO_RESOLVE"
    text = explanation.human_readable.lower()
    assert "card fee explains the difference" not in text


def test_ai_unavailable_explanation_never_claims_ai_determined_anything(mutated_dataset, ground_truth, tmp_path):
    """A real, total AI provider outage (ProviderError on every call) run
    through the actual decision pipeline -- not a fabricated report."""
    from app.ai.provider import ProviderError
    from app.audit.ledger import AuditLedger
    from app.db.session import init_db, make_engine, make_session_factory
    from app.engines.reconciliation.candidate_generation import build_context
    from app.policy.approval import ApprovalWorkflowStore
    from tests.adversarial.helpers import DecisionEnvironment

    class _AlwaysFailingProvider:
        def decide_next_action(self, state):
            raise ProviderError("simulated total outage")

    order_id = pick_by_archetype(ground_truth, "unexplained_difference", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next((s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id), None)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)

    engine = make_engine(tmp_path / "halluc.db")
    init_db(engine)
    session = make_session_factory(engine)()
    env = DecisionEnvironment(ledger=AuditLedger(session), approval_store=ApprovalWorkflowStore(), provider=_AlwaysFailingProvider(), session=session)
    result = decide_one(mutated_dataset, payment.payment_id, env)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    session.close()
    engine.dispose()

    assert explanation.ai_investigation_status == "UNAVAILABLE_OR_DEGRADED"
    assert explanation.ai_hypotheses == []  # never fabricated
    assert explanation.decision != "SAFE_TO_RESOLVE"
    text = explanation.human_readable.lower()
    assert "ai determined" not in text
    assert "unavailable" in text or "degraded" in text


def test_policy_denied_automation_explanation_never_says_automatically_resolved(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert explanation.decision != "SAFE_TO_RESOLVE"
    text = explanation.human_readable.lower()
    assert "automatically resolved" not in text
    assert "auto resolved" not in text
    assert "auto-resolved" not in text


def test_ai_hypothesis_claims_are_never_rendered_as_verified_fact(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    text = explanation.human_readable
    for h in explanation.ai_hypotheses:
        if h.final_disposition != "ACCEPTED":
            # A rejected/not-accepted hypothesis's own claim text may still
            # appear (quoted, as what the AI proposed), but must always be
            # immediately paired with its verification result on the same line.
            assert f'"{h.claim}"' in text
            line = next(l for l in text.splitlines() if h.claim in l)
            assert "verification" in line.lower()
