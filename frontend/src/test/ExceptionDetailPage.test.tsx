import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExceptionDetailPage } from "../pages/ExceptionDetailPage";
import { installFetchMock, mockExceptionDetail, mockExplanation, mockProvenance } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/exceptions/EXC-p0-critical"]}>
      <Routes>
        <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ExceptionDetailPage", () => {
  it("loads the detail, explanation, and provenance responses and renders the contradiction prominently", async () => {
    installFetchMock({
      "/exceptions/EXC-p0-critical/explanation": mockExplanation,
      "/exceptions/EXC-p0-critical/provenance": mockProvenance,
      "/exceptions/EXC-p0-critical": mockExceptionDetail,
    });

    renderDetail();

    await waitFor(() => expect(screen.getByText("Why This Exception Is Prioritized")).toBeInTheDocument());

    // AI investigation is shown as an investigation, never as "AI decided" (Phase 10).
    expect(screen.getByText("AI Investigation")).toBeInTheDocument();
    expect(screen.queryByText(/AI decided/i)).not.toBeInTheDocument();

    // The contradiction is a dedicated, visible callout, not buried text.
    expect(screen.getAllByText(/CONTRADICTION DETECTED/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Actual fee-rule calculation does not explain the residual/).length).toBeGreaterThan(0);

    // Provenance timeline renders real events.
    expect(screen.getByText("Audit & Provenance")).toBeInTheDocument();
    expect(screen.getByText("Ai Investigation")).toBeInTheDocument(); // timeline entry, title-cased

    // Final decision is visible and unambiguous.
    expect(screen.getByText("Final Decision")).toBeInTheDocument();
  });

  it("never renders a financial mutation control", async () => {
    installFetchMock({
      "/exceptions/EXC-p0-critical/explanation": mockExplanation,
      "/exceptions/EXC-p0-critical/provenance": mockProvenance,
      "/exceptions/EXC-p0-critical": mockExceptionDetail,
    });

    renderDetail();
    await waitFor(() => expect(screen.getByText("Final Decision")).toBeInTheDocument());

    const forbidden = /force.resolve|force.approve|override policy|approve|refund|payout|mark.reconciled/i;
    for (const button of screen.queryAllByRole("button")) {
      expect(button.textContent ?? "").not.toMatch(forbidden);
    }
  });
});
