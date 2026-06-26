import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev proxies /api (REST) and the WS event stream to the stdlib server on :8000.
// Prod build → dist/, which `python run_server.py --ui-dir app/dist` serves directly.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, ws: true },
    },
  },
  test: {
    environment: "node", // serialize/status are pure modules — no DOM
    include: ["src/**/*.test.ts"],
  },
});
