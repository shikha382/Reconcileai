// Phase 17/22/23: GET /health and GET /sources/status only. Deliberately
// shows nothing beyond what those endpoints return -- no environment
// variables, API keys, database credentials, or internal paths (neither
// backend endpoint ever includes them, per app/api/schemas.py). The Data
// Sources section never claims "LIVE" unless the backend itself reports
// LIVE READ-ONLY (which requires real, configured credentials) -- a
// fixture-mode adapter is always shown honestly as SYNTHETIC DATA.
import { api } from "../api/client";
import { ErrorState, LoadingState } from "../components/StatusStates";
import { PageHeader } from "../components/PageHeader";
import { useApi } from "../lib/useApi";

const MODE_TONE: Record<string, string> = {
  "SYNTHETIC DATA": "badge--info",
  "MOCK PROVIDER": "badge--neutral",
  "LIVE READ-ONLY": "badge--success",
  UNAVAILABLE: "badge--danger",
};

export function HealthPage() {
  const healthState = useApi(() => api.health(), []);
  const sourcesState = useApi(() => api.sourcesStatus(), []);

  return (
    <div className="page">
      <PageHeader eyebrow="Runtime visibility" title="System Health" description="Credential-safe status for the API and every configured data source." />
      {healthState.status === "loading" && <LoadingState label="Checking API" />}
      {healthState.status === "error" && <ErrorState error={healthState.error} onRetry={healthState.reload} />}
      {healthState.status === "ready" && (
        <section className="card">
          <div className="financial-grid">
            <div>
              <span className="label">API Status</span>
              <span className={healthState.data.status === "ok" ? "text-success" : "text-danger"}>{healthState.data.status.toUpperCase()}</span>
            </div>
            <div>
              <span className="label">Service</span>
              <span>{healthState.data.service}</span>
            </div>
          </div>
          <p className="muted">
            This page reflects only what the backend's health endpoint reports. It never exposes environment variables, API
            keys, database credentials, or internal file paths.
          </p>
        </section>
      )}

      <section className="card" aria-label="Data sources">
        <h2>Data Sources</h2>
        {sourcesState.status === "loading" && <LoadingState label="Checking data sources" />}
        {sourcesState.status === "error" && <ErrorState error={sourcesState.error} onRetry={sourcesState.reload} />}
        {sourcesState.status === "ready" && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Mode</th>
                  <th>Configured</th>
                  <th>Available</th>
                  <th>Records</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {sourcesState.data.sources.map((s) => (
                  <tr key={s.name}>
                    <td>{s.name}</td>
                    <td>
                      <span className={`badge ${MODE_TONE[s.mode] ?? "badge--neutral"}`}>{s.mode}</span>
                    </td>
                    <td>{s.configured ? "Yes" : "No"}</td>
                    <td>{s.available ? "Yes" : "No"}</td>
                    <td className="num">{s.record_count ?? "—"}</td>
                    <td className="muted">{s.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">
          A source is only ever shown as <strong>LIVE READ-ONLY</strong> when real provider credentials are actually
          configured — this demo runs entirely on <strong>SYNTHETIC DATA</strong> by default.
        </p>
      </section>
    </div>
  );
}
