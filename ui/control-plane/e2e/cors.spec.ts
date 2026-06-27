/**
 * L2 — the real-backend CORS gate, enforced by the browser. A cross-origin POST from the Vite origin
 * to the backend origin, carrying the custom X-Auth-Token header, triggers a preflight (OPTIONS).
 * The browser only lets the real POST through if the backend reflected the localhost origin
 * (server.py:188-193). If CORS were missing, fetch() would reject and page.evaluate would throw.
 *
 * The REJECT case (a non-localhost Origin) is an L1 test (server.py:55-56) — a browser can't forge an
 * arbitrary Origin, so it can only be proven in-process.
 */
import { test, expect } from "@playwright/test";

import { runtime, type Runtime } from "./_runtime";

let rt: Runtime; // read lazily — global-setup writes .runtime.json just before tests run
test.beforeEach(() => {
  rt = runtime();
});

test("preflight from the Vite origin succeeds against the real backend", async ({ page }) => {
  await page.goto(rt.viteUrl); // origin is now the Vite dev server (a localhost origin)

  const status = await page.evaluate(
    async ({ backend, token }) => {
      const res = await fetch(`${backend}/api/files/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Auth-Token": token },
        body: JSON.stringify({ scope: "workspace", path: "cors_probe.txt", kind: "file" }),
      });
      return res.status; // reaching here at all means the preflight + request were allowed
    },
    { backend: rt.backendUrl, token: rt.token },
  );

  expect([200, 409]).toContain(status); // created, or already-exists on a re-run — both prove CORS passed
});
