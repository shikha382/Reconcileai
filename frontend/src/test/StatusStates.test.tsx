import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";
import { ApiError } from "../api/client";

describe("shared state components", () => {
  it("renders a loading state with an accessible status role", () => {
    render(<LoadingState label="Loading exceptions" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading exceptions");
  });

  it("renders an empty state with a title and optional hint", () => {
    render(<EmptyState title="No exceptions match these filters" hint="Try widening your filters." />);
    expect(screen.getByText("No exceptions match these filters")).toBeInTheDocument();
    expect(screen.getByText("Try widening your filters.")).toBeInTheDocument();
  });

  it("renders a structured API error without a stack trace", () => {
    const error = new ApiError("Exception was not found.", "EXCEPTION_NOT_FOUND", 404, "REQ-abc123");
    render(<ErrorState error={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Exception was not found.");
    expect(screen.getByText(/EXCEPTION_NOT_FOUND/)).toBeInTheDocument();
    expect(screen.getByText(/REQ-abc123/)).toBeInTheDocument();
  });

  it("offers a retry action when provided", () => {
    let retried = false;
    const error = new ApiError("Network error.", "NETWORK_ERROR", 0, null);
    render(<ErrorState error={error} onRetry={() => (retried = true)} />);
    screen.getByRole("button", { name: "Try again" }).click();
    expect(retried).toBe(true);
  });
});
