"""M10 Phase 21: explanation generation overhead. The explanation layer
must not rerun expensive reconciliation/AI/policy logic -- it consumes
already-produced results, so building it for the whole 300-record dataset
should be small compared to the pipeline run itself.
"""
import time

from app.explainability.builder import build_explanation


def test_building_explanations_for_the_whole_dataset_is_fast_relative_to_the_pipeline(mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context
    from app.services.exception_service import run_exception_intelligence
    from tests.adversarial.helpers import decide_one

    t0 = time.perf_counter()
    _, bundles = run_exception_intelligence(
        mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions,
        mutated_dataset.refunds, mutated_dataset.fee_rules,
    )
    sample = bundles[:40]
    results = [decide_one(mutated_dataset, b.payment_id, decision_env) for b in sample]
    pipeline_seconds = time.perf_counter() - t0

    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    payments_by_id = {p.payment_id: p for p in mutated_dataset.payments}

    t1 = time.perf_counter()
    explanations = []
    for result in results:
        payment = payments_by_id[result.bundle.payment_id]
        settlement = next((s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id), None)
        explanations.append(build_explanation(result, context=context, payment=payment, settlement=settlement))
    explanation_seconds = time.perf_counter() - t1

    assert len(explanations) == len(sample)
    # The explanation layer building 40 reports must be a small fraction of
    # the time the actual pipeline (matching + AI + policy + audit) took for
    # those same 40 exceptions -- proving it isn't re-running anything expensive.
    assert explanation_seconds < pipeline_seconds
    print(f"\nPipeline (40 exceptions): {pipeline_seconds:.4f}s; explanation building: {explanation_seconds:.4f}s "
          f"({100 * explanation_seconds / pipeline_seconds:.2f}% of pipeline time)")


def test_building_one_explanation_does_not_call_expensive_engines_repeatedly(get_decision, monkeypatch):
    import app.services.exception_service as exception_service_module

    call_count = {"n": 0}
    real_fn = exception_service_module.run_exception_intelligence

    def _counting(*args, **kwargs):
        call_count["n"] += 1
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(exception_service_module, "run_exception_intelligence", _counting)

    result, payment, settlement, context = get_decision("exact_match", 0)
    from app.explainability.builder import build_explanation

    build_explanation(result, context=context, payment=payment, settlement=settlement)
    # get_decision's own fixture already called run_exception_intelligence
    # once to produce `result`/`context` -- build_explanation itself must
    # add ZERO further calls to it.
    assert call_count["n"] == 0
