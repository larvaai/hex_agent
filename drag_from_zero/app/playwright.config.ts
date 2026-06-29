import { defineConfig } from "@playwright/test";

// Thin smoke over the real DOM canvas, served by the production chain:
// `python ../run_server.py --ui-dir dist` on :8000 (built app, no Vite proxy = source of truth).
// NOT part of the Python `browser` marker / CI (DEC-12 role-split) — author->run is already
// covered by tests/e2e/test_topology_to_server.py; this only proves the React canvas mounts.
export default defineConfig({
  testDir: "./src/e2e",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:8000", headless: true },
  webServer: {
    command: "python3 ../run_server.py --ui-dir dist --port 8000 --pace 0",
    url: "http://127.0.0.1:8000/api/session",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
