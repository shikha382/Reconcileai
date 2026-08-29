import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { StartRunPanel } from "../components/StartRunPanel";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";
import { useRunContext } from "../context/RunContext";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { RunResponse } from "../api/types";

export function RunsPage() {
  const runsState = useApi(() => api.listRuns(), []);
  const { setCurrentRunId } = useRunContext();
  const navigate = useNavigate();

  const handleStarted = (run: RunResponse) => {
    setCurrentRunId(run.run_id);
    runsState.reload();
  };

  const openRun = (runId: string) => {
    setCurrentRunId(runId);
    navigate("/");
  };

  return (
    <div className="page">
      <h1>Runs</h1>
      <StartRunPanel onStarted={handleStarted} />

      {runsState.status === "loading" && <LoadingState label="Loading runs" />}
      {runsState.status === "error" && <ErrorState error={runsState.error} onRetry={runsState.reload} />}
      {runsState.status === "ready" && runsState.data.items.length === 0 && <EmptyState title="No runs yet" hint="Start one above." />}
      {runsState.status === "ready" && runsState.data.items.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Started</th>
                <th>Completed</th>
                <th>Status</th>
                <th>Records</th>
                <th>Auto Resolved</th>
                <th>Human Review</th>
                <th>Blocked</th>
                <th>Unresolved</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runsState.data.items.map((run) => (
                <tr key={run.run_id}>
                  <td>
                    <code>{run.run_id}</code>
                  </td>
                  <td>{formatDateTime(run.started_at)}</td>
                  <td>{formatDateTime(run.completed_at)}</td>
                  <td>
                    <span className={`badge ${run.status === "completed" ? "badge--success" : "badge--danger"}`}>{run.status}</span>
                  </td>
                  <td className="num">{run.records_processed}</td>
                  <td className="num">{run.auto_resolved}</td>
                  <td className="num">{run.human_review}</td>
                  <td className="num">{run.blocked}</td>
                  <td className="num">{run.unresolved}</td>
                  <td>
                    <button type="button" className="btn btn--secondary" onClick={() => openRun(run.run_id)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
