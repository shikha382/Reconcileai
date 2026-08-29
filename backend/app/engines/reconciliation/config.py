"""All tunable constants for the reconciliation engine, in one place, so they
can be tuned against ground truth without hunting through engine logic
(CLAUDE.md / docs/ai-design.md's rule for confidence thresholds applies
equally to this deterministic scorer). Values below were set from first
principles, then checked against the 300-record evaluation and left as-is
where they produced correct results -- see docs/evaluation.md / the M2
evaluation report in PROJECT_PLAN.md for the numbers that validated them.
"""
from decimal import Decimal

# --- Date tolerance windows (days) ---
# Stage 1/2 ("exact"/"normalized-reference" match) require the settlement to
# have posted within this many days of the payment -- tight enough that a
# genuine timing_mismatch (2-5 day lag, per data/synthetic/generator.py)
# does NOT qualify here and instead falls through to Stage 3.
TIGHT_DATE_TOLERANCE_DAYS = 1

# Stage 3 ("financial consistency") uses a more generous window to accommodate
# real settlement lag, while still bounding candidate generation.
LENIENT_DATE_TOLERANCE_DAYS = 6

# --- Financial tolerances ---
# Amounts must match to the paisa for "exact"; this is a rounding safety
# margin only (should never actually be hit given Decimal-only arithmetic
# throughout -- see shared/money.py), not a business tolerance.
AMOUNT_EXACT_TOLERANCE = Decimal("0.00")

# When verifying settlement.net_amount against a FeeRule's computed value,
# allow this much slack for compounding rounding across fee+tax, not for
# genuine unexplained differences.
FEE_VERIFICATION_TOLERANCE = Decimal("0.01")

# --- Multi-field scoring weights (must sum to 1.0; enforced by an assertion
# in scoring.py). Each has a stated reason -- no signal is included "to look
# sophisticated" (explicit project rule).
SCORE_WEIGHTS: dict[str, Decimal] = {
    "reference": Decimal("0.30"),  # the strongest positive signal when references genuinely agree
    "amount": Decimal("0.30"),     # a financial system's most fundamental fact
    "date": Decimal("0.15"),       # settlement lag is expected and should only mildly penalize
    "fee": Decimal("0.15"),        # rewards a mathematically-verified fee relationship
    "merchant": Decimal("0.05"),   # a secondary corroborating signal, not decisive alone
    "link": Decimal("0.05"),       # small bonus for a confirmed bank credit / direct FK link
}

# --- Decision thresholds ---
# A candidate must clear this total score to be auto-resolved as MATCHED via
# scoring (Stage 5+); records resolved directly via Stage 1-3's hard checks
# don't go through this threshold at all (they're either exactly right or
# they're not).
AUTO_RESOLVE_SCORE_THRESHOLD = Decimal("0.90")

# If the best and second-best candidate scores are within this margin of each
# other, the result is AMBIGUOUS regardless of how high the top score is --
# the non-negotiable ambiguity rule from the M2 brief. Never auto-pick "the
# highest score" when a genuine rival is close behind.
AMBIGUITY_MARGIN = Decimal("0.05")

# A candidate-scored payment whose top score falls below this floor has no
# real evidence to act on at all (UNRESOLVED). Above it but below the
# auto-resolve threshold (or too close to a rival) is AMBIGUOUS -- there IS
# a plausible candidate, just not enough certainty to safely auto-resolve.
MIN_PLAUSIBLE_CANDIDATE_SCORE = Decimal("0.50")

ENGINE_VERSION = "reconciliation-engine-0.1.0"
