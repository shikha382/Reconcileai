"""In-memory registry of completed pipeline runs, for the API process's own
lifetime. NOT a new persistence layer for financial data or decisions --
`PipelineRunResult`/`DecisionResult` were already plain in-memory dataclasses
(M6/M7, unchanged); this registry just keeps them addressable by `run_id`/
`exception_id` across separate HTTP requests within one running process,
exactly the "GET must not rerun the pipeline" requirement.

Kept in-memory deliberately, for the same reasoning already established for
`ApprovalWorkflowStore` (M5) and `AIInvestigationTrace` (M4): no caller needs
a run summary to survive a process restart yet, and the durable record of
what actually happened already lives in the audit ledger regardless (`GET
/runs/{run_id}/audit` and `GET /exceptions/{id}/provenance` both read the
real, persistent database -- only the rich in-memory decision objects behind
`GET /exceptions` and `GET /exceptions/{id}` would be lost on a restart, and
that's documented as a known limitation, not silently unaddressed).
"""
from __future__ import annotations

from threading import Lock

from app.services.reconciliation_pipeline import PipelineRunResult


class RunNotFoundError(Exception):
    pass


class ExceptionNotFoundError(Exception):
    pass


class RunRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, PipelineRunResult] = {}
        # exception_id -> (run_id, order_id) -- exception_id is globally
        # unique (UUID-derived, app.engines.evidence.bundle), so no run_id
        # qualifier is needed to look one up directly.
        self._exception_index: dict[str, tuple[str, str]] = {}

    def add(self, result: PipelineRunResult) -> None:
        with self._lock:
            self._runs[result.run_id] = result
            for order_id, decision in result.decisions.items():
                self._exception_index[decision.exception_id] = (result.run_id, order_id)

    def get_run(self, run_id: str) -> PipelineRunResult:
        with self._lock:
            result = self._runs.get(run_id)
        if result is None:
            raise RunNotFoundError(run_id)
        return result

    def list_runs(self) -> list[PipelineRunResult]:
        with self._lock:
            return list(self._runs.values())

    def get_exception(self, exception_id: str):
        with self._lock:
            location = self._exception_index.get(exception_id)
        if location is None:
            raise ExceptionNotFoundError(exception_id)
        run_id, order_id = location
        run = self.get_run(run_id)
        return run.decisions[order_id]

    def list_exceptions(self, *, run_id: str | None = None):
        with self._lock:
            if run_id is not None:
                runs = [self._runs[run_id]] if run_id in self._runs else []
            else:
                runs = list(self._runs.values())
        decisions = []
        for run in runs:
            decisions.extend(run.decisions.values())
        return decisions
