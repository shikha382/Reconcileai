import { NavLink, Outlet } from "react-router-dom";
import { ErrorBoundary } from "./ErrorBoundary";
import { useRunContext } from "../context/RunContext";
import { truncateId } from "../lib/format";

const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true },
  { to: "/work-queue", label: "Work Queue" },
  { to: "/exceptions", label: "Exceptions" },
  { to: "/runs", label: "Runs" },
  { to: "/audit", label: "Audit" },
  { to: "/health", label: "System Health" },
  { to: "/about", label: "Why ReconcileAI" },
];

export function Shell() {
  const { currentRunId } = useRunContext();

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="shell__topbar">
        <div className="shell__brand">
          <span className="shell__brand-mark" aria-hidden="true">
            ◆
          </span>
          <span className="shell__brand-name">RECONCILEAI</span>
          <span className="shell__brand-subtitle">Finance Controller Command Center</span>
        </div>
        <div className="shell__context">
          <span className="shell__env-badge" title="This build runs entirely on synthetic, deterministic demo data -- no live provider credentials exist.">
            DEMO · SYNTHETIC DATA
          </span>
          <span className="shell__run-indicator">
            {currentRunId ? (
              <>
                Active run <code>{truncateId(currentRunId, 18)}</code>
              </>
            ) : (
              "No run selected"
            )}
          </span>
        </div>
      </header>
      <div className="shell__body">
        <nav className="shell__nav" aria-label="Primary">
          <ul>
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className={({ isActive }) => (isActive ? "shell__nav-link shell__nav-link--active" : "shell__nav-link")}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main id="main-content" className="shell__main">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
