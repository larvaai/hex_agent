import { test, expect } from "@playwright/test";

// Smoke: author 2 agents + an edge, Run, see the execution tree appear with a verdict. The
// backend author->run path is already covered in pytest; this only proves the React canvas
// mounts, serializes, and renders the live stream without console errors.
test("author -> run -> live execution tree", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto("/");
  await expect(page.getByLabel("palette")).toBeVisible();

  // add a planner (first agent auto-becomes entry) and a coder
  await page.getByTestId("palette-agent").click();
  await page.getByTestId("palette-agent").click();

  // connect them by dragging from the first node's source handle to the second's target handle
  const handles = page.locator(".react-flow__handle-right");
  const targets = page.locator(".react-flow__handle-left");
  await handles.first().dragTo(targets.nth(1));

  await page.getByTestId("run-btn").click();

  // the tree streams in: a root node, then a verdict chip, within the run timeout
  await expect(page.getByTestId("run-status")).toHaveText(/running|done|awaiting/, { timeout: 15_000 });
  await expect(page.locator(".tree-node").first()).toBeVisible({ timeout: 15_000 });

  expect(errors, errors.join("\n")).toHaveLength(0);
});
