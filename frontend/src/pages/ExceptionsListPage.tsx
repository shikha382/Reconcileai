// A plain, un-prioritized exception list (GET /exceptions) -- filtering and
// a practical ID/order/payment search (Phase 21) without loading massive
// datasets solely to search them client-side.
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { DecisionBadge, RiskBadge } from "../components/Badges";
import { PageHeader } from "../components/PageHeader";
import { RunPicker } from "../components/RunPicker";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";
import { useRunContext } from "../context/RunContext";
import { formatInr, titleCase, truncateId } from "../lib/format";
import { useApi } from "../lib/useApi";

const PAGE_SIZE = 25;

export function ExceptionsListPage() {
  const { currentRunId } = useRunContext();
  const runsState = useApi(() => api.listRuns(), []);
  const navigate = useNavigate();

  const [category, setCategory] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [decision, setDecision] = useState("");
  const [page, setPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  if (runsState.status === "loading") return <LoadingState label="Loading runs" />;
  if (runsState.status === "error") return <ErrorState error={runsState.error} onRetry={runsState.reload} />;

  const runs = runsState.data.items;
  const activeRunId = currentRunId && runs.some((r) => r.run_id === currentRunId) ? currentRunId : runs[0]?.run_id ?? null;

  const runSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const term = searchTerm.trim();
    if (!term) return;
    setSearching(true);
    setSearchError(null);
    try {
      if (term.startsWith("EXC-")) {
        await api.getException(term);
        navigate(`/exceptions/${term}`);
        return;
      }
      setSearchError("Search by exact exception ID (starting with EXC-), or use the Category/Risk/Decision filters below for order/payment matches on the current page.");
    } catch (err) {
      setSearchError(err instanceof ApiError ? err.message : "Exception not found.");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Evidence registry"
        title="Reconciliation Records"
        description="Inspect every evaluated record—including clean matches—and drill into its evidence, policy, and provenance."
        actions={<RunPicker runs={runs} />}
      />

      <form className="search-bar" role="search" onSubmit={runSearch}>
        <label htmlFor="exception-search" className="sr-only">
          Search by exception ID
        </label>
        <input
          id="exception-search"
          type="text"
          placeholder="Search exception ID (EXC-…)"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        <button type="submit" className="btn btn--secondary" disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </button>
      </form>
      {searchError && <p className="state-panel state-panel--error">{searchError}</p>}

      {!activeRunId && <EmptyState title="No run selected" hint="Start or select a reconciliation run to see its exceptions." />}
      {activeRunId && (
        <ExceptionsTable
          runId={activeRunId}
          category={category}
          riskLevel={riskLevel}
          decision={decision}
          page={page}
          onCategory={(v) => {
            setCategory(v);
            setPage(1);
          }}
          onRiskLevel={(v) => {
            setRiskLevel(v);
            setPage(1);
          }}
          onDecision={(v) => {
            setDecision(v);
            setPage(1);
          }}
          onPage={setPage}
        />
      )}
    </div>
  );
}

function ExceptionsTable({
  runId,
  category,
  riskLevel,
  decision,
  page,
  onCategory,
  onRiskLevel,
  onDecision,
  onPage,
}: {
  runId: string;
  category: string;
  riskLevel: string;
  decision: string;
  page: number;
  onCategory: (v: string) => void;
  onRiskLevel: (v: string) => void;
  onDecision: (v: string) => void;
  onPage: (p: number) => void;
}) {
  const listState = useApi(
    () => api.listExceptions({ run_id: runId, category: category || undefined, risk_level: riskLevel || undefined, decision: decision || undefined, page, page_size: PAGE_SIZE }),
    [runId, category, riskLevel, decision, page],
  );

  if (listState.status === "loading") return <LoadingState label="Loading exceptions" />;
  if (listState.status === "error") return <ErrorState error={listState.error} onRetry={listState.reload} />;

  const { items, total } = listState.data;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <div className="filter-bar">
        <label>
          Category
          <input type="text" value={category} onChange={(e) => onCategory(e.target.value)} placeholder="e.g. fee_mismatch" />
        </label>
        <label>
          Risk
          <select value={riskLevel} onChange={(e) => onRiskLevel(e.target.value)}>
            <option value="">All</option>
            <option value="LOW">Low</option>
            <option value="MEDIUM">Medium</option>
            <option value="HIGH">High</option>
            <option value="CRITICAL">Critical</option>
          </select>
        </label>
        <label>
          Decision
          <select value={decision} onChange={(e) => onDecision(e.target.value)}>
            <option value="">All</option>
            <option value="SAFE_TO_RESOLVE">Auto Resolved</option>
            <option value="HUMAN_REVIEW">Human Review</option>
            <option value="REJECTED">Blocked</option>
            <option value="ESCALATED">Escalated</option>
            <option value="UNRESOLVED">Unresolved</option>
          </select>
        </label>
      </div>

      {items.length === 0 ? (
        <EmptyState title="No exceptions match these filters" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Exception</th>
                <th>Order</th>
                <th>Payment</th>
                <th>Category</th>
                <th>Exposure</th>
                <th>Risk</th>
                <th>AI Investigated</th>
                <th>Contradiction</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.exception_id}>
                  <td>
                    <Link to={`/exceptions/${item.exception_id}`} title={item.exception_id}>{truncateId(item.exception_id, 15)}</Link>
                  </td>
                  <td><span title={item.order_id}>{truncateId(item.order_id, 12)}</span></td>
                  <td><span title={item.payment_id}>{truncateId(item.payment_id, 12)}</span></td>
                  <td>{titleCase(item.category)}</td>
                  <td className="num">{formatInr(item.financial_exposure)}</td>
                  <td>
                    <RiskBadge level={item.risk_level} />
                  </td>
                  <td>{item.ai_investigated ? "Yes" : "No"}</td>
                  <td>{item.contradiction_found ? "⚠ Yes" : "No"}</td>
                  <td>
                    <DecisionBadge decision={item.decision} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <nav className="pagination" aria-label="Exceptions pages">
        <button type="button" className="btn btn--secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {totalPages}
        </span>
        <button type="button" className="btn btn--secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </nav>
    </>
  );
}
