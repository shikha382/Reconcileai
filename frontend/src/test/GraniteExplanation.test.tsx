import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GraniteExplanation } from "../components/GraniteExplanation";
import { api } from "../api/client";

vi.mock("../api/client", () => ({ api: { graniteStatus: vi.fn(), explainWithGranite: vi.fn() } }));
afterEach(() => vi.resetAllMocks());
const health = { available: true, model: "granite4:3b", reason: null };
const answer = { explanation: "The existing decision requires review.", model: "granite4:3b",
  source: "granite" as const, elapsed_ms: 100, snapshot_fingerprint: "abc", fact_ids: ["decision"], fallback_reason: null };

describe("local Granite panel", () => {
  it("does not generate automatically; renders a requested explanation as text", async () => {
    vi.mocked(api.graniteStatus).mockResolvedValue(health);
    vi.mocked(api.explainWithGranite).mockResolvedValue(answer);
    render(<GraniteExplanation exceptionId="one" />);
    const button = await screen.findByRole("button", { name: "Explain this exception" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(api.explainWithGranite).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(await screen.findByText(answer.explanation)).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("labels deterministic fallbacks", async () => {
    vi.mocked(api.graniteStatus).mockResolvedValue(health);
    vi.mocked(api.explainWithGranite).mockResolvedValue({ ...answer, source: "deterministic_fallback" });
    render(<GraniteExplanation exceptionId="one" />);
    await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByText("Deterministic fallback — not an AI answer")).toBeInTheDocument();
  });

  it("allows retry after model unavailable", async () => {
    vi.mocked(api.graniteStatus).mockResolvedValue({ ...health, available: false, reason: "Start Ollama" });
    render(<GraniteExplanation exceptionId="one" />);
    expect(await screen.findByText("Start Ollama")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry explanation" })).toBeEnabled();
  });

  it("cancels and ignores a late result", async () => {
    vi.mocked(api.graniteStatus).mockResolvedValue(health);
    let resolve!: (value: typeof answer) => void;
    vi.mocked(api.explainWithGranite).mockImplementation(() => new Promise(r => { resolve = r; }));
    render(<GraniteExplanation exceptionId="one" />);
    await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(api.explainWithGranite).toHaveBeenCalled());
    const signal = vi.mocked(api.explainWithGranite).mock.calls[0][1];
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(signal.aborted).toBe(true);
    await act(async () => resolve(answer));
    expect(screen.queryByText(answer.explanation)).not.toBeInTheDocument();
    expect(screen.getByText("Explanation cancelled.")).toBeInTheDocument();
  });

  it("clears on keyed navigation and aborts old requests", async () => {
    vi.mocked(api.graniteStatus).mockResolvedValue(health);
    vi.mocked(api.explainWithGranite).mockResolvedValue(answer);
    const { rerender } = render(<GraniteExplanation key="one" exceptionId="one" />);
    await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    await screen.findByText(answer.explanation);
    const signal = vi.mocked(api.explainWithGranite).mock.calls[0][1];
    rerender(<GraniteExplanation key="two" exceptionId="two" />);
    expect(signal.aborted).toBe(true);
    expect(screen.queryByText(answer.explanation)).not.toBeInTheDocument();
  });
});
