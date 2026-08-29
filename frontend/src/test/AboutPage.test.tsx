import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AboutPage } from "../pages/AboutPage";

describe("AboutPage", () => {
  it("renders the AI-authority diagram and the cited M13 competitive numbers, with no live API call", () => {
    render(
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("AI Proposes. Policy Decides. Audit Remembers.")).toBeInTheDocument();
    expect(screen.getByText("INVESTIGATES")).toBeInTheDocument();
    expect(screen.getByText("DECIDES")).toBeInTheDocument();

    // The cited, historical M13 evaluation numbers -- static content, not a live metric.
    expect(screen.getByText("14.67% unsafe auto-resolution rate")).toBeInTheDocument();
    expect(screen.getByText("0.0000% unsafe auto-resolution rate")).toBeInTheDocument();

    expect(screen.getByText("Security")).toBeInTheDocument();
    expect(screen.getByText(/No financial mutation endpoint exists/)).toBeInTheDocument();
  });

  it("never renders a mutation control", () => {
    render(
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>,
    );
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
