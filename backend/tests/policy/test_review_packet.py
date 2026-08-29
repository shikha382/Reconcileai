"""The structured review packet a future UI renders without recomputing
business logic."""
from app.policy.review_packet import build_review_packet
from app.policy.risk import assess_priority, assess_sla


def test_review_packet_assembles_every_required_section(full_m5_resolution):
    d = full_m5_resolution
    payments_by_id = {p.payment_id: p for p in d["payments"]}

    # Pick a case that actually requires review.
    order_id, r = next((oid, r) for oid, r in d["results"].items() if r["review"] is not None)
    bundle = r["bundle"]
    payment = payments_by_id[bundle.payment_id]
    priority = assess_priority(payment, bundle.root_cause, d["reference_now"])
    sla = assess_sla(payment, d["reference_now"])

    packet = build_review_packet(bundle, r["policy_decision"], r["proposal"], priority, sla)
    packet_dict = packet.to_dict()

    for key in ("exception", "financial_summary", "evidence", "negative_evidence", "hypotheses", "policy", "risk", "proposal"):
        assert key in packet_dict

    assert packet_dict["exception"]["exception_id"] == bundle.exception_id
    assert packet_dict["policy"]["decision"] == r["policy_decision"].decision.value
    assert packet_dict["proposal"]["proposal_id"] == r["proposal"].proposal_id
