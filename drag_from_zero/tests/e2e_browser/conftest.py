"""Fixtures for the opt-in browser layer. Imports cleanly even without playwright.

The actual `pytest.importorskip("playwright.sync_api")` lives at the top of the test module,
so a host without playwright SKIPS these (never a collection error). `sync_playwright` is
imported lazily inside the `page` fixture for the same reason.
"""
import threading

import pytest

from dragzero.server import Run, make_server

# Reuse the deterministic demo wiring the real server ships (FakeLLM + the verifier DONE_WHEN
# spec), so the browser drives exactly what `python run_server.py` serves.
from run_server import DONE_WHEN, TASK, UI_DIR, _demo_builder


@pytest.fixture
def base_url():
    """Serve the real ui/ against the deterministic runtime on an ephemeral port."""
    run = Run(id="run-1", title="auth feature", task=TASK,
              builder=_demo_builder(), pace=0.03, done_when=DONE_WHEN)
    httpd = make_server(run, static_dir=UI_DIR, host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


@pytest.fixture
def page(base_url):
    """A headless chromium page with console/page errors captured on `page.dz_errors`."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        # dz_errors = uncaught JS exceptions (the hard "did it crash" gate). console.error is
        # kept separately and NOT gated: the DC framework emits a benign SVG-template warning
        # ("<path d> Expected moveto … '{{ e.d }}'") for un-bound edge paths — cosmetic, not a crash.
        pg.dz_errors = []     # type: ignore[attr-defined]
        pg.dz_console = []    # type: ignore[attr-defined]
        pg.on("pageerror", lambda exc: pg.dz_errors.append(f"pageerror: {exc}"))
        pg.on("console", lambda msg: pg.dz_console.append(msg.text) if msg.type == "error" else None)
        pg.dz_base = base_url   # type: ignore[attr-defined]
        try:
            yield pg
        finally:
            browser.close()
