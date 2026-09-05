// The frontend's ONLY piece of global state: which run_id the Overview/Work
// Queue/Audit screens are currently looking at. This is a UI convenience,
// not a second source of truth -- every screen still re-fetches the real
// run/exception/queue data for whatever run_id is selected here; nothing is
// cached as if it were authoritative.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

const STORAGE_KEY = "reconcileai.currentRunId";

interface RunContextValue {
  currentRunId: string | null;
  setCurrentRunId: (runId: string | null) => void;
}

const RunContext = createContext<RunContextValue | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const [currentRunId, setCurrentRunIdState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const setCurrentRunId = useCallback((runId: string | null) => {
    setCurrentRunIdState(runId);
    try {
      if (runId) localStorage.setItem(STORAGE_KEY, runId);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Private-mode/blocked storage -- the in-memory state above still works for this session.
    }
  }, []);

  const value = useMemo(() => ({ currentRunId, setCurrentRunId }), [currentRunId, setCurrentRunId]);

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRunContext(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRunContext must be used within a RunProvider");
  return ctx;
}
