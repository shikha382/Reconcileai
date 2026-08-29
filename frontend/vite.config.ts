import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

// M12: the frontend calls the backend API directly (no `/api` prefix --
// app.api.router mounts every route at the root, e.g. `/health`, `/runs`,
// `/exceptions`). In dev, requests are proxied to the FastAPI process so no
// CORS configuration is needed for local demo use; see docs/frontend.md.
const BACKEND_ORIGIN = "http://127.0.0.1:8000";

// M16, Phase 7 finding: `/health`, `/runs`, and `/exceptions` are proxied
// path PREFIXES, but the SPA ALSO has real client-side routes at those
// exact paths (System Health, Runs, Exceptions). A full page navigation
// (a bookmark, a manual refresh, or Playwright's page.goto) sends
// `Accept: text/html` and would otherwise be proxied straight to the
// backend, which returns raw JSON instead of the app shell -- a genuine,
// reproduced bug (confirmed via `curl -H "Accept: text/html" .../runs`
// returning `{"items":[],"total":0}` instead of HTML). `bypass` lets the
// dev server serve `index.html` for exactly this case, while every real
// `fetch()` call from already-loaded React code (which never sends an
// `Accept: text/html` header) still proxies through normally.
function apiProxy(): ProxyOptions {
  return {
    target: BACKEND_ORIGIN,
    bypass(req) {
      if (req.headers.accept?.includes("text/html")) {
        return "/index.html";
      }
    },
  };
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": apiProxy(),
      "/runs": apiProxy(),
      "/exceptions": apiProxy(),
      "/sources": apiProxy(),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    // M16: `e2e/` holds Playwright specs (a different test runner/API,
    // `frontend/playwright.config.ts`, run via `npm run test:e2e`) -- exclude
    // it here so Vitest's own `npm test` never tries to execute them.
    exclude: ["**/node_modules/**", "**/e2e/**"],
  },
} as any);
