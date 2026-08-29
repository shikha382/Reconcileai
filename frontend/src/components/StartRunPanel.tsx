// Phase 18: a controlled UI for POST /runs. Shows what will happen BEFORE
// starting, then a real (not simulated) running/result state. No fake
// progress percentage -- the API returns a completed result in one response;
// there is no intermediate status to poll, so we say so plainly rather than
// inventing a progress bar the backend cannot back up.
import { useState } from "react";
import { api, ApiError as ApiErrorClass } from "../api/client";
import type { RunResponse } from "../api/types";

const PIPELINE_STAGES = ["Ingest", "Reconcile", "Investigate", "Verify", "Decide", "Audit"];

export function StartRunPanel({ onStarted }: { onStarted: (run: RunResponse) => void }) {
  const [dataset] = useState("seeds");
  const [state, setState] = useState<"idle" | "running" | "error">("idle");
  const [error, setError] = useState<ApiErrorClass | null>(null);

  const start = async () => {
    setState("running");
    setError(null);
    try {
      const run = await api.startRun(dataset);
      setState("idle");
      onStarted(run);
    } catch (e) {
      setState("error");
      setError(e instanceof ApiErrorClass ? e : new ApiErrorClass(String(e), "UNKNOWN_ERROR", 0, null));
    }
  };

  return (
    <section className="card start-run-panel">
      <h2>Start Reconciliation</h2>
      <p className="muted">This runs the complete deterministic + AI-assisted pipeline against the real synthetic dataset.</p>

      <div className="start-run-panel__grid">
        <div>
          <h3>Sources</h3>
          <ul className="plain-list">
            <li>Payment data</li>
            <li>Settlement data</li>
            <li>Bank transaction data</li>
            <li>Order data</li>
            <li>Refund data</li>
            <li>Fee rules</li>
          </ul>
        </div>
        <div>
          <h3>Workflow</h3>
          <ol className="stage-list">
            {PIPELINE_STAGES.map((stage) => (
              <li key={stage}>{stage}</li>
            ))}
          </ol>
        </div>
      </div>

      <button type="button" className="btn btn--primary" onClick={start} disabled={state === "running"}>
        {state === "running" ? "Running…" : "Start reconciliation"}
      </button>

      {state === "running" && (
        <p className="start-run-panel__status" role="status" aria-live="polite">
          RUNNING — the API executes every stage synchronously and returns the finished result; there is no partial-progress
          endpoint to poll, so no percentage is shown.
        </p>
      )}
      {state === "error" && error && (
        <p className="start-run-panel__status start-run-panel__status--error" role="alert">
          {error.message} ({error.code})
        </p>
      )}
    </section>
  );
}
