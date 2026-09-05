// M11's work queue, exposed here exactly as the backend orders it -- this
// page NEVER recomputes priority or re-sorts client-side; the backend
// (GET /exceptions/queue) remains the sole authority on ordering (Phase 7).
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { PriorityBadge, RiskBadge, SlaBadge, DecisionBadge } from "../components/Badges";
import { PageHeader } from "../components/PageHeader";
import { RunPicker } from "../components/RunPicker";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";
import { useRunContext } from "../context/RunContext";
import { formatInr, titleCase, truncateId } from "../lib/format";
import { useApi } from "../lib/useApi";

const PRIORITIES = ["P0", "P1", "P2", "P3"];
const DECISION_STATUSES = ["SAFE_TO_RESOLVE", "HUMAN_REVIEW", "REJECTED", "ESCALATED", "UNRESOLVED"];
const SLA_STATUSES = ["BREACHED", "AT_RISK", "WITHIN_SLA"];
const PAGE_SIZE = 25;

export function WorkQueuePage() {
  const { currentRunId } = useRunContext();
  const runsState = useApi(() => api.listRuns(), []);

  const [priority, setPriority] = useState("");
  const [decisionStatus, setDecisionStatus] = useState("");
  const [slaStatus, setSlaStatus] = useState("");
  const [minExposure, setMinExposure] = useState("");
  const [page, setPage] = useState(1);

  if (runsState.status === "loading") return <LoadingState label="Loading runs" />;
  if (runsState.status === "error") return <ErrorState error={runsState.error} onRetry={runsState.reload} />;

  const runs = runsState.data.items;
  const activeRunId = currentRunId && runs.some((r) => r.run_id === currentRunId) ? currentRunId : runs[0]?.run_id ?? null;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Operations"
        title="Work Queue"
        description="Backend-ranked records ordered by priority, exposure, and age—never re-ranked in the browser."
        actions={<RunPicker runs={runs} />}
      />

      {!activeRunId && <EmptyState title="No run selected" hint="Start or select a reconciliation run to see its work queue." />}
      {activeRunId && (
        <QueueTable
          runId={activeRunId}
          filters={{ priority, decisionStatus, slaStatus, minExposure, page }}
          onFilterChange={{ setPriority, setDecisionStatus, setSlaStatus, setMinExposure, setPage }}
        />
      )}
    </div>
  );
}

interface Filters {
  priority: string;
  decisionStatus: string;
  slaStatus: string;
  minExposure: string;
  page: number;
}

interface FilterSetters {
  setPriority: (v: string) => void;
  setDecisionStatus: (v: string) => void;
  setSlaStatus: (v: string) => void;
  setMinExposure: (v: string) => void;
  setPage: (v: number) => void;
}

function QueueTable({ runId, filters, onFilterChange }: { runId: string; filters: Filters; onFilterChange: FilterSetters }) {
  const { priority, decisionStatus, slaStatus, minExposure, page } = filters;
  const { setPriority, setDecisionStatus, setSlaStatus, setMinExposure, setPage } = onFilterChange;

  const queueState = useApi(
    () =>
      api.getExceptionsQueue(runId, {
        priority: priority || undefined,
        decision_status: decisionStatus || undefined,
        sla_status: slaStatus || undefined,
        min_exposure: minExposure || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [runId, priority, decisionStatus, slaStatus, minExposure, page],
  );

  if (queueState.status === "loading") return <LoadingState label="Loading work queue" />;
  if (queueState.status === "error") return <ErrorState error={queueState.error} onRetry={queueState.reload} />;

  const { items, summary, total } = queueState.data;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <div className="filter-bar" role="search" aria-label="Work queue filters">
        <label>
          Priority
          <select
            value={priority}
            onChange={(e) => {
              setPriority(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          Decision
          <select
            value={decisionStatus}
            onChange={(e) => {
              setDecisionStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All</option>
            {DECISION_STATUSES.map((d) => (
              <option key={d} value={d}>
                {titleCase(d)}
              </option>
            ))}
          </select>
        </label>
        <label>
          SLA
          <select
            value={slaStatus}
            onChange={(e) => {
              setSlaStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All</option>
            {SLA_STATUSES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Min. exposure (₹)
          <input
            type="number"
            min="0"
            inputMode="decimal"
            value={minExposure}
            onChange={(e) => {
              setMinExposure(e.target.value);
              setPage(1);
            }}
            placeholder="0.00"
          />
        </label>
      </div>

      <div className="queue-summary" aria-label="Queue summary">
        <span><strong>{summary.total}</strong> evaluated</span>
        <span><strong>{summary.counts_by_priority["P0"] ?? 0}</strong> P0 critical</span>
        <span><strong>{formatInr(summary.total_financial_exposure)}</strong> gross exposure</span>
      </div>

      {items.length === 0 ? (
        <EmptyState title="No exceptions match these filters" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Exception</th>
                <th>Category</th>
                <th>Exposure</th>
                <th>Risk</th>
                <th>SLA</th>
                <th>Age</th>
                <th>Reasons</th>
                <th>Recommended Action</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.exception_id} className={item.priority === "P0" ? "data-table__row--p0" : undefined}>
                  <td>
                    <PriorityBadge priority={item.priority} />
                  </td>
                  <td>
                    <Link to={`/exceptions/${item.exception_id}`} state={{ priorityItem: item }}>
                      <span title={item.exception_id}>{truncateId(item.exception_id, 15)}</span>
                    </Link>
                  </td>
                  <td>{titleCase(item.exception_category)}</td>
                  <td className="num">{formatInr(item.financial_exposure)}</td>
                  <td>
                    <RiskBadge level={item.risk_level} />
                  </td>
                  <td>
                    <SlaBadge status={item.sla_status} />
                  </td>
                  <td className="num">{item.age_days}d</td>
                  <td>
                    <div className="reason-chips">
                      {item.reason_codes.slice(0, 3).map((code) => (
                        <span className="reason-chip" key={code}>{titleCase(code)}</span>
                      ))}
                      {item.reason_codes.length > 3 && (
                        <span className="reason-chip reason-chip--more" title={item.reason_codes.slice(3).map(titleCase).join(", ")}>
                          +{item.reason_codes.length - 3} more
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="recommended-action">{titleCase(item.recommended_action)}</td>
                  <td>
                    <DecisionBadge decision={item.decision_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <nav className="pagination" aria-label="Work queue pages">
        <button type="button" className="btn btn--secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {totalPages}
        </span>
        <button type="button" className="btn btn--secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </nav>
    </>
  );
}
