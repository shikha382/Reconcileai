"""Phase 21 CLI: verify the tamper-evident hash chain of a ReconcileAI
audit ledger database.

Usage:
    python scripts/verify_audit_ledger.py [path/to/database.db]

Defaults to backend/reconcileai.db (app.config's default) if no path given.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.audit.verify import verify_chain  # noqa: E402
from app.db.session import make_session_factory, make_engine  # noqa: E402


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (REPO_ROOT / "backend" / "reconcileai.db")

    print("RECONCILEAI AUDIT LEDGER")
    print("=" * 24)
    print()

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 2

    engine = make_engine(db_path)
    session = make_session_factory(engine)()
    result = verify_chain(session)

    print(f"Events checked: {result.events_checked:,}")
    print()
    if result.valid:
        print("Chain: VALID")
        return 0

    print("Chain: INVALID")
    print(f"Event: {result.first_invalid_event_id}")
    print(f"Reason: {result.reason}")
    if result.details:
        print(f"Details: {result.details}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
