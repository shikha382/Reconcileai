"""30 real local inference calls over ten real synthetic pipeline exceptions.

Writes measured outputs, never invents a human quality score. Run from repo root.
"""
import asyncio
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from fastapi.testclient import TestClient
from app.api.dependencies import get_session, get_run_registry, get_provider
from app.api.run_registry import RunRegistry
from app.ai.provider import MockAIProvider
from app.db.session import init_db, make_engine, make_session_factory
from app.main import app
from app.granite import MODEL, explain, snapshot
from app import granite


async def evaluate(decisions):
    rows = []
    for repeat in range(3):
        for index, decision in enumerate(decisions):
            facts = snapshot(decision)
            captured = []
            validator = granite.validate_answer
            def capture(raw, supplied):
                captured.append(raw)
                return validator(raw, supplied)
            granite.validate_answer = capture
            try:
                response = await explain(facts)
            finally:
                granite.validate_answer = validator
            row = {"scenario": index + 1, "repeat": repeat + 1, "facts": facts,
                   "response": response.model_dump(), "raw_model_output": captured,
                   "human_review": None}
            rows.append(row)
            print(json.dumps(row), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="granite-evaluation-results.json", help="JSON filename within docs/")
    parser.add_argument("--holdout", action="store_true", help="Nine alternate records plus the same golden fee-safety regression case")
    args = parser.parse_args()
    if Path(args.output).name != args.output or not args.output.endswith(".json"):
        parser.error("--output must be a simple .json filename")
    with tempfile.TemporaryDirectory(prefix="reconcile-granite-eval-") as temp:
        engine = make_engine(Path(temp) / "synthetic.db")
        init_db(engine)
        factory = make_session_factory(engine)
        registry = RunRegistry()
        def sessions():
            with factory() as session:
                yield session
        app.dependency_overrides[get_session] = sessions
        app.dependency_overrides[get_run_registry] = lambda: registry
        app.dependency_overrides[get_provider] = lambda: MockAIProvider()
        try:
            with TestClient(app) as client:
                run = client.post("/runs", json={"dataset": "seeds"})
                run.raise_for_status()
            decisions = registry.list_exceptions()
            # First preserve the adversarial fee case, then one case per
            # category/decision combination. Exact facts are saved for review.
            selected = []
            fee_case = next((d for d in decisions if snapshot(d)["residual"] == "9.83"), None)
            if fee_case:
                selected.append(fee_case)
            for category in [None, "missing_transaction", "ambiguous_match", "duplicate",
                             "partial_settlement", "over_settlement", "under_settlement",
                             "refund_mismatch", "timing_mismatch"]:
                candidates = [d for d in decisions if d.bundle.category == category]
                selected.append(candidates[1 if args.holdout else 0])
            assert len(selected) == 10
            rows = asyncio.run(evaluate(selected))
            report = {"timestamp": datetime.now(timezone.utc).isoformat(), "model": MODEL,
                      "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                      "working_tree": "uncommitted Granite implementation", "hardware": platform.platform(),
                      "configuration": {"context": 2048, "output_limit": 256, "temperature": 0, "keep_alive": "60s"},
                      "adapter_sha256": hashlib.sha256((ROOT / "backend/app/granite.py").read_bytes()).hexdigest(),
                      "holdout": args.holdout,
                      "rows": rows}
            path = ROOT / "docs" / args.output
            path.write_text(json.dumps(report, indent=2) + "\n")
            print(f"REPORT: {path}", flush=True)
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


if __name__ == "__main__":
    main()
