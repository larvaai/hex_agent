/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Keep vitest to the unit/contract tier under src/. The Playwright browser specs in e2e/ are run
    // by `playwright test`, not vitest — without this, vitest's default *.spec glob grabs them.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
