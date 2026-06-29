---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 5 — Playwright browser E2E (opt-in, marker=browser)

**Goal:** drive the **real** `ui/Agent IDE.dc.html` in headless Chromium against the real
server, proving the UI the README claims works actually boots, runs, and renders. Opt-in:
excluded from the default suite; skips cleanly when playwright/chromium absent.

## Prerequisites (documented in MANUAL_TESTING.md + phase report)

```bash
pip install -e ".[test-browser]"   # playwright + pytest-playwright
python -m playwright install chromium
pytest tests/e2e_browser -m browser -q
```

## UI contract (grounded from ui/Agent IDE.dc.html)

- Framework: custom DC (`<x-dc>`, `script[data-dc-script]`, `sc-for`, `{{ }}`); single local
  script `./support.js`; only external = Google Fonts (cosmetic → tests must not depend on it).
- Endpoints the UI calls: `GET /api/session`, `POST /api/runs/{id}/reset`,
  `POST /api/runs/{id}/start`, `GET /api/runs/{id}/artifacts`, `…/artifact?path=`,
  `WS /api/runs/{id}/events`.
- Stable assertion anchors (rendered TEXT, not ids — ids are dynamic/SVG):
  - Run button: a `<button>` with the play-triangle SVG + label `{{ runBtnLabel }}` (handler
    `runDemo`). Reset button text "Reset". Send button text "Send". Tabs: titles
    "Workspace — files & code" / "Agents — orchestration graph".
  - chat narration strings (from `applyEvent`): `"routing the goal"`,
    `"reduced — children done"` / `"passed"`, `"run finished · "` + status + `" steps"`,
    `"too big → decomposed into"`, `"blocked · "`.
  - file chip: `sc-for list="{{ chips }}"`, each `title="open <name>"`.
- Set the `reduceMotion` prop true (data-props) when serving for tests → animations off.

## Target files

- `tests/e2e_browser/conftest.py` — `pytest.importorskip("playwright.sync_api")`; a fixture
  that `make_server(run_from_topology, static_dir="ui", port=0)` on a thread and yields the
  base URL; the `Run.pace` set low-but-nonzero so frames animate but tests stay fast.
- `tests/e2e_browser/test_agent_ide_ui.py` (all `@pytest.mark.browser`):
  1. **boot (settles U1/U2):** `page.goto(base)`; assert no uncaught console error
     (`page.on("console", …)` / `pageerror`); the graph root node label is visible; the
     `/api/session` graph rendered (root node present). *If this fails, the UI cannot render
     headless → STOP and convert browser coverage to manual-only (see fallback).* 
  2. **run:** click the Run button (by play-icon/label) → wait for chat text
     `"run finished · done"`; assert intermediate chat shows `"routing the goal"` and a
     pass/`"reduced — children done"`; assert ≥2 nodes drawn in the graph.
  3. **artifact chip:** switch to the Workspace tab → a file chip (`title^="open "`) appears →
     click it → the artifact content the agent wrote is shown in the editor pane.
  4. **reset:** click Reset → status returns to created/idle, graph reflects the seeded root.
- Waits anchor on `expect(locator).to_be_visible()` / `to_have_text` with timeout — **no
  `sleep`** as a sync primitive.

## Fallback (decision point, per red-team #4)

If step 1 proves the DC UI cannot render under headless Chromium offline, do NOT sink time
into hacks: mark the browser scenarios `xfail(reason=...)` OR move them verbatim into
MANUAL_TESTING.md as a human checklist, and record the decision in the phase report + a DEC.
The deterministic over-wire E2E (phase 4) already covers the server contract the UI depends on.

## TDD framing

- **Red proof:** temporarily point the server at a broken index (empty html) → boot test
  fails (proves it asserts real render, not just HTTP 200). Restore.
- **Green gate:** `pytest -m browser -q` green locally with chromium; `pytest -q` (default)
  still does NOT collect/run these.

## Acceptance

- [ ] browser tests skip cleanly when playwright missing (importorskip), never error the suite.
- [ ] boot + run + artifact-chip + reset scenarios present and green with chromium installed.
- [ ] assertions anchor on rendered text/locators, reduceMotion on, zero bare sleeps.
- [ ] default `pytest -q` unaffected (browser excluded).
- [ ] U1/U2 resolved in the phase report (renders offline? support.js ok?) — or fallback taken.
