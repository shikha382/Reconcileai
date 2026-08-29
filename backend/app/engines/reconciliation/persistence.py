"""Thin adapter from in-memory ReconciliationResult objects to persisted
ReconciliationMatch rows. Kept separate from engine.py so the engine itself
never needs a database session to run or be tested."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.db.models import ReconciliationMatch
from app.engines.reconciliation.types import ReconciliationResult
from shared.money import dumps


def _candidates_json(result: ReconciliationResult) -> str:
    return dumps([
        {
            "settlement_id": c.settlement_id,
            "accepted": c.accepted,
            "score": asdict(c.score),
            "why_matched": c.why_matched,
            "why_not_matched": c.why_not_matched,
        }
        for c in result.candidates
    ])


def to_orm(result: ReconciliationResult) -> ReconciliationMatch:
    return ReconciliationMatch(
        reconciliation_id=result.reconciliation_id,
        payment_id=result.payment_id,
        order_id=result.order_id,
        status=result.status.value,
        method=result.method,
        relationship_type=result.relationship.value,
        matched_settlement_ids_json=dumps(result.matched_settlement_ids),
        matched_bank_txn_ids_json=dumps(result.matched_bank_txn_ids),
        matched_refund_ids_json=dumps(result.matched_refund_ids),
        score=result.score,
        candidates_json=_candidates_json(result),
        why_matched_json=dumps(result.why_matched),
        why_not_matched_json=dumps(result.why_not_matched),
        differences_json=dumps(result.differences),
        financial_impact=result.financial_impact,
        created_at=result.created_at,
        engine_version=result.engine_version,
    )


def persist_results(session: Session, results: list[ReconciliationResult]) -> None:
    for result in results:
        session.merge(to_orm(result))
