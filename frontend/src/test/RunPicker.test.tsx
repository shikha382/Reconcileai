import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { RunPicker } from "../components/RunPicker";
import { RunProvider } from "../context/RunContext";
import { mockRun } from "./fixtures";

afterEach(() => localStorage.clear());

describe("RunPicker", () => {
  it("selects and persists the newest available run when no stored run is valid", async () => {
    localStorage.setItem("reconcileai.currentRunId", "RUN-no-longer-available");

    render(
      <MemoryRouter>
        <RunProvider>
          <RunPicker runs={[mockRun]} />
        </RunProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole("combobox")).toHaveValue(mockRun.run_id);
    await waitFor(() => expect(localStorage.getItem("reconcileai.currentRunId")).toBe(mockRun.run_id));
  });
});
