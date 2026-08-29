"""Milestone 9's reusable adversarial mutation framework (Phase 3). Builds
deliberately-confusing scenarios by MUTATING COPIES of the real 300-record
M1 dataset -- never a separate, fake financial model. Every mutation
produces a fresh, unattached record (never touches a live SQLAlchemy
session), so scenarios never contaminate each other or the shared base
fixture.

Reuses the exact M2/M3/M4/M5/M6 entry points every prior milestone already
established (`run_exception_intelligence`, `run_decision_pipeline`) --
nothing here re-implements matching, verification, policy, or audit logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable

from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement
from app.engines.evidence.bundle import EvidenceBundle
from app.engines.evidence.graph import build_graph
from app.engines.reconciliation.candidate_generation import build_context
from app.services.decision_service import DecisionResult
from app.services.exception_service import run_exception_intelligence


def clone(obj, **overrides):
    """Generic clone for any of the six M1 SQLAlchemy models -- reads every
    mapped column off the source object and constructs a brand-new, session-
    -less instance, so mutating a clone's field can never mark the real
    session-attached object dirty or flush anything to the real database."""
    cls = type(obj)
    values = {c.name: getattr(obj, c.name) for c in cls.__table__.columns}
    values.update(overrides)
    return cls(**values)


@dataclass
class Dataset:
    payments: list[Payment]
    settlements: list[Settlement]
    bank_transactions: list[BankTransaction]
    refunds: list[Refund]
    fee_rules: list[FeeRule]

    def clone_all(self) -> "Dataset":
        return Dataset(
            payments=[clone(p) for p in self.payments],
            settlements=[clone(s) for s in self.settlements],
            bank_transactions=[clone(b) for b in self.bank_transactions],
            refunds=[clone(r) for r in self.refunds],
            fee_rules=[clone(f) for f in self.fee_rules],
        )


@dataclass
class Scenario:
    """Phase 3's required scenario metadata shape."""
    scenario_id: str
    base_record_id: str  # order_id (or payment_id) of the record under test
    mutation_type: str
    description: str
    expected_safety_outcome: str  # e.g. "human_review", "unresolved", "rejected", "auto_resolve_ok", "ambiguous"
    severity: str  # "critical" | "high" | "medium" | "low"


def find_payment_by_order(dataset: Dataset, order_id: str) -> Payment:
    return next(p for p in dataset.payments if p.order_id == order_id)


def settlements_for_payment(dataset: Dataset, payment_id: str) -> list[Settlement]:
    return [s for s in dataset.settlements if s.payment_id == payment_id]


def refunds_for_payment(dataset: Dataset, payment_id: str) -> list[Refund]:
    return [r for r in dataset.refunds if r.payment_id == payment_id]


def analyze(dataset: Dataset, target_payment_id: str) -> EvidenceBundle:
    """Runs M2 (reconcile_all) + M3 (exception intelligence) over the WHOLE
    mutated dataset (so ambiguity/candidate scoring sees the real universe of
    other records, not an artificially small one) and returns just the
    target payment's EvidenceBundle -- fast (~6-8k records/sec, M3's own
    benchmark), so running this once per scenario is cheap."""
    _, bundles = run_exception_intelligence(
        dataset.payments, dataset.settlements, dataset.bank_transactions, dataset.refunds, dataset.fee_rules,
    )
    by_payment = {b.payment_id: b for b in bundles}
    return by_payment[target_payment_id]


@dataclass
class DecisionEnvironment:
    """Shared, reusable machinery for running the full M4-M6 decision
    pipeline for ONE target exception at a time (not all 300 -- that would
    make a whole adversarial suite prohibitively slow for what is otherwise
    a cheap per-scenario check)."""
    ledger: object
    approval_store: object
    provider: object
    session: object


def decide_one(dataset: Dataset, target_payment_id: str, env: DecisionEnvironment, *, run_id: str | None = None) -> DecisionResult:
    from app.services.decision_service import run_decision_pipeline

    _, bundles = run_exception_intelligence(
        dataset.payments, dataset.settlements, dataset.bank_transactions, dataset.refunds, dataset.fee_rules,
    )
    bundle = next(b for b in bundles if b.payment_id == target_payment_id)
    context = build_context(dataset.payments, dataset.settlements, dataset.bank_transactions, dataset.refunds, dataset.fee_rules)
    graph = build_graph(dataset.payments, dataset.settlements, dataset.bank_transactions, dataset.refunds)
    payment = next(p for p in dataset.payments if p.payment_id == target_payment_id)
    reference_now = max(p.captured_at for p in dataset.payments)

    result = run_decision_pipeline(
        payment, bundle, context, graph, env.provider, env.ledger, reference_now, env.approval_store, run_id=run_id,
    )
    env.session.commit()
    return result


ONE_PAISA = Decimal("0.01")


def pick_by_archetype(ground_truth: list[dict], archetype: str, index: int = 0, *, not_adversarial: bool = True) -> str:
    """Picks the order_id of the Nth real dataset record of a given
    generator archetype -- lets scenarios start from a genuinely
    representative base case (e.g. a clean exact_match) rather than an
    arbitrarily chosen or synthetic-from-scratch one."""
    matches = [
        row["order_id"] for row in ground_truth
        if row["archetype"] == archetype and (not not_adversarial or not row.get("is_adversarial"))
    ]
    return matches[index]
