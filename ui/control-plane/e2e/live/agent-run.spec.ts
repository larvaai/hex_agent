/**
 * L3 — the ONLY tier that drives a real agent run end-to-end through the browser (FLOW 1-2 live).
 * Real `python -m ui.ide` + real local 35B. Tagged @live, so `test:e2e` (--grep-invert @live) skips
 * it and the deterministic tier never needs the model.
 *
 * Content is non-deterministic, so every assertion is STRUCTURAL/SECURITY, never the model's text:
 * a successful fs_write tool step, an assistant bubble, a terminal `finished` status, and a diff row
 * proving the write hit disk. The prompt is the fixed one proven to drive exactly one fs_write.
 *
 * Approval + SIGTERM-reconnect were CUT after red-team (F4/F5): the runner has no live approval gate
 * (server.py:173-174) and a bounced server starts with an empty in-memory buffer — both → manual L4.
 */
import { test, expect } from "@playwright/test";

import { runtime, type Runtime } from "../_runtime";

const LLM_URL = (process.env.LLM_BASE_URL ?? "http://localhost:1234/v1").replace(/\/$/, "");
const LIVE = 120_000; // a real local run is slow — generous, content-agnostic polling

let rt: Runtime; // read lazily — global-setup writes .runtime.json just before tests run
test.beforeEach(() => {
  rt = runtime();
});

test.describe("L3 live full-stack (real ui.ide + real 35B)", () => {
  test("@live submit prompt → file written + events flow + diff appears", async ({ page }) => {
    // Fail-fast, NOT a silent green: the 35B must be up. This is the ONE allowed guarded skip.
    const reachable = await fetch(`${LLM_URL}/models`).then((r) => r.ok).catch(() => false);
    test.skip(
      !reachable,
      `local 35B unreachable at ${LLM_URL}/models — start LM Studio (TEXT-mode JSON) and set LLM_BASE_URL. See docs/testing/README.md.`,
    );

    await page.goto(rt.viteUrl);

    // submit the fixed prompt that reliably drives one fs_write
    await page.getByLabel("prompt").fill("create var/workspace/calc.py with add(a,b)");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.locator(".cp-ack")).toContainText(/received|rejected/); // sync ack

    // a successful fs_write tool step, folded into the chat thread (bridge.py:60-79)
    await expect(
      page.locator('.chat-tool[data-ok="true"] .chat-tool-name', { hasText: "fs_write" }),
    ).toBeVisible({ timeout: LIVE });

    // the turn closed with an assistant bubble and a terminal finished status (runner.py:175-182)
    await expect(page.locator(".chat-assistant")).toBeVisible({ timeout: LIVE });
    await expect(page.locator(".ide-runpill")).toHaveText("finished", { timeout: LIVE });

    // the write hit disk: a diff row appears against the run-start baseline
    await page.getByRole("button", { name: /Changes/ }).click();
    await expect(page.locator(".ide-diff-file").first()).toBeVisible({ timeout: LIVE });
  });
});
