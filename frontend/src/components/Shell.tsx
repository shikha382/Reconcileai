import { NavLink, Outlet } from "react-router-dom";
import { ErrorBoundary } from "./ErrorBoundary";
import { useRunContext } from "../context/RunContext";
import { truncateId } from "../lib/format";

const NAV_ITEMS = [
  { to: "/", label: "Overview", glyph: "⌂", end: true },
  { to: "/work-queue", label: "Work Queue", glyph: "◇" },
  { to: "/exceptions", label: "Exceptions", glyph: "≡" },
  { to: "/runs", label: "Runs", glyph: "↻" },
  { to: "/audit", label: "Audit Trail", glyph: "⌁" },
  { to: "/health", label: "System Health", glyph: "◉" },
  { to: "/about", label: "Why ReconcileAI", glyph: "✦" },
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
          <span className="shell__brand-mark" aria-hidden="true"><span>R</span></span>
          <span className="shell__brand-copy">
            <span className="shell__brand-name">ReconcileAI</span>
            <span className="shell__brand-subtitle">Finance control plane</span>
          </span>
        </div>
        <div className="shell__context">
          <span className="shell__env-badge" title="This build runs entirely on synthetic, deterministic demo data -- no live provider credentials exist.">
            DEMO · SYNTHETIC DATA
          </span>
          <span className="shell__run-indicator">
            {currentRunId ? (
              <>
                <span className="shell__status-dot" aria-hidden="true" /> Active run <code>{truncateId(currentRunId, 18)}</code>
              </>
            ) : (
              "Waiting for a run"
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
                  <span className="shell__nav-glyph" aria-hidden="true">{item.glyph}</span>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="shell__nav-note">
            <span>Safety model</span>
            <strong>AI proposes · Policy decides</strong>
          </div>
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
