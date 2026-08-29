import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunProvider } from "../context/RunContext";
import { WorkQueuePage } from "../pages/WorkQueuePage";
import { installFetchMock, mockQueue, mockRunList } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("WorkQueuePage", () => {
  it("renders the queue in the exact order the backend returned, with reason codes and recommended action", async () => {
    installFetchMock({ "/runs": mockRunList, "/exceptions/queue": mockQueue });

    render(
      <MemoryRouter>
        <RunProvider>
          <WorkQueuePage />
        </RunProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getAllByRole("row").length).toBeGreaterThan(1));

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows).toHaveLength(2);
    // Backend order was [P0 critical, P3 clean] -- the frontend must not re-sort.
    expect(within(rows[0]).getByText("EXC-p0-critical")).toBeInTheDocument();
    expect(within(rows[1]).getByText("EXC-p3-clean")).toBeInTheDocument();

    expect(within(rows[0]).getByText("Critical Risk")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Sla Breached")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Contradictory Evidence")).toBeInTheDocument();
  });

  it("visually distinguishes P0 rows without relying on color alone (the priority badge text is present too)", async () => {
    installFetchMock({ "/runs": mockRunList, "/exceptions/queue": mockQueue });

    render(
      <MemoryRouter>
        <RunProvider>
          <WorkQueuePage />
        </RunProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getAllByRole("row").length).toBeGreaterThan(1));
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].className).toContain("data-table__row--p0");
    expect(within(rows[0]).getByText("P0")).toBeInTheDocument();
    expect(rows[1].className).not.toContain("data-table__row--p0");
  });

  it("shows an empty state when a filter matches nothing", async () => {
    installFetchMock({
      "/runs": mockRunList,
      "/exceptions/queue": { items: [], summary: { total: 0, counts_by_priority: {}, total_financial_exposure: "0.00", sla_breached_count: 0, sla_at_risk_count: 0, highest_exposure_exception_id: null, most_common_category: null }, page: 1, page_size: 25, total: 0 },
    });

    render(
      <MemoryRouter>
        <RunProvider>
          <WorkQueuePage />
        </RunProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("No exceptions match these filters")).toBeInTheDocument();
  });
});
