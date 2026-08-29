import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunProvider } from "../context/RunContext";
import { RunsPage } from "../pages/RunsPage";
import { installErrorFetchMock, installFetchMock, mockRunList } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("RunsPage", () => {
  it("renders the runs table from the real API response", async () => {
    installFetchMock({ "/runs": mockRunList });

    render(
      <MemoryRouter>
        <RunProvider>
          <RunsPage />
        </RunProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("RUN-test0001")).toBeInTheDocument());
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start reconciliation" })).toBeInTheDocument();
  });

  it("renders a structured error, not a stack trace, when the API is unavailable", async () => {
    installErrorFetchMock(503, "SERVICE_UNAVAILABLE", "The reconciliation API is temporarily unavailable.");

    render(
      <MemoryRouter>
        <RunProvider>
          <RunsPage />
        </RunProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText(/temporarily unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/site-packages/i)).not.toBeInTheDocument();
  });

  it("renders a 403 (unauthorized) response as a clear error, not a crash", async () => {
    installErrorFetchMock(403, "FORBIDDEN", "The caller is not authorized to perform this action.");

    render(
      <MemoryRouter>
        <RunProvider>
          <RunsPage />
        </RunProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/not authorized/)).toBeInTheDocument();
  });
});
