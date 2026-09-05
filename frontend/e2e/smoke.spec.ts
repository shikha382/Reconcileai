import { test, expect } from "@playwright/test";

// Milestone 16, Phase 6: the 14-step judge journey smoke test, against the
// REAL running backend (uvicorn) and REAL running frontend (vite dev
// server) -- no mocked fetch anywhere in this file. Requires both servers
// already running (see docs/final-validation.md). This exercises real
// application code end-to-end in a real browser; it is not a substitute
// for the Vitest component suite, and is deliberately small (one file, one
// linear journey) rather than a large E2E framework.

test("the 14-step judge demo journey works end-to-end in a real browser", async ({ page }) => {
  // 1. Start a real run so Overview has real data to show.
  await page.goto("/runs");
  await page.getByRole("button", { name: "Start reconciliation" }).click();
  await expect(page.getByRole("table")).toBeVisible({ timeout: 20_000 });

  // 2. Open Overview.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  // 3. Confirm DEMO · SYNTHETIC DATA badge.
  await expect(page.getByText("DEMO · SYNTHETIC DATA")).toBeVisible();

  // 4. Confirm the safety metric (hero card) is present with a real value.
  await expect(page.getByText("Unsafe Auto-Resolution Rate")).toBeVisible({ timeout: 15_000 });

  // 5. Open Work Queue.
  await page.getByRole("link", { name: "Work Queue" }).click();
  await expect(page.getByRole("heading", { name: "Work Queue" })).toBeVisible();

  // 6. Select the top (P0 or otherwise top-priority) exception.
  await page.waitForSelector("table tbody tr");
  const firstRowLink = page.locator("table tbody tr").first().getByRole("link");
  await firstRowLink.click();

  // 7. Exception Detail loaded.
  await expect(page.getByText("Financial Summary")).toBeVisible({ timeout: 15_000 });

  // 8. AI Investigation section is present (structurally, even if this
  // particular exception needed no AI investigation -- the section itself
  // always renders).
  await expect(page.getByRole("heading", { name: "AI Investigation" })).toBeVisible();

  // 9/10/11. Policy, Final Decision, and Audit sections are present.
  await expect(page.getByRole("heading", { name: "Policy", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Final Decision" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Audit & Provenance" })).toBeVisible();

  // 12. Open Audit page.
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: "Audit Trail", exact: true })).toBeVisible();

  // 13. Open About and confirm the competitive baseline numbers.
  await page.goto("/about");
  await expect(page.getByText("0.0000% unsafe auto-resolution rate")).toBeVisible();
  await expect(page.getByText("14.67% unsafe auto-resolution rate")).toBeVisible();

  // 14. Confirm no mutation-shaped action exists anywhere on this page.
  const buttons = await page.getByRole("button").all();
  for (const button of buttons) {
    const text = (await button.textContent())?.toLowerCase() ?? "";
    expect(text).not.toMatch(/force.?resolve|force.?approve|override|delete|mutate/);
  }
});

test("the synthetic ₹9.83 fee trap is rejected by policy with no financial action", async ({ page }) => {
  await page.goto("/runs");
  await page.getByRole("button", { name: "Start reconciliation" }).click();
  await expect(page.getByRole("table")).toBeVisible({ timeout: 20_000 });

  await page.goto("/work-queue");
  await page.getByLabel("Decision").selectOption("REJECTED");
  const blockedFeeRow = page.locator("tbody tr").filter({ hasText: "Fee Mismatch" }).first();
  await expect(blockedFeeRow).toBeVisible({ timeout: 15_000 });
  await blockedFeeRow.getByRole("link").click();

  await expect(page.getByText("Unexplained Residual", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("₹9.83", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/actively disproven by deterministic verification/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Final Decision" })).toBeVisible();
  await expect(page.locator(".decision-flow__final")).toContainText("Blocked");
  await expect(page.getByText(/Review .*state/i)).toHaveCount(0);
});
