"""M5 schema closedness -- no dangerous generic resolution types, no
free-text-only decisions."""
from app.policy.schemas import ReasonCode, ResolutionType


def test_resolution_type_has_no_dangerous_generic_action():
    values = {r.value for r in ResolutionType}
    assert "EXECUTE_ARBITRARY_UPDATE" not in values
    assert values == {"MARK_RECONCILED", "LINK_RECORDS", "CLASSIFY_EXCEPTION", "REQUEST_HUMAN_REVIEW", "ESCALATE", "NO_ACTION"}


def test_reason_code_is_a_closed_enum_not_free_text():
    values = {r.value for r in ReasonCode}
    assert values == {
        "VERIFIED_EVIDENCE", "FINANCIAL_RISK", "AMBIGUOUS_MATCH", "EVIDENCE_INSUFFICIENT",
        "POLICY_BLOCK", "INCORRECT_PROPOSAL", "DUPLICATE", "OTHER",
    }
