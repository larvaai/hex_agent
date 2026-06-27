"""L1 backend-integration — the real HTTP surface's CORS + auth asymmetry + idempotency, over a
live socket against the real ``IdeControlServer``. No model.

Pins the security posture a browser can't forge from JS: CORS reflects only localhost origins
(never ``*``), the snapshot is public but every mutating verb is token-gated, and a replayed
SubmitPrompt dispatches the run exactly once.
"""
from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection

import pytest

import ui.ide.server as server_mod


@pytest.fixture()
def server(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    srv = server_mod.IdeControlServer(("127.0.0.1", 0), token="tok", session_id="t1_demo")
    port = srv.socket.getsockname()[1]
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        yield srv, port
    finally:
        srv.shutdown()
        srv.server_close()


# ── CORS: localhost reflected, arbitrary origin denied (server.py:55-56,188-193) ──
@pytest.mark.security
@pytest.mark.integration
def test_cors_reflects_localhost_only(server):
    _, port = server
    good = _request(port, "GET", "/api/snapshot", origin="http://127.0.0.1:3000")
    assert good.status == 200
    assert good.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:3000"
    assert good.headers.get("Access-Control-Allow-Origin") != "*"  # never a blanket wildcard

    evil = _request(port, "GET", "/api/snapshot", origin="http://evil.com")
    assert evil.status == 200  # the snapshot is public…
    assert evil.headers.get("Access-Control-Allow-Origin") is None  # …but not readable cross-origin


@pytest.mark.integration
def test_options_preflight_headers(server):
    _, port = server
    resp = _request(port, "OPTIONS", "/api/files/write", origin="http://localhost:5173")
    assert resp.status == 204
    assert "PUT" in resp.headers.get("Access-Control-Allow-Methods", "")
    assert "X-Auth-Token" in resp.headers.get("Access-Control-Allow-Headers", "")
    assert resp.headers.get("Access-Control-Max-Age") == "86400"
    assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


# ── snapshot public, every write gated (server.py:195-205, :242-248) ──────────────
@pytest.mark.security
@pytest.mark.integration
def test_snapshot_is_public_but_writes_gated(server):
    _, port = server
    assert _request(port, "GET", "/api/snapshot").status == 200  # public read, no token

    # every mutating verb without the token → 401, disk untouched
    assert _request(port, "POST", "/api/files/create",
                    body={"scope": "workspace", "path": "x.txt", "kind": "file"}).status == 401
    assert _request(port, "PUT", "/api/files/write",
                    body={"scope": "workspace", "path": "x.txt", "content": "no"}).status == 401
    assert _request(port, "DELETE", "/api/files?scope=workspace&path=x.txt").status == 401


# ── idempotency: replayed SubmitPrompt dispatches once (server.py:111-155) ────────
@pytest.mark.integration
def test_idempotency_dedup_same_ack(server, monkeypatch):
    srv, port = server
    calls: list[str] = []

    def counting_start(self, prompt, system_prompt=None):  # noqa: ANN001
        calls.append(prompt)
        return "run-id"  # non-None → server treats the run as dispatched

    monkeypatch.setattr(server_mod.AgentRunner, "start", counting_start)

    body = {
        "command_id": "cmd-1",
        "command_type": "SubmitPrompt",
        "session_id": "t1_demo",
        "issued_by": {"type": "human", "user_id": "tester"},
        "idempotency_key": "key-1",
        "payload": {"prompt": "build it"},
    }
    first = _request(port, "POST", "/api/commands", body=body, token="tok")
    second = _request(port, "POST", "/api/commands", body=body, token="tok")

    assert first.status == 200 and second.status == 200
    assert first.json == second.json  # identical ack on replay
    assert first.json["status"] == "received" and first.json["seq"] is not None
    assert calls == ["build it"]  # dispatched exactly once despite two POSTs


# ── tiny socket client returning status + headers + json ──────────────────────────
class _Resp:
    def __init__(self, status, headers, json_body):
        self.status = status
        self.headers = headers
        self.json = json_body


def _request(port, method, path, *, body=None, token=None, origin=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Auth-Token"] = token
    if origin:
        headers["Origin"] = origin
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    resp = conn.getresponse()
    raw = resp.read()
    hdrs = {k: v for k, v in resp.getheaders()}
    conn.close()
    return _Resp(resp.status, hdrs, json.loads(raw) if raw else {})
