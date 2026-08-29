// Shared loading / empty / error presentation (Phase 22). Errors always
// render the backend's own structured {code, message} -- never a stack
// trace, never raw exception text.
import type { ApiError } from "../api/client";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state-panel state-panel--loading" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <p>{label}…</p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="state-panel state-panel--empty" role="status">
      <p className="state-panel__title">{title}</p>
      {hint && <p className="state-panel__hint">{hint}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; hint?: string; onRetry?: () => void }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <p className="state-panel__title">Something went wrong</p>
      <p className="state-panel__hint">
        {error.message}
        {error.code ? <span className="state-panel__code"> ({error.code})</span> : null}
      </p>
      {error.requestId && <p className="state-panel__request-id">Request ID: {error.requestId}</p>}
      {onRetry && (
        <button type="button" className="btn btn--secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
