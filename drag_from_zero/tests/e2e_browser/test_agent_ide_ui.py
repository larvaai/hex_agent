"""Phase 5 — drive the REAL Agent-IDE UI in headless Chromium against the real server.

Opt-in (marker=browser, deselected by default). Skips cleanly when playwright is absent.
Assertions anchor on rendered TEXT (the chat narration strings the UI emits in `applyEvent`)
and button labels — not on dynamic/SVG ids. The first test settles U1/U2: can the custom DC
framework render headless + offline at all? If boot fails, that's the signal to fall back to
browser-as-manual (see plan phase-5 fallback).
"""
import re

import pytest

# NOTE: no top-level playwright import — the module must collect cleanly without it so the
# default suite DESELECTS these (0 skip noise). The root conftest skip-marks `browser` items
# when playwright is absent, so `pytest -m browser` skips cleanly; `expect` is imported lazily.
pytestmark = pytest.mark.browser


def _goto(page):
    page.goto(page.dz_base, wait_until="networkidle")


# 1 — boot: the DC UI renders, talks to /api/session, no uncaught JS errors (settles U1/U2).
def test_ui_boots_and_renders(page):
    from playwright.sync_api import expect

    _goto(page)
    # the Run button proves the component mounted (it reads runBtnLabel from state)
    expect(page.get_by_role("button", name=re.compile("run", re.I)).first).to_be_visible(timeout=10_000)
    # the seeded root task title is rendered somewhere in the graph/spec panel
    expect(page.get_by_text(re.compile("auth", re.I)).first).to_be_visible(timeout=10_000)
    assert page.dz_errors == [], f"uncaught JS errors on boot: {page.dz_errors}"


# 2 — run: clicking Run streams the tree live and narrates translated verdicts in chat.
def test_run_decomposes_and_finishes(page):
    from playwright.sync_api import expect

    _goto(page)
    page.get_by_role("button", name=re.compile("^run", re.I)).first.click()
    # the orchestrator narration the UI prints on run_start / run_end
    expect(page.get_by_text("routing the goal").first).to_be_visible(timeout=15_000)
    expect(page.get_by_text(re.compile("run finished")).first).to_be_visible(timeout=30_000)
    # the tree grew past the root (decompose narration appears for a delegated parent)
    expect(page.get_by_text(re.compile("decomposed into")).first).to_be_visible(timeout=30_000)
    assert page.dz_errors == [], f"uncaught JS errors during run: {page.dz_errors}"


# 3 — artifacts: a file the agent wrote opens and shows its real content.
def test_artifact_chip_opens_written_file(page):
    from playwright.sync_api import expect

    _goto(page)
    page.get_by_role("button", name=re.compile("^run", re.I)).first.click()
    expect(page.get_by_text(re.compile("run finished")).first).to_be_visible(timeout=30_000)
    # switch to the files/Workspace tab and open report.md (written by the demo's tester).
    page.locator('[title^="Workspace"]').first.click()
    report = page.get_by_text("report.md", exact=True)
    expect(report).to_be_visible(timeout=15_000)
    report.click()
    # the editor shows REAL file content — "86%" is unique to what the tester wrote, not a node
    # goal (goals only mention "coverage"), so this proves the artifact actually opened.
    expect(page.get_by_text(re.compile(r"86%")).first).to_be_visible(timeout=15_000)


# 4 — reset: returns the run to a fresh, idle state.
def test_reset_returns_to_idle(page):
    from playwright.sync_api import expect

    _goto(page)
    page.get_by_role("button", name=re.compile("^run", re.I)).first.click()
    expect(page.get_by_text(re.compile("run finished")).first).to_be_visible(timeout=30_000)
    page.get_by_role("button", name=re.compile("^reset", re.I)).first.click()
    # after reset the Run button is clickable again (idle) and the seeded root is still shown
    expect(page.get_by_role("button", name=re.compile("^run", re.I)).first).to_be_enabled(timeout=10_000)
    expect(page.get_by_text(re.compile("auth", re.I)).first).to_be_visible(timeout=10_000)
