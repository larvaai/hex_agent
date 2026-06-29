/**
 * L2 — multi-session over the real backend (FLOW 9, HTTP-backed, no model). Clicking "New" hits
 * POST /api/sessions then GET /api/sessions and switches the store to the server-generated id; the
 * graph is not needed to assert this (it would need the model) — the session dropdown is.
 */
import { test, expect } from "@playwright/test";

import { runtime, type Runtime } from "./_runtime";

let rt: Runtime; // read lazily — global-setup writes .runtime.json just before tests run
test.beforeEach(() => {
  rt = runtime();
});

test("create session → dropdown updates + switches to it", async ({ page }) => {
  await page.goto(rt.viteUrl);

  const select = page.locator("select.ide-session-select");
  await expect(select).toBeVisible();
  await expect(select).toHaveValue(rt.session); // starts on the pinned default (t1_demo)
  const before = await select.locator("option").count();

  await page.getByRole("button", { name: "new session" }).click();

  // the store switched to a fresh server-generated session id (s_… per SessionRegistry.create)
  await expect(select).not.toHaveValue(rt.session);
  expect((await select.inputValue()).startsWith("s_")).toBeTruthy();
  // and the dropdown now lists more sessions than before (came from GET /api/sessions)
  expect(await select.locator("option").count()).toBeGreaterThan(before);
});
