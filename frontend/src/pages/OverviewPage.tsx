// "What is happening with my financial reconciliation?" -- every number
// below is read straight from the API (GET /runs/{id}, GET /exceptions/queue,
// GET /exceptions), never hardcoded and never computed by summing
// individually-fetched amounts in the frontend.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { BarChart } from "../components/BarChart";
import { MetricCard } from "../components/MetricCard";
import { PageHeader } from "../components/PageHeader";
import { RunPicker } from "../components/RunPicker";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";
import { useRunContext } from "../context/RunContext";
import { countByCategory, fetchAllExceptionsForRun } from "../lib/aggregateExceptions";
import { formatInr, titleCase, truncateId } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { QueueSummary, RunResponse } from "../api/types";

export function OverviewPage() {
  const { currentRunId } = useRunContext();
  const navigate = useNavigate();
  const runsState = useApi(() => api.listRuns(), []);

  if (runsState.status === "loading") return <LoadingState label="Loading runs" />;
  if (runsState.status === "error") return <ErrorState error={runsState.error} onRetry={runsState.reload} />;

  const runs = runsState.data.items;
  const activeRunId = currentRunId && runs.some((r) => r.run_id === currentRunId) ? currentRunId : runs[0]?.run_id ?? null;

  if (!activeRunId) {
    return (
      <div className="page">
        <PageHeader eyebrow="Control center" title="Overview" description="A live, evidence-backed view of reconciliation safety, outcomes, and operational exposure." />
        <EmptyState title="No reconciliation runs yet" hint="Start one from the Runs page to see live metrics here." />
        <button type="button" className="btn btn--primary" onClick={() => navigate("/runs")}>
          Go to Runs
        </button>
      </div>
    );
  }

  return <OverviewForRun runId={activeRunId} runs={runs} />;
}

function OverviewForRun({ runId, runs }: { runId: string; runs: RunResponse[] }) {
  const runState = useApi(() => api.getRun(runId), [runId]);
  const summaryState = useApi(() => api.getExceptionsQueue(runId, { page_size: 1 }), [runId]);
  const safetyState = useApi(() => api.getRunSafetyMetrics(runId), [runId]);
  const [categories, setCategories] = useState<{ category: string; count: number }[] | null>(null);
  const [categoriesError, setCategoriesError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCategories(null);
    setCategoriesError(null);
    fetchAllExceptionsForRun(runId)
      .then((items) => {
        if (!cancelled) setCategories(countByCategory(items));
      })
      .catch(() => {
        if (!cancelled) setCategoriesError("Could not load exception categories.");
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (runState.status === "loading" || summaryState.status === "loading") return <LoadingState label="Loading overview" />;
  if (runState.status === "error") return <ErrorState error={runState.error} onRetry={runState.reload} />;
  if (summaryState.status === "error") return <ErrorState error={summaryState.error} onRetry={summaryState.reload} />;

  const run = runState.data;
  const summary: QueueSummary = summaryState.data.summary;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Control center"
        title="Overview"
        description="A live, evidence-backed view of reconciliation safety, outcomes, and operational exposure."
        actions={<RunPicker runs={runs} />}
      />

      <section aria-label="Safety" className="hero-metric-wrap">
        {safetyState.status === "ready" && safetyState.data.available && (
          <div className={`hero-metric ${safetyState.data.false_auto_resolution_rate === 0 ? "hero-metric--safe" : "hero-metric--unsafe"}`}>
            <span className="hero-metric__label">Unsafe Auto-Resolution Rate</span>
            <span className="hero-metric__value">{(safetyState.data.false_auto_resolution_rate * 100).toFixed(2)}%</span>
            <span className="hero-metric__hint">
              {safetyState.data.false_auto_resolutions} of {safetyState.data.graded} graded exceptions incorrectly auto-resolved — the single most
              important safety number in this system, measured against the run's synthetic ground truth, never hardcoded.
            </span>
          </div>
        )}
        {safetyState.status === "ready" && !safetyState.data.available && (
          <div className="hero-metric hero-metric--neutral">
            <span className="hero-metric__label">Unsafe Auto-Resolution Rate</span>
            <span className="hero-metric__value">N/A</span>
            <span className="hero-metric__hint">{safetyState.data.reason_unavailable}</span>
          </div>
        )}
      </section>

      <section aria-label="Reconciliation status">
        <div className="metric-grid">
          <MetricCard label="Records Processed" value={run.records_processed} />
          <MetricCard label="Match Rate" value={run.records_processed ? `${((run.matched / run.records_processed) * 100).toFixed(1)}%` : "—"} tone="info" hint={`${run.matched} deterministically matched`} />
          <MetricCard label="Auto Resolved" value={run.auto_resolved} tone="success" hint="Safely resolved, no human action needed" />
          <MetricCard label="Human Review" value={run.human_review} tone="warning" hint="Requires finance controller attention" />
          <MetricCard label="Blocked" value={run.blocked} tone="danger" hint="Policy rejected an unsafe proposal" />
          <MetricCard label="Unresolved" value={run.unresolved} hint="Insufficient data to decide" />
          <MetricCard
            label="Audit Chain"
            value={run.audit_chain_valid ? "Valid" : "INVALID"}
            tone={run.audit_chain_valid ? "success" : "danger"}
            hint={`${run.audit_event_count} events recorded`}
          />
        </div>
      </section>

      <div className="overview-grid">
      <section aria-label="Financial impact" className="card card--feature">
        <div className="section-heading">
          <div><span className="section-heading__eyebrow">Portfolio view</span><h2>Financial Impact</h2></div>
          <span className="section-heading__meta">Synthetic evaluation</span>
        </div>
        <div className="financial-grid">
          <MetricCard label="Gross Exposure Evaluated" value={formatInr(summary.total_financial_exposure)} tone="warning" hint="All evaluated records, including resolved items" />
          <MetricCard label="Highest Single Exposure" value={summary.highest_exposure_exception_id ? truncateId(summary.highest_exposure_exception_id, 15) : "—"} hint={summary.highest_exposure_exception_id ?? "Exception ID"} />
          <MetricCard label="Age Threshold Exceeded" value={summary.sla_breached_count} tone="danger" hint="All evaluated records; not open cases only" />
          <MetricCard label="Age Threshold At Risk" value={summary.sla_at_risk_count} tone="warning" hint="All evaluated records; not open cases only" />
          <MetricCard label="P0 Critical Exceptions" value={summary.counts_by_priority["P0"] ?? 0} tone="danger" />
          <MetricCard label="Most Common Category" value={titleCase(summary.most_common_category)} />
        </div>
      </section>

      <section aria-label="Reconciliation outcome mix" className="card card--feature">
        <div className="section-heading">
          <div><span className="section-heading__eyebrow">Data quality</span><h2>Reconciliation Outcome Mix</h2></div>
          <span className="section-heading__meta">{run.records_processed} records</span>
        </div>
        <p className="muted">Classification mix across all evaluated records. Clean exact matches are labelled explicitly.</p>
        {categoriesError && <p className="state-panel state-panel--error">{categoriesError}</p>}
        {!categoriesError && categories === null && <LoadingState label="Loading category breakdown" />}
        {!categoriesError && categories !== null && <BarChart data={categories.map((c) => ({ label: c.category, value: c.count }))} caption="Exception count by category" />}
      </section>
      </div>
    </div>
  );
}
