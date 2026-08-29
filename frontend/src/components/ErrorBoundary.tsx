// Phase 22: a last-resort guard against a malformed/unexpected backend
// response causing a raw white-screen crash. Never renders the caught
// error's message or stack -- just a generic, honest "something broke"
// panel, consistent with the backend's own generic 500 handler.
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Server-side-style logging only -- never surfaced to the viewer.
    console.error("ReconcileAI frontend render error:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="state-panel state-panel--error" role="alert">
          <p className="state-panel__title">Something went wrong displaying this page</p>
          <p className="state-panel__hint">This is usually caused by an unexpected API response shape. Try reloading the page.</p>
        </div>
      );
    }
    return this.props.children;
  }
}
