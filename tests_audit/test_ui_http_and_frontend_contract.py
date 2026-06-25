"""Black-box HTTP API and static frontend contract tests."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import ui.server as ui_server


class FakeController:
    def __init__(self):
        self.started = []

    def start(self, prompt, system_prompt):
        self.started.append((prompt, system_prompt))
        return ui_server.RunJob("fake-run", prompt, system_prompt)

    def get(self, run_id):
        return None

    def close(self):
        return None


@pytest.fixture
def ui_http_server():
    controller = FakeController()
    server = ui_server.AgentUIServer(("127.0.0.1", 0), controller)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base, controller
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(base, path, *, body=None, headers=None):
    raw = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(base + path, data=raw, headers=headers or {}, method="POST" if body is not None else "GET")
    try:
        response = urlopen(request, timeout=3)
    except HTTPError as exc:
        response = exc
    payload = response.read()
    content_type = response.headers.get("Content-Type", "")
    parsed = json.loads(payload) if "application/json" in content_type else payload
    return response.status, response.headers, parsed


@pytest.mark.audit
@pytest.mark.integration
def test_http_static_and_read_apis_have_exact_status_and_types(ui_http_server):
    base, _ = ui_http_server
    status, headers, html = _request(base, "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert b"Core Agent Console" in html

    status, headers, js = _request(base, "/app.js")
    assert status == 200
    assert "javascript" in headers["Content-Type"]
    assert js.startswith(b'"use strict"')

    status, _, payload = _request(base, "/api/runs")
    assert status == 200 and payload == {"runs": []}
    status, _, payload = _request(base, "/does-not-exist")
    assert status == 404
    assert isinstance(payload, bytes)


@pytest.mark.audit
@pytest.mark.integration
@pytest.mark.parametrize("path", ["/api/tree?scope=invalid", "/api/snapshot?scope=invalid", "/api/bootstrap?scope=invalid"])
def test_every_scope_endpoint_returns_json_400_for_invalid_scope(ui_http_server, path):
    base, _ = ui_http_server
    status, headers, payload = _request(base, path)
    assert status == 400
    assert headers["Content-Type"].startswith("application/json")
    assert payload["ok"] is False
    assert "scope" in payload["error"]


@pytest.mark.audit
@pytest.mark.integration
@pytest.mark.parametrize(
    ("body", "status", "error"),
    [
        ({}, 400, "prompt is required"),
        ({"prompt": "   "}, 400, "prompt is required"),
        ({"prompt": "x", "system_prompt": 123}, 400, "must be a string"),
        ({"prompt": "x" * (ui_server.MAX_PROMPT_CHARS + 1)}, 400, "prompt exceeds"),
        ({"prompt": "x", "system_prompt": "s" * (ui_server.MAX_SYSTEM_PROMPT_CHARS + 1)}, 400, "system_prompt exceeds"),
    ],
)
def test_run_submission_rejects_invalid_payload_matrix(ui_http_server, body, status, error):
    base, controller = ui_http_server
    actual, _, payload = _request(base, "/api/runs", body=body, headers={"Content-Type": "application/json"})
    assert actual == status
    assert error in payload["error"]
    assert controller.started == []


@pytest.mark.audit
@pytest.mark.integration
def test_run_submission_preserves_exact_custom_system_prompt(ui_http_server):
    base, controller = ui_http_server
    custom = "SYSTEM\nkeep whitespace  \n"

    status, _, payload = _request(
        base,
        "/api/runs",
        body={"prompt": "  user task  ", "system_prompt": custom},
        headers={"Content-Type": "application/json"},
    )

    assert status == 202
    assert payload == {"ok": True, "run": asdict(ui_server.RunJob("fake-run", "user task", custom))}
    assert controller.started == [("user task", custom)]


@pytest.mark.audit
@pytest.mark.security
def test_http_responses_set_baseline_browser_security_headers(ui_http_server):
    base, _ = ui_http_server
    for path in ("/", "/app.js", "/api/runs"):
        status, headers, _ = _request(base, path)
        assert status == 200
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] in {"no-referrer", "same-origin"}
        assert "default-src 'self'" in headers["Content-Security-Policy"]


@pytest.mark.audit
def test_frontend_every_literal_id_selector_exists_in_html():
    html = (ui_server.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    javascript = (ui_server.STATIC_DIR / "app.js").read_text(encoding="utf-8")
    declared = set(re.findall(r'\bid="([^"]+)"', html))
    referenced = set(re.findall(r'\$\("#([^"]+)"\)', javascript))

    assert referenced
    assert referenced - declared == set()


@pytest.mark.audit
@pytest.mark.security
def test_frontend_has_no_third_party_runtime_dependency_or_unsafe_html_sink():
    html = (ui_server.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    javascript = (ui_server.STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "https://" not in html and "http://" not in html
    assert "innerHTML" not in javascript
    assert "eval(" not in javascript
    assert "new Function(" not in javascript


@pytest.mark.audit
def test_utf8_frontend_sources_do_not_contain_mojibake_markers():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ui_server.STATIC_DIR / "index.html", ui_server.STATIC_DIR / "app.js")
    )
    markers = ("Ã", "Ä", "Â", "â€", "ï»¿", "�")
    found = {marker for marker in markers if marker in text}
    assert found == set()
