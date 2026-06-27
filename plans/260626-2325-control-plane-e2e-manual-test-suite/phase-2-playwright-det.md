---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — L2 Playwright harness + deterministic browser E2E (real ui.ide, NO model)

**Goal:** real browser (Playwright) driving the real React UI against a real `python -m ui.ide` —
asserting ONLY the flows with a real HTTP surface (file-API, CORS, session-create). Establishes the harness (DEC-T1).

> **Trimmed after red-team (F1).** Graph/timeline/chat/redaction/reconnect are NOT browser-assertable without
> the model (they fold `loop.*` events that have no HTTP seed route — `snapshot.py:3-9`). The only model-free
> node is the hardcoded root "O" (`AgentGraph.tsx:65`), which proves nothing. Those assertions live at L1
> (in-process) and L3 (@live). L2 asserts only what the browser can really drive over HTTP.

## New tooling (DEC-T1 — first Playwright in repo)
- devDep `@playwright/test`; `npx playwright install chromium` (document in README — NOT in current CI, DEC-T5).
- `ui/control-plane/package.json` scripts: `"test:e2e": "playwright test --grep-invert @live"`.
- `ui/control-plane/playwright.config.ts` — `use.screenshot:'only-on-failure'`; `webServer` runs Vite.

## Files
`ui/control-plane/playwright.config.ts` · `e2e/global-setup.ts` · `e2e/global-teardown.ts` ·
`e2e/files.spec.ts` · `e2e/sessions.spec.ts` · `e2e/cors.spec.ts`

## global-setup.ts (F9 — no port race, no process leak)
1. Pick an ephemeral port; spawn `python -m ui.ide --host 127.0.0.1 --port <p> --token e2e-token --session e2e`
   (server.py:463) in a temp workspace dir, **as a process group**.
2. **Readiness poll** GET `/api/snapshot` until 200 (cap ~10s) BEFORE exporting env — no fixed sleep.
3. Export `VITE_CP_BASE_URL=http://127.0.0.1:<p>` + `VITE_CP_TOKEN=e2e-token` (config.ts:3-4); Vite (via
   Playwright `webServer`) then serves a UI pointed at the real backend.
4. Teardown kills the **process group** (not just the handle) + rms the temp workspace.

## Tests Before (red) → specs → assertions (all model-free, all HTTP-backed)

### files.spec.ts — the IDE file loop (FLOW 7, runner-free)
- `file tree → open → edit → save → diff` — **baseline ordering matters (F3):** seed a `.py` via PUT
  `/api/files/write`, THEN create a fresh session via POST `/api/sessions` (so its baseline excludes the seed).
  In browser: expand tree, click file (FileExplorer.tsx:49), edit in CodeEditor, Cmd/Ctrl+S, switch to Diff,
  assert a diff row with `+`/`−` for the edit (DiffPanel.tsx:43). Assert dirty-pill before save, cleared after.
- `sensitive file not openable` — seed `.env`; tree shows it, open → error surfaced, no content (files.py:117-123).

### sessions.spec.ts — multi-session (FLOW 9, HTTP-backed)
- `create session → dropdown updates → file explorer resets` — click New (SessionBar.tsx:13), assert dropdown
  gains it and the file tree re-points to the new session's scope (store reset is observable via the explorer,
  not the graph — graph needs no reset to assert here).

### cors.spec.ts — real-backend CORS gate
- `preflight from the Vite origin succeeds` — cross-origin POST from the Vite origin returns after a 204
  preflight, proving the real backend allows the localhost UI origin (server.py:188-193). (The reject case for a
  non-localhost origin is an L1 test — server.py:55-56 — since a browser can't forge an arbitrary Origin.)

## "Is the test real?" gate (F-gate, sharpened)
- **Fake-vs-real discriminator (named):** the real backend PERSISTS to disk; assert each save by a fresh GET
  `/api/files/read` and by `os`-level file existence in the temp workspace — not just the DOM. A fake/fixture
  server would not produce the on-disk file. This is the concrete tell, not "looks real".
- Each spec must fail if the file isn't actually written (delete the write call → red). Screenshot on failure.

## Regression Gate
`npm --prefix ui/control-plane test` (vitest) untouched + green. `npm --prefix ui/control-plane run test:e2e`
green with NO model running. README states: needs `playwright install chromium`; NOT in current CI (DEC-T5).
