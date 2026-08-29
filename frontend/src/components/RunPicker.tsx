import { useNavigate } from "react-router-dom";
import type { RunResponse } from "../api/types";
import { formatDateTime } from "../lib/format";
import { useRunContext } from "../context/RunContext";

export function RunPicker({ runs }: { runs: RunResponse[] }) {
  const { currentRunId, setCurrentRunId } = useRunContext();
  const navigate = useNavigate();

  if (runs.length === 0) {
    return (
      <div className="run-picker run-picker--empty">
        <p>No reconciliation runs yet.</p>
        <button type="button" className="btn btn--primary" onClick={() => navigate("/runs")}>
          Go start one
        </button>
      </div>
    );
  }

  return (
    <div className="run-picker">
      <label htmlFor="run-picker-select">Run</label>
      <select
        id="run-picker-select"
        value={currentRunId ?? ""}
        onChange={(e) => setCurrentRunId(e.target.value || null)}
      >
        <option value="" disabled>
          Select a run…
        </option>
        {runs.map((run) => (
          <option key={run.run_id} value={run.run_id}>
            {run.run_id} — {formatDateTime(run.started_at)} ({run.status})
          </option>
        ))}
      </select>
    </div>
  );
}
