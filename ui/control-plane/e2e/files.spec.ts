/**
 * L2 — the IDE file loop against the REAL backend, NO model (FLOW 7, runner-free).
 * tree → open → edit → save → diff. The fake-vs-real discriminator (F-gate): the real backend
 * PERSISTS to disk — every save is checked by an os-level read of the temp workspace AND a fresh
 * GET /api/files/read, not just the DOM. A fixture server would not produce the on-disk file.
 */
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

import { runtime, type Runtime } from "./_runtime";

const MARKER = "E2E_EDIT_MARKER_42";
// Read the runtime descriptor lazily (not at import time): global-setup writes it just before tests
// run, so a top-level read would crash collection / `--list` when the file isn't there yet.
let rt: Runtime;
test.beforeEach(() => {
  rt = runtime();
});

test.describe("IDE file loop (real ui.ide, no model)", () => {
  test("tree → open → edit → save → diff, persisted to disk", async ({ page }) => {
    await page.goto(rt.viteUrl);

    // tree renders the seeded workspace file
    const fileRow = page.locator(".ide-tree-file", { hasText: "e2e_target.py" });
    await expect(fileRow).toBeVisible();

    // open → editor tab + seed content
    await fileRow.click();
    await expect(page.locator(".ide-tab-name", { hasText: "e2e_target.py" })).toBeVisible();
    await expect(page.locator(".cm-content")).toContainText("def add");

    // edit: select-all inside CodeMirror, replace with a single marker line
    await page.locator(".cm-content").click();
    await page.keyboard.press("Meta+a");
    await page.keyboard.type(`${MARKER} = 1`);

    // dirty pill on the active tab + Save enabled
    await expect(page.locator(".ide-tab.is-active .ide-tab-name")).toContainText("●");
    const save = page.locator(".ide-save");
    await expect(save).toBeEnabled();

    // save via Cmd/Ctrl+S → dirty clears, Save disables
    await page.keyboard.press("Meta+s");
    await expect(page.locator(".ide-tab.is-active .ide-tab-name")).not.toContainText("●");
    await expect(save).toBeDisabled();

    // DISCRIMINATOR 1: the change is on disk in the real workspace
    const onDisk = readFileSync(path.join(rt.workspaceDir, "e2e_target.py"), "utf-8");
    expect(onDisk).toContain(MARKER);
    // DISCRIMINATOR 2: a fresh backend read returns it (not a cached DOM value)
    const read = await page.request.get(
      `${rt.backendUrl}/api/files/read?scope=workspace&path=e2e_target.py`,
      { headers: { "X-Auth-Token": rt.token } },
    );
    expect((await read.json()).content).toContain(MARKER);

    // diff tab shows a row for the file, with the marker as an added line
    await page.getByRole("button", { name: /Changes/ }).click();
    const diffFile = page.locator(".ide-diff-file", { hasText: "e2e_target.py" });
    await expect(diffFile).toBeVisible();
    await expect(diffFile.locator(".ide-diff-add", { hasText: MARKER })).toBeVisible();
  });

  test("sensitive file is listed but not openable", async ({ page }) => {
    await page.goto(rt.viteUrl);
    const envRow = page.locator(".ide-tree-file", { hasText: ".env" });
    await expect(envRow).toBeVisible();
    await envRow.click();
    // openFile's error surfaces in the explorer status; no editor tab is opened for .env
    await expect(page.locator(".ide-explorer-status")).toContainText(/sensitive/i);
    await expect(page.locator(".ide-tab-name", { hasText: ".env" })).toHaveCount(0);
  });
});
