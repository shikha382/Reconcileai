"""Canonical enums shared by the backend engines and the synthetic data generator.

Single source of truth so the exception taxonomy can never drift between what the
generator labels a case and what the (future) matching/exception/policy engines expect.
See docs/data-model.md for the authoritative field-level design this mirrors.
"""
from enum import Enum


class ExceptionCategory(str, Enum):
    MISSING_TRANSACTION = "missing_transaction"
    DUPLICATE = "duplicate"
    PARTIAL_SETTLEMENT = "partial_settlement"
    OVER_SETTLEMENT = "over_settlement"
    UNDER_SETTLEMENT = "under_settlement"
    FEE_MISMATCH = "fee_mismatch"
    REFUND_MISMATCH = "refund_mismatch"
    TIMING_MISMATCH = "timing_mismatch"
    REFERENCE_MISMATCH = "reference_mismatch"
    SPLIT_SETTLEMENT = "split_settlement"
    AGGREGATED_SETTLEMENT = "aggregated_settlement"
    REVERSED_TRANSACTION = "reversed_transaction"
    AMBIGUOUS_MATCH = "ambiguous_match"
    UNEXPLAINED_DIFFERENCE = "unexplained_difference"


class RecordArchetype(str, Enum):
    """The full set of case archetypes the synthetic generator produces.
    Equal to ExceptionCategory plus EXACT_MATCH, which is deliberately kept
    out of ExceptionCategory since a clean match is not a kind of exception."""
    EXACT_MATCH = "exact_match"
    MISSING_TRANSACTION = "missing_transaction"
    DUPLICATE = "duplicate"
    PARTIAL_SETTLEMENT = "partial_settlement"
    OVER_SETTLEMENT = "over_settlement"
    UNDER_SETTLEMENT = "under_settlement"
    FEE_MISMATCH = "fee_mismatch"
    REFUND_MISMATCH = "refund_mismatch"
    TIMING_MISMATCH = "timing_mismatch"
    REFERENCE_MISMATCH = "reference_mismatch"
    SPLIT_SETTLEMENT = "split_settlement"
    AGGREGATED_SETTLEMENT = "aggregated_settlement"
    REVERSED_TRANSACTION = "reversed_transaction"
    AMBIGUOUS_MATCH = "ambiguous_match"
    UNEXPLAINED_DIFFERENCE = "unexplained_difference"


class ExpectedAction(str, Enum):
    """What a correct system should do with this case -- used only by the
    evaluation harness (future milestone), never fed to the engines themselves."""
    AUTO_RESOLVE = "auto_resolve"
    HUMAN_REVIEW = "human_review"
    UNRESOLVED = "unresolved"


class PaymentStatus(str, Enum):
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class SettlementStatus(str, Enum):
    SETTLED = "settled"
    REVERSED = "reversed"


class RefundStatus(str, Enum):
    PROCESSED = "processed"
    INITIATED = "initiated"


class OrderStatus(str, Enum):
    PAID = "paid"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class BankDirection(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class ReconciliationStatus(str, Enum):
    """Output status of the M2 deterministic reconciliation engine. This is
    deliberately coarser than ExceptionCategory: M2 decides WHETHER a record
    can be safely reconciled and how (matched/partial/mismatch/ambiguous/
    unresolved); assigning the fine-grained 14-value exception category is a
    later milestone's job (exception detection/classification), not the
    matching engine's. See docs/architecture.md and PROJECT_PLAN.md M5."""
    MATCHED = "matched"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class RelationshipType(str, Enum):
    """How a payment relates to the settlement(s)/bank transaction(s) it was
    reconciled against."""
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"  # one payment, split across multiple settlements
    MANY_TO_ONE = "many_to_one"  # multiple payments aggregated into one settlement
    NONE = "none"  # no relationship established (unresolved / no candidates)


# Every record produced anywhere in this codebase is synthetic/simulated.
# CLAUDE.md requires this be clearly labelled in both code and any future UI.
SIMULATED = True
