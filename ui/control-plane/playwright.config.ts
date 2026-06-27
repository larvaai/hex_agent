/**
 * Playwright config — L2 deterministic browser E2E (DEC-T1). Drives the REAL `python -m ui.ide`
 * backend + a real Vite dev UI, no model. Both servers are spawned in global-setup (ephemeral ports,
 * process groups — F9) rather than via Playwright's `webServer`, because the backend port is chosen
 * at setup time and has to be injected into Vite's env before Vite boots.
 *
 * `test:e2e` runs `--grep-invert @live`, so the live agent-run spec (Phase 3) is excluded here and
 * this tier never needs the 35B. NOT in current CI (no Node job — DEC-T5); a local pre-merge gate.
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  workers: 1, // one real backend + workspace on disk → serialise
  forbidOnly: !!process.env.CI,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: [["list"]],
  use: {
    screenshot: "only-on-failure",
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
