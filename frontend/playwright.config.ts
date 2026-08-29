import { defineConfig } from "@playwright/test";

// Milestone 16, Phase 6: a minimal, deterministic browser smoke suite --
// NOT a large E2E framework. Assumes the real backend (uvicorn) and the
// real frontend dev server are already running (see docs/final-validation.md
// for the exact commands) -- this config does not start them itself, since
// the backend requires a real Python process this tool cannot manage.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    screenshot: "only-on-failure",
  },
});
