import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

type Result = Awaited<ReturnType<typeof api.explainWithGranite>>;

export function GraniteExplanation({ exceptionId }: { exceptionId: string }) {
  const [status, setStatus] = useState<Awaited<ReturnType<typeof api.graniteStatus>> | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    void api.graniteStatus(controller.signal).then(setStatus).catch(() => {
      if (!controller.signal.aborted) setStatus({ available: false, model: "granite4:3b", reason: "Local experiment is unavailable." });
    });
    return () => {
      controller.abort();
      request.current?.abort();
      generation.current++;
    };
  }, []);

  async function explain() {
    const token = ++generation.current;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setMessage(""); setResult(null);
    try {
      const health = await api.graniteStatus(controller.signal);
      if (token !== generation.current) return;
      setStatus(health);
      if (!health.available) { setMessage(health.reason ?? "Model unavailable."); return; }
      const response = await api.explainWithGranite(exceptionId, controller.signal);
      if (token === generation.current) setResult(response);
    } catch (error) {
      if (token === generation.current) setMessage(error instanceof Error ? error.message : "Explanation failed. Please retry.");
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }

  function cancel() {
    generation.current++;
    request.current?.abort();
    setLoading(false); setMessage("Explanation cancelled.");
  }

  return (
    <section className="card granite-panel" aria-label="IBM Granite local explanation" aria-busy={loading}>
      <h2>Explain this exception — IBM Granite</h2>
      <p className="muted">Local experiment · English · Explanation only, not a financial decision.</p>
      <p>The financial amounts and policy decision above remain authoritative.</p>
      <div className="granite-panel__controls">
        <button className="btn btn--primary" type="button" onClick={() => void explain()} disabled={loading || status === null}>
          {result || message || status?.available === false ? "Retry explanation" : "Explain this exception"}
        </button>
        {loading && <button className="btn btn--secondary" type="button" onClick={cancel}>Cancel</button>}
      </div>
      <div role="status" aria-live="polite">
        {status === null && <p>Checking local model availability…</p>}
        {loading && <p>Generating explanation locally…</p>}
        {!loading && message && <p>{message}</p>}
        {!loading && !message && status?.available === false && <p>{status.reason}</p>}
      </div>
      {result && (
        <div aria-live="polite">
          <h3>{result.source === "granite" ? "AI-generated explanation — review against the facts" : "Deterministic fallback — not an AI answer"}</h3>
          {result.fallback_reason && <p className="muted">{result.fallback_reason}</p>}
          <p>{result.explanation}</p>
          <p className="muted">Model: {result.model} · {(result.elapsed_ms / 1000).toFixed(1)} seconds</p>
        </div>
      )}
    </section>
  );
}
