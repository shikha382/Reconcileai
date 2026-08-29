import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunProvider } from "../context/RunContext";
import { OverviewPage } from "../pages/OverviewPage";
import { installFetchMock, mockExceptionList, mockQueue, mockRunList, mockSafetyMetrics } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("OverviewPage", () => {
  it("renders real metrics from the API, never hardcoded values", async () => {
    installFetchMock({
      "/runs/RUN-test0001/safety-metrics": mockSafetyMetrics,
      "/runs/RUN-test0001": mockRunList.items[0],
      "/runs": mockRunList,
      "/exceptions/queue": mockQueue,
      "/exceptions": mockExceptionList,
    });

    render(
      <MemoryRouter>
        <RunProvider>
          <OverviewPage />
        </RunProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("Records Processed")).toBeInTheDocument());
    expect(screen.getByText("300")).toBeInTheDocument(); // records_processed, read from the mock RunResponse
    expect(screen.getByText("219")).toBeInTheDocument(); // auto_resolved
    expect(screen.getByText("67")).toBeInTheDocument(); // human_review
    expect(await screen.findByText("Financial Impact")).toBeInTheDocument();
    expect(await screen.findByText("Unsafe Auto-Resolution Rate")).toBeInTheDocument();
    expect(screen.getByText("0.00%")).toBeInTheDocument(); // the hero metric, sourced from the real safety-metrics API, never hardcoded
    expect(screen.getByText("Match Rate")).toBeInTheDocument();
  });

  it("shows N/A for the unsafe auto-resolution rate when no ground truth is available for the dataset, never a fabricated number", async () => {
    installFetchMock({
      "/runs/RUN-test0001/safety-metrics": { available: false, total: 0, graded: 0, false_auto_resolutions: 0, false_auto_resolution_rate: 0, match_rate: 0, reason_unavailable: "No ground_truth.json exists for this run's dataset." },
      "/runs/RUN-test0001": mockRunList.items[0],
      "/runs": mockRunList,
      "/exceptions/queue": mockQueue,
      "/exceptions": mockExceptionList,
    });

    render(
      <MemoryRouter>
        <RunProvider>
          <OverviewPage />
        </RunProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Unsafe Auto-Resolution Rate")).toBeInTheDocument();
    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(screen.getByText(/No ground_truth\.json exists/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs", async () => {
    installFetchMock({ "/runs": { items: [], total: 0 } });

    render(
      <MemoryRouter>
        <RunProvider>
          <OverviewPage />
        </RunProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("No reconciliation runs yet")).toBeInTheDocument();
  });
});
