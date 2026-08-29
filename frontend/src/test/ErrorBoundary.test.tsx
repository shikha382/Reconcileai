import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { RunProvider } from "../context/RunContext";
import { RunsPage } from "../pages/RunsPage";
import { installFetchMock } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("malformed backend response handling", () => {
  it("shows a graceful fallback instead of a raw crash when a response is missing expected fields", async () => {
    // Deliberately malformed: no `items` field at all.
    installFetchMock({ "/runs": { total: 0 } });
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <MemoryRouter>
        <RunProvider>
          <ErrorBoundary>
            <RunsPage />
          </ErrorBoundary>
        </RunProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Something went wrong displaying this page")).toBeInTheDocument();
    expect(screen.queryByText(/TypeError/)).not.toBeInTheDocument();
    expect(screen.queryByText(/at RunsPage/)).not.toBeInTheDocument();
  });
});
