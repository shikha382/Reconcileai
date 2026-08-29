// A small shared data-fetching hook so every page handles loading/error
// states identically (Phase 22) without a heavier data-fetching library.
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export type ApiState<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: T };

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[]): ApiState<T> & { reload: () => void } {
  const [state, setState] = useState<ApiState<T>>({ status: "loading" });
  const requestIdRef = useRef(0);

  const load = () => {
    const thisRequestId = ++requestIdRef.current;
    setState({ status: "loading" });
    fetcher()
      .then((data) => {
        if (requestIdRef.current === thisRequestId) setState({ status: "ready", data });
      })
      .catch((error) => {
        if (requestIdRef.current === thisRequestId) {
          setState({ status: "error", error: error instanceof ApiError ? error : new ApiError(String(error), "UNKNOWN_ERROR", 0, null) });
        }
      });
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, deps);

  return { ...state, reload: load };
}
