// Phase 16: a read-only audit-log viewer. No mutation controls exist here or
// anywhere in this app -- GET /runs/{id}/audit and /audit/events are the
// only calls this page makes.
import { useState } from "react";
import { api } from "../api/client";
import { RunPicker } from "../components/RunPicker";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";
import { useRunContext } from "../context/RunContext";
import { formatDateTime, titleCase } from "../lib/format";
import { useApi } from "../lib/useApi";

const PAGE_SIZE = 25;

export function AuditPage() {
  const { currentRunId } = useRunContext();
  const runsState = useApi(() => api.listRuns(), []);
  const [eventTypeFilter, setEventTypeFilter] = useState("");
  const [page, setPage] = useState(1);

  if (runsState.status === "loading") return <LoadingState label="Loading runs" />;
  if (runsState.status === "error") return <ErrorState error={runsState.error} onRetry={runsState.reload} />;

  const runs = runsState.data.items;
  const activeRunId = currentRunId && runs.some((r) => r.run_id === currentRunId) ? currentRunId : runs[0]?.run_id ?? null;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Decision provenance"
        title="Audit Trail"
        description="A read-only, tamper-evident timeline of evidence, verification, policy, and final outcomes."
        actions={<RunPicker runs={runs} />}
      />
      {!activeRunId && <EmptyState title="No run selected" hint="Start or select a reconciliation run to see its audit trail." />}
      {activeRunId && <AuditForRun runId={activeRunId} eventTypeFilter={eventTypeFilter} setEventTypeFilter={setEventTypeFilter} page={page} setPage={setPage} />}
    </div>
  );
}

function AuditForRun({
  runId,
  eventTypeFilter,
  setEventTypeFilter,
  page,
  setPage,
}: {
  runId: string;
  eventTypeFilter: string;
  setEventTypeFilter: (v: string) => void;
  page: number;
  setPage: (p: number) => void;
}) {
  const statusState = useApi(() => api.getRunAuditStatus(runId), [runId]);
  const eventsState = useApi(() => api.listRunAuditEvents(runId, page, PAGE_SIZE), [runId, page]);

  if (statusState.status === "loading" || eventsState.status === "loading") return <LoadingState label="Loading audit trail" />;
  if (statusState.status === "error") return <ErrorState error={statusState.error} onRetry={statusState.reload} />;
  if (eventsState.status === "error") return <ErrorState error={eventsState.error} onRetry={eventsState.reload} />;

  const status = statusState.data;
  const { items, total } = eventsState.data;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const eventTypes = Array.from(new Set(items.map((e) => e.event_type))).sort();
  const filtered = eventTypeFilter ? items.filter((e) => e.event_type === eventTypeFilter) : items;

  return (
    <>
      <section className={`card audit-status ${status.chain_valid ? "audit-status--valid" : "audit-status--invalid"}`} aria-label="Audit chain status">
        <div className="financial-grid">
          <div>
            <span className="label">Chain Validity</span>
            <span className={status.chain_valid ? "text-success" : "text-danger"}>{status.chain_valid ? "Valid" : "INVALID"}</span>
          </div>
          <div>
            <span className="label">Total Events</span>
            <span>{status.event_count}</span>
          </div>
          {status.first_event && (
            <div>
              <span className="label">First Event</span>
              <span>
                {titleCase(status.first_event.event_type)} · {formatDateTime(status.first_event.timestamp)}
              </span>
            </div>
          )}
          {status.last_event && (
            <div>
              <span className="label">Last Event</span>
              <span>
                {titleCase(status.last_event.event_type)} · {formatDateTime(status.last_event.timestamp)}
              </span>
            </div>
          )}
        </div>
        {!status.chain_valid && status.invalid_reason && <p className="state-panel state-panel--error">{status.invalid_reason}</p>}
      </section>

      <div className="filter-bar">
        <label>
          Event type (this page)
          <select value={eventTypeFilter} onChange={(e) => setEventTypeFilter(e.target.value)}>
            <option value="">All</option>
            {eventTypes.map((t) => (
              <option key={t} value={t}>
                {titleCase(t)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No audit events match this filter" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Timestamp</th>
                <th>Event</th>
                <th>Actor</th>
                <th>Entity</th>
                <th>Correlation</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((event) => (
                <tr key={event.event_id}>
                  <td className="num">{event.sequence}</td>
                  <td>{formatDateTime(event.timestamp)}</td>
                  <td>{titleCase(event.event_type)}</td>
                  <td>
                    {titleCase(event.actor_type)}
                    {event.actor_id ? ` (${event.actor_id})` : ""}
                  </td>
                  <td>
                    {titleCase(event.entity_type)} {event.entity_id}
                  </td>
                  <td>
                    <code title={event.correlation_id}>{event.correlation_id.slice(0, 12)}…</code>
                  </td>
                  <td>
                    <details>
                      <summary>View</summary>
                      <pre className="audit-details">{event.details}</pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <nav className="pagination" aria-label="Audit event pages">
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
