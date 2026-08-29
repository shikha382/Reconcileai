import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HealthPage } from "../pages/HealthPage";
import { installFetchMock, mockSourcesStatus } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("HealthPage", () => {
  it("renders health status and the real data-sources table", async () => {
    installFetchMock({ "/health": { status: "ok", service: "reconcileai" }, "/sources/status": mockSourcesStatus });

    render(
      <MemoryRouter>
        <HealthPage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("OK")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    expect(screen.getByText("Data Sources")).toBeInTheDocument();
    expect(screen.getByText("Synthetic Fixture")).toBeInTheDocument();
    expect(screen.getByText("Razorpay Adapter")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getAllByText("SYNTHETIC DATA").length).toBe(4);
  });

  it("never renders a LIVE READ-ONLY badge when the backend reports fixture mode", async () => {
    installFetchMock({ "/health": { status: "ok", service: "reconcileai" }, "/sources/status": mockSourcesStatus });

    render(
      <MemoryRouter>
        <HealthPage />
      </MemoryRouter>,
    );

    // Wait for the sources TABLE itself (not just the always-present "Data
    // Sources" heading, which renders during the loading state too) --
    // otherwise this assertion can race ahead of the fetch resolving.
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    // The page's own disclaimer sentence legitimately contains the words
    // "LIVE READ-ONLY" as prose -- what must NOT exist is a status BADGE
    // showing it for any source, since every mocked source is fixture-mode.
    const table = screen.getByRole("table");
    expect(table.textContent).not.toContain("LIVE READ-ONLY");
  });
});
