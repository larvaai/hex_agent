"""Adversarial/rigor coverage for the OLD observability HTTP server (ui/server.py, ui/__main__.py).

Pins the real BaseHTTPRequestHandler routes end-to-end over loopback sockets:
every do_GET branch, do_POST run submission, SSE /stream framing+termination,
path-traversal rejection across scopes, security headers, run-lifecycle threading
driven WITHOUT a real LLM, and the __main__/main() CLI entrypoints. This is the
legacy console, NOT the new control-plane (which is hot and untouched here).
"""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import asdict
from http import HTTPStatus
from http.client import HTTPConnection
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import ui.server as ui_server
import ui.__main__ as ui_main

pytestmark = [pytest.mark.audit, pytest.mark.integration]


# ----------------------------------------------------------------------------
# Harness: real server on an ephemeral port + a stub controller we fully drive.
# ----------------------------------------------------------------------------


class StubController:
    """Records start() calls and serves canned get() so handlers stay LLM-free."""

    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.jobs: dict[str, dict] = {}

    def start(self, prompt: str, system_prompt: str) -> ui_server.RunJob:
        run_id = f"stub-{len(self.started)}"
        self.started.append((prompt, system_prompt))
        job = ui_server.RunJob(run_id=run_id, prompt=prompt, system_prompt=system_prompt)
        self.jobs[run_id] = asdict(job)
        return job

    def get(self, run_id: str):  # noqa: ANN001
        return self.jobs.get(run_id)

    def close(self) -> None:  # pragma: no cover - parity with real controller
        return None


def _serve(controller) -> tuple[ui_server.AgentUIServer, threading.Thread, str]:
    server = ui_server.AgentUIServer(("127.0.0.1", 0), controller)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    return server, thread, base


@pytest.fixture
def ui_server_with_stub():
    """Real AgentUIServer wired to a deterministic stub controller."""
    controller = StubController()
    server, thread, base = _serve(controller)
    try:
        yield base, controller, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(base, path, *, body=None, headers=None, method=None):
    raw = None if body is None else json.dumps(body).encode("utf-8")
    verb = method or ("POST" if body is not None else "GET")
    request = Request(base + path, data=raw, headers=headers or {}, method=verb)
    try:
        response = urlopen(request, timeout=4)
    except HTTPError as exc:
        response = exc
    payload = response.read()
    content_type = response.headers.get("Content-Type", "")
    parsed = json.loads(payload) if "application/json" in content_type else payload
    return response.status, response.headers, parsed


def _port(base: str) -> int:
    return int(base.rsplit(":", 1)[1])


# ----------------------------------------------------------------------------
# do_GET — every read route + 404/400 error branches.
# ----------------------------------------------------------------------------


def test_runs_route_empty_when_no_runs_dir(ui_server_with_stub):
    # WHY: /api/runs over a fresh (nonexistent) runs_dir must be an empty list, status 200.
    base, _, _ = ui_server_with_stub
    status, headers, payload = _request(base, "/api/runs")
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert payload == {"runs": []}


def test_bootstrap_route_carries_project_and_default_prompt(ui_server_with_stub):
    # WHY: /api/bootstrap composes run_snapshot + static metadata; pins the extra keys.
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/bootstrap?scope=workspace")
    assert status == 200
    assert payload["project"] == ui_server.PROJECT_DIR.name
    assert payload["default_system_prompt"] == ui_server.DEFAULT_SYSTEM
    # run_snapshot shape is merged in:
    assert "runs" in payload and "files" in payload and "run" in payload


def test_tree_route_reflects_workspace_filesystem(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: /api/tree must walk the live workspace_dir and report entry counts.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/tree?scope=workspace")
    assert status == 200
    assert payload["scope"] == "workspace"
    names = {child["name"] for child in payload["tree"]["children"]}
    assert "pkg" in names
    assert payload["entries"] == 3  # root + pkg + mod.py
    assert payload["truncated"] is False


def test_file_route_returns_normalized_utf8_content(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: /api/file returns preview with CRLF normalized to LF and a language tag.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "a.txt").write_text("one\r\ntwo\rthree\n", encoding="utf-8")
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/file?scope=workspace&path=a.txt")
    assert status == 200
    assert payload["content"] == "one\ntwo\nthree\n"
    assert payload["language"] == "txt"
    assert payload["name"] == "a.txt"


def test_snapshot_route_default_scope_is_workspace(ui_server_with_stub):
    # WHY: /api/snapshot with no scope defaults to workspace and returns the full shape.
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/snapshot")
    assert status == 200
    assert payload["files"]["scope"] == "workspace"
    assert payload["selected_run_id"] is None  # no runs on disk
    assert payload["run"]["status"] == "idle"


@pytest.mark.parametrize("path", ["/api/tree", "/api/snapshot", "/api/bootstrap", "/api/file"])
def test_invalid_scope_yields_json_400_on_every_scope_route(ui_server_with_stub, path):
    # WHY: ValueError from _root_for_scope must surface as a JSON 400, not a 500.
    base, _, _ = ui_server_with_stub
    sep = "&" if "?" in path else "?"
    status, headers, payload = _request(base, f"{path}{sep}scope=bogus")
    assert status == 400
    assert headers["Content-Type"].startswith("application/json")
    assert payload["ok"] is False
    assert "scope" in payload["error"]


def test_file_route_unknown_file_is_json_404(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: missing file path -> FileNotFoundError -> 404 JSON (not a static 404 page).
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    base, _, _ = ui_server_with_stub
    status, headers, payload = _request(base, "/api/file?scope=workspace&path=nope.txt")
    assert status == 404
    assert headers["Content-Type"].startswith("application/json")
    assert payload == {"ok": False, "error": "file not found"}


def test_file_route_sensitive_name_is_json_403(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: sensitive filenames are blocked with 403 even when the file exists & is readable.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/file?scope=workspace&path=.env")
    assert status == 403
    assert payload["ok"] is False
    assert "sensitive" in payload["error"]


@pytest.mark.parametrize("suffix", [".pem", ".key", ".p12", ".pfx"])
def test_file_route_sensitive_suffix_is_json_403(ui_server_with_stub, tmp_path, monkeypatch, suffix):
    # WHY: cert/key suffixes are blocked regardless of basename.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / f"secret{suffix}").write_text("-----BEGIN-----\n", encoding="utf-8")
    base, _, _ = ui_server_with_stub
    status, _, _ = _request(base, f"/api/file?scope=workspace&path=secret{suffix}")
    assert status == 403


def test_file_route_binary_preview_disabled_is_400(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: NUL byte in the first 4KB triggers a ValueError -> 400 (binary preview off).
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"abc\x00def")
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/file?scope=workspace&path=blob.bin")
    assert status == 400
    assert "binary" in payload["error"]


def test_file_route_oversize_preview_is_400(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: files above MAX_FILE_BYTES are refused with the explicit limit message.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "big.txt").write_bytes(b"a" * (ui_server.MAX_FILE_BYTES + 1))
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/file?scope=workspace&path=big.txt")
    assert status == 400
    assert "preview limit" in payload["error"]


def test_file_route_invalid_utf8_is_400(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: non-UTF-8 bytes (no NUL) reach the decode branch and 400 as "not UTF-8 text".
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "latin.txt").write_bytes(b"caf\xe9 latin1 only")  # 0xe9, no NUL
    base, _, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/file?scope=workspace&path=latin.txt")
    assert status == 400
    assert "UTF-8" in payload["error"]


# ----------------------------------------------------------------------------
# Path traversal — both scopes, several escape shapes.
# ----------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.parametrize(
    "evil",
    [
        "../outside.txt",
        "../../etc/passwd",
        "%2e%2e%2foutside.txt",  # url-encoded ../
        "/etc/passwd",  # absolute path
        "sub/../../escape.txt",
    ],
)
def test_safe_file_rejects_traversal_workspace_scope(tmp_path, monkeypatch, evil):
    # WHY: every ../, encoded, or absolute escape must raise before any read.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "sub").mkdir(exist_ok=True)
    with pytest.raises((ValueError, PermissionError, FileNotFoundError)):
        ui_server.read_file_snapshot("workspace", evil)


@pytest.mark.security
def test_safe_file_absolute_path_escapes_root(tmp_path, monkeypatch):
    # WHY: an absolute /etc/passwd resolves outside root -> ValueError, never read.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    with pytest.raises(ValueError):
        ui_server._safe_file("workspace", "/etc/passwd")


@pytest.mark.security
def test_safe_file_symlink_escape_rejected(tmp_path, monkeypatch):
    # WHY: a symlink pointing outside the root must be caught by the resolve() check.
    outside = tmp_path / "secret.txt"
    outside.write_text("TOP SECRET\n", encoding="utf-8")
    root = tmp_path / "ws"
    root.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: root)
    with pytest.raises((ValueError, PermissionError)):
        ui_server.read_file_snapshot("workspace", "escape")


@pytest.mark.security
def test_file_route_traversal_over_http_does_not_leak(ui_server_with_stub, tmp_path, monkeypatch):
    # WHY: end-to-end, a ../ escape on /api/file returns a 400/403 JSON, never file bytes.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    base, _, _ = ui_server_with_stub
    status, headers, payload = _request(base, "/api/file?scope=workspace&path=../../etc/passwd")
    assert status in (400, 403, 404)
    assert headers["Content-Type"].startswith("application/json")
    assert payload["ok"] is False


@pytest.mark.security
def test_project_scope_hidden_paths_are_forbidden(monkeypatch):
    # WHY: project scope must refuse files inside IGNORED_DIRS / var/agent_runs.
    # PROJECT_DIR has a .git dir; reading into it must raise PermissionError.
    with pytest.raises(PermissionError):
        ui_server._safe_file("project", ".git/config")


def test_is_hidden_project_path_matrix():
    # WHY: pin the filter that drives both tree pruning and project-scope file gating.
    from pathlib import Path

    assert ui_server._is_hidden_project_path(Path(".git/config")) is True
    assert ui_server._is_hidden_project_path(Path("node_modules/x")) is True
    assert ui_server._is_hidden_project_path(Path("__pycache__")) is True
    assert ui_server._is_hidden_project_path(Path("var/agent_runs/r1")) is True
    assert ui_server._is_hidden_project_path(Path("var/workspace/ok.txt")) is False
    assert ui_server._is_hidden_project_path(Path("ui/server.py")) is False


# ----------------------------------------------------------------------------
# Static serving + its own traversal guard + security headers.
# ----------------------------------------------------------------------------


def test_static_index_served_at_root_and_index_html(ui_server_with_stub):
    # WHY: "/" and "/index.html" both map to the same static index file.
    base, _, _ = ui_server_with_stub
    for path in ("/", "/index.html"):
        status, headers, html = _request(base, path)
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert isinstance(html, (bytes, bytearray))


def test_static_known_assets_have_content_type(ui_server_with_stub):
    # WHY: app.js / app.css serve with their guessed content-types and cache-control.
    base, _, _ = ui_server_with_stub
    for name, marker in (("/app.js", "javascript"), ("/app.css", "css")):
        status, headers, _ = _request(base, name)
        assert status == 200
        assert marker in headers["Content-Type"]
        assert headers["Cache-Control"] == "no-store"


def test_static_unknown_file_is_404(ui_server_with_stub):
    # WHY: unknown static path -> send_error 404 (non-JSON body).
    base, _, _ = ui_server_with_stub
    status, _, body = _request(base, "/does-not-exist.js")
    assert status == 404
    assert isinstance(body, (bytes, bytearray))


def test_static_serve_rejects_subdir_traversal(ui_server_with_stub):
    # WHY: _serve_static only serves files whose parent IS STATIC_DIR (no nested escape).
    base, _, _ = ui_server_with_stub
    for evil in ("/../server.py", "/sub/index.html", "/..%2fserver.py"):
        status, _, _ = _request(base, evil)
        assert status == 404


@pytest.mark.security
def test_security_headers_present_on_json_static_and_error(ui_server_with_stub):
    # WHY: baseline hardening headers must ride on success JSON, static, AND error JSON.
    base, _, _ = ui_server_with_stub
    for path in ("/api/runs", "/", "/app.js", "/api/tree?scope=bogus"):
        _, headers, _ = _request(base, path)
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'self'" in headers["Content-Security-Policy"]
        assert "object-src 'none'" in headers["Content-Security-Policy"]


# ----------------------------------------------------------------------------
# do_POST /api/runs — happy path + malformed bodies (error branches).
# ----------------------------------------------------------------------------


def test_post_run_accepted_and_forwards_to_controller(ui_server_with_stub):
    # WHY: a valid POST returns 202 with the asdict(job) and trims prompt whitespace.
    base, controller, _ = ui_server_with_stub
    status, _, payload = _request(
        base,
        "/api/runs",
        body={"prompt": "  do a thing  "},
        headers={"Content-Type": "application/json"},
    )
    assert status == 202
    assert payload["ok"] is True
    assert payload["run"]["prompt"] == "do a thing"
    assert payload["run"]["status"] == "queued"
    assert controller.started == [("do a thing", ui_server.DEFAULT_SYSTEM)]


def test_post_run_custom_system_prompt_preserved_verbatim(ui_server_with_stub):
    # WHY: system_prompt is stored exactly (whitespace kept), only prompt is stripped.
    base, controller, _ = ui_server_with_stub
    custom = "SYS\n  keep  \n"
    status, _, payload = _request(
        base,
        "/api/runs",
        body={"prompt": "go", "system_prompt": custom},
        headers={"Content-Type": "application/json"},
    )
    assert status == 202
    assert payload["run"]["system_prompt"] == custom
    assert controller.started == [("go", custom)]


def test_post_to_wrong_path_is_404(ui_server_with_stub):
    # WHY: POST routing only accepts /api/runs.
    base, _, _ = ui_server_with_stub
    status, _, _ = _request(base, "/api/file", body={"x": 1}, headers={"Content-Type": "application/json"})
    assert status == 404


def test_post_empty_body_rejected(ui_server_with_stub):
    # WHY: Content-Length 0 path -> "empty or too large" 413.
    base, controller, _ = ui_server_with_stub
    conn = HTTPConnection("127.0.0.1", _port(base), timeout=4)
    conn.request("POST", "/api/runs", body=b"", headers={"Content-Length": "0"})
    resp = conn.getresponse()
    body = json.loads(resp.read())
    conn.close()
    assert resp.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert body["ok"] is False
    assert controller.started == []


def test_post_oversize_body_rejected(ui_server_with_stub):
    # WHY: Content-Length above MAX_REQUEST_BYTES is rejected BEFORE the body is read.
    base, controller, _ = ui_server_with_stub
    conn = HTTPConnection("127.0.0.1", _port(base), timeout=4)
    # Lie about a huge length; server must 413 without consuming the (absent) body.
    conn.putrequest("POST", "/api/runs")
    conn.putheader("Content-Length", str(ui_server.MAX_REQUEST_BYTES + 1))
    conn.endheaders()
    resp = conn.getresponse()
    body = json.loads(resp.read())
    conn.close()
    assert resp.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert "too large" in body["error"]
    assert controller.started == []


def test_post_non_integer_content_length_is_400(ui_server_with_stub):
    # WHY: a non-numeric Content-Length hits the int() ValueError branch -> 400 JSON.
    base, controller, _ = ui_server_with_stub
    conn = HTTPConnection("127.0.0.1", _port(base), timeout=4)
    body = b'{"prompt":"x"}'
    conn.putrequest("POST", "/api/runs")
    conn.putheader("Content-Length", "not-a-number")
    conn.putheader("X-Real-Length", str(len(body)))
    conn.endheaders()
    conn.send(body)
    resp = conn.getresponse()
    payload = json.loads(resp.read())
    conn.close()
    assert resp.status == 400
    assert "Content-Length" in payload["error"]
    assert controller.started == []


def test_post_malformed_json_body_is_400(ui_server_with_stub):
    # WHY: a non-JSON body (valid Content-Length) hits the JSONDecodeError branch.
    base, controller, _ = ui_server_with_stub
    conn = HTTPConnection("127.0.0.1", _port(base), timeout=4)
    body = b"{not valid json"
    conn.request("POST", "/api/runs", body=body, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    payload = json.loads(resp.read())
    conn.close()
    assert resp.status == 400
    assert "JSON" in payload["error"]
    assert controller.started == []


def test_post_invalid_utf8_body_is_400(ui_server_with_stub):
    # WHY: bytes that aren't valid UTF-8 hit the UnicodeDecodeError branch.
    base, controller, _ = ui_server_with_stub
    conn = HTTPConnection("127.0.0.1", _port(base), timeout=4)
    body = b"\xff\xfe\x00bad"
    conn.request("POST", "/api/runs", body=body, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    payload = json.loads(resp.read())
    conn.close()
    assert resp.status == 400
    assert "UTF-8" in payload["error"]
    assert controller.started == []


def test_post_json_array_body_is_missing_prompt(ui_server_with_stub):
    # WHY: a non-dict JSON payload -> prompt resolves empty -> "prompt is required".
    base, controller, _ = ui_server_with_stub
    status, _, payload = _request(
        base, "/api/runs", body=[1, 2, 3], headers={"Content-Type": "application/json"}
    )
    assert status == 400
    assert payload["error"] == "prompt is required"
    assert controller.started == []


# ----------------------------------------------------------------------------
# SSE /stream — framing, scope validation, keep-alive, and termination.
# ----------------------------------------------------------------------------


def test_stream_invalid_scope_is_json_400(ui_server_with_stub):
    # WHY: _stream validates scope FIRST; bad scope short-circuits to a 400 JSON.
    base, _, _ = ui_server_with_stub
    status, headers, payload = _request(base, "/api/stream?scope=bogus")
    assert status == 400
    assert headers["Content-Type"].startswith("application/json")
    assert "scope" in payload["error"]


def test_stream_emits_retry_and_snapshot_frame_then_terminates(ui_server_with_stub):
    # WHY: a live SSE stream must send `retry:`, an `event: snapshot` frame with JSON
    #      data, and must stop cleanly when the client disconnects (no hang/leak).
    #      Raw socket + recv (NOT read(n), which blocks waiting for a fixed count
    #      since the stream idles between digest changes).
    base, _, _ = ui_server_with_stub
    raw = socket.create_connection(("127.0.0.1", _port(base)), timeout=5)
    raw.sendall(b"GET /api/stream?scope=workspace HTTP/1.1\r\nHost: localhost\r\n\r\n")
    # Read until the first snapshot frame is fully present: marker + a data line whose
    # frame terminator (blank line) has arrived. recv() yields whatever is buffered.
    payload = b""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        chunk = raw.recv(2048)
        if not chunk:
            break
        payload += chunk
        if b"event: snapshot" in payload and payload.split(b"event: snapshot", 1)[1].count(b"\n\n"):
            break
    assert b"text/event-stream" in payload
    assert b"retry: 1000" in payload
    assert b"event: snapshot" in payload
    body = payload.split(b"\r\n\r\n", 1)[-1]  # drop HTTP response headers
    data_line = next(line for line in body.split(b"\n") if line.startswith(b"data: "))
    decoded = json.loads(data_line[len(b"data: "):].strip())
    assert "selected_run_id" in decoded and "files" in decoded

    raw.close()  # client disconnects; handler loop must hit broken-pipe and return.
    # The server itself is still serving new requests (handler thread died, server alive):
    status, _, payload = _request(base, "/api/runs")
    assert status == 200 and payload == {"runs": []}


def test_stream_terminates_on_abrupt_socket_close(ui_server_with_stub):
    # WHY: rawest path — open the SSE, read the preamble, hard-close the socket. The
    #      ThreadingHTTPServer handler must swallow the connection error and not crash
    #      the server (subsequent request still succeeds).
    base, _, _ = ui_server_with_stub
    raw = socket.create_connection(("127.0.0.1", _port(base)), timeout=5)
    raw.sendall(b"GET /api/stream?scope=workspace HTTP/1.1\r\nHost: localhost\r\n\r\n")
    preamble = raw.recv(1024)
    assert b"text/event-stream" in preamble
    raw.close()  # abrupt close mid-stream
    # Server stays healthy for the next client.
    status, _, payload = _request(base, "/api/runs")
    assert status == 200 and payload == {"runs": []}


# ----------------------------------------------------------------------------
# RunController threading & lifecycle — WITHOUT a real LLM.
# ----------------------------------------------------------------------------


def _drive_execute(monkeypatch, *, outcome=None, raise_exc=None):
    """Stub every collaborator ui.server._execute touches so a job runs LLM-free."""

    emitted: list[tuple] = []

    class FakeLogger:
        def __init__(self, run_id=None, **_):  # noqa: ANN001
            self.run_id = run_id

        def emit(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            emitted.append(("emit", args, kwargs))

        def finish(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            emitted.append(("finish", args, kwargs))

    monkeypatch.setattr(ui_server, "EventLogger", FakeLogger)
    monkeypatch.setattr(ui_server, "create_kernel", lambda: type("K", (), {"events": object()})())
    monkeypatch.setattr(ui_server, "attach_to_bus", lambda *a, **k: None)
    monkeypatch.setattr(ui_server, "create_delegation_service", lambda kernel: object())

    def fake_run_agent(kernel, prompt, **kwargs):  # noqa: ANN001, ANN003
        if raise_exc is not None:
            raise raise_exc
        return outcome if outcome is not None else {"status": "completed"}

    monkeypatch.setattr(ui_server, "run_agent", fake_run_agent)
    return emitted


def _await_terminal(controller, run_id, *, timeout=6.0):
    """Poll a controller job until it leaves the queued/starting/running states."""
    deadline = time.monotonic() + timeout
    terminal = {"completed", "succeeded", "failed"}
    while time.monotonic() < deadline:
        job = controller.get(run_id)
        if job and job["status"] in terminal:
            return job
        time.sleep(0.01)
    job = controller.get(run_id)
    raise AssertionError(f"run {run_id} never reached terminal state: {job}")


@pytest.mark.concurrency
def test_controller_run_reaches_terminal_completed(monkeypatch):
    # WHY: full start->_execute lifecycle with a stubbed agent ends in the agent's status.
    emitted = _drive_execute(monkeypatch, outcome={"status": "succeeded"})
    controller = ui_server.RunController(max_workers=2)
    try:
        job = controller.start("hello", "sys")
        # NOTE: do not assert job.status == "queued" here — the stubbed executor can
        # finish before this line, mutating the shared RunJob dataclass in place.
        final = _await_terminal(controller, job.run_id)
        assert final["status"] == "succeeded"
        assert final["started_at"] is not None
        assert final["finished_at"] is not None
        assert final["error"] is None
        # logger.finish was called exactly once on success.
        assert sum(1 for kind, *_ in emitted if kind == "finish") == 1
    finally:
        controller.close()


@pytest.mark.concurrency
def test_controller_run_failure_records_error_and_failed_status(monkeypatch):
    # WHY: an exception in run_agent must drive status=failed and stash a typed error string.
    emitted = _drive_execute(monkeypatch, raise_exc=RuntimeError("boom"))
    controller = ui_server.RunController(max_workers=1)
    try:
        job = controller.start("explode", "sys")
        final = _await_terminal(controller, job.run_id)
        assert final["status"] == "failed"
        assert final["error"] == "RuntimeError: boom"
        assert final["finished_at"] is not None
        assert any(kind == "finish" for kind, *_ in emitted)
    finally:
        controller.close()


@pytest.mark.concurrency
def test_controller_default_completed_when_outcome_lacks_status(monkeypatch):
    # WHY: outcome without a 'status' falls back to "completed".
    _drive_execute(monkeypatch, outcome={"result": "ok"})
    controller = ui_server.RunController(max_workers=1)
    try:
        job = controller.start("noop", "sys")
        final = _await_terminal(controller, job.run_id)
        assert final["status"] == "completed"
    finally:
        controller.close()


@pytest.mark.concurrency
def test_controller_concurrent_starts_have_unique_ids_and_all_terminate(monkeypatch):
    # WHY: many concurrent submissions must each get a unique run_id and all finish.
    _drive_execute(monkeypatch, outcome={"status": "completed"})
    controller = ui_server.RunController(max_workers=4)
    try:
        threads = []
        results = {}

        def submit(i):
            job = controller.start(f"task-{i}", "sys")
            results[i] = job.run_id

        for i in range(12):
            t = threading.Thread(target=submit, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=5)
        ids = list(results.values())
        assert len(ids) == 12
        assert len(set(ids)) == 12  # all unique
        for run_id in ids:
            final = _await_terminal(controller, run_id)
            assert final["status"] == "completed"
    finally:
        controller.close()


def test_controller_get_unknown_run_is_none():
    # WHY: get() for an unknown id returns None (no KeyError leak).
    controller = ui_server.RunController(max_workers=1)
    try:
        assert controller.get("does-not-exist") is None
    finally:
        controller.close()


def test_controller_update_unknown_run_raises_keyerror():
    # WHY: _update assumes the job exists; document that contract (KeyError on miss).
    controller = ui_server.RunController(max_workers=1)
    try:
        with pytest.raises(KeyError):
            controller._update("ghost", status="x")
    finally:
        controller.close()


def test_controller_execute_missing_job_is_noop(monkeypatch):
    # WHY: _execute(run_id) where the job vanished returns early without touching collaborators.
    _drive_execute(monkeypatch, outcome={"status": "completed"})
    controller = ui_server.RunController(max_workers=1)
    try:
        # No job registered for this id; _execute must short-circuit on get()==None.
        controller._execute("never-registered")  # must not raise
    finally:
        controller.close()


# ----------------------------------------------------------------------------
# list_runs / run_snapshot — disk-backed read path without a controller LLM.
# ----------------------------------------------------------------------------


def test_list_runs_reads_disk_summaries(monkeypatch, tmp_path):
    # WHY: list_runs walks runs_dir, newest-first, merging checkpoint/summary/job.
    runs = tmp_path / "runs"
    runs.mkdir()
    for name, step in (("20240101_000000_aaaa", 2), ("20240102_000000_bbbb", 5)):
        d = runs / name
        d.mkdir()
        (d / "checkpoint.json").write_text(json.dumps({"task": f"t-{name}", "step": step}), encoding="utf-8")
        (d / "summary.json").write_text(json.dumps({"status": "completed", "metrics": {"k": 1}}), encoding="utf-8")
    monkeypatch.setattr(ui_server, "runs_dir", lambda: runs)

    controller = StubController()
    rows = ui_server.list_runs(controller)
    assert [r["run_id"] for r in rows] == ["20240102_000000_bbbb", "20240101_000000_aaaa"]  # reverse sorted
    assert rows[0]["step"] == 5
    assert rows[0]["status"] == "completed"
    assert rows[0]["metrics"] == {"k": 1}
    assert rows[0]["prompt"] == "t-20240102_000000_bbbb"


def test_run_snapshot_unknown_run_id_still_lists_and_is_idle(monkeypatch, tmp_path):
    # WHY: requesting a run_id that isn't a real dir yields empty checkpoint + idle status,
    #      while still returning the (empty) runs list and a workspace tree.
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(ui_server, "runs_dir", lambda: runs)
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    snap = ui_server.run_snapshot("ghost-run", "workspace", StubController())
    assert snap["selected_run_id"] == "ghost-run"
    assert snap["run"]["status"] == "idle"
    assert snap["run"]["checkpoint"] == {}
    assert snap["files"]["scope"] == "workspace"


@pytest.mark.security
@pytest.mark.xfail(
    reason="run_snapshot path-traversal: guard checks run_path.parent.resolve() but "
    "Path('runs/..').parent is lexically 'runs', so a run_id of '..' passes the guard "
    "while run_path itself resolves to runs_dir's PARENT, leaking checkpoint.json from "
    "outside runs_dir. Guard should be run_path.resolve().parent == runs_dir().resolve().",
    strict=False,
)
def test_run_snapshot_path_escape_run_id_is_ignored(monkeypatch, tmp_path):
    # WHY (security): a traversal-style run_id ('..') must NOT read files outside runs_dir.
    runs = tmp_path / "runs"
    runs.mkdir()
    # Plant a checkpoint OUTSIDE runs_dir (in its parent) that a naive join would reach.
    outside = tmp_path / "checkpoint.json"
    outside.write_text(json.dumps({"task": "LEAK", "step": 99}), encoding="utf-8")
    monkeypatch.setattr(ui_server, "runs_dir", lambda: runs)
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    snap = ui_server.run_snapshot("..", "workspace", StubController())
    # Correct behaviour: the '..' escape is refused, so no foreign checkpoint leaks.
    assert snap["run"]["checkpoint"] == {}
    assert snap["run"].get("step", 0) != 99


# ----------------------------------------------------------------------------
# ui/__main__.py + ui.server.main() CLI entrypoint.
# ----------------------------------------------------------------------------


def test_main_help_exits_zero():
    # WHY: argparse --help raises SystemExit(0); pin that the CLI parser is wired.
    with pytest.raises(SystemExit) as excinfo:
        ui_server.main(["--help"])
    assert excinfo.value.code == 0


def test_main_bad_arg_exits_nonzero():
    # WHY: an unknown flag makes argparse exit with code 2.
    with pytest.raises(SystemExit) as excinfo:
        ui_server.main(["--nonsense"])
    assert excinfo.value.code == 2


def test_main_serves_then_shuts_down_cleanly_on_port_zero(monkeypatch):
    # WHY: main() boots a real server on an ephemeral port and returns 0 after a
    #      KeyboardInterrupt-equivalent shutdown — driven without an LLM.
    started = {}
    real_server_cls = ui_server.AgentUIServer

    class OneShotServer(real_server_cls):  # type: ignore[misc, valid-type]
        def serve_forever(self, poll_interval=0.5):  # noqa: ANN001
            started["address"] = self.server_address
            # Simulate Ctrl-C immediately so main() runs its finally/cleanup path.
            raise KeyboardInterrupt

    monkeypatch.setattr(ui_server, "AgentUIServer", OneShotServer)
    rc = ui_server.main(["--host", "127.0.0.1", "--port", "0"])
    assert rc == 0
    assert started["address"][0] == "127.0.0.1"


def test_dunder_main_module_reexports_main():
    # WHY: ui/__main__.py must re-export the same main callable (0% -> covered import).
    assert ui_main.main is ui_server.main


# ----------------------------------------------------------------------------
# Pure-function error/boundary branches (complement tests/test_ui_server.py).
# ----------------------------------------------------------------------------


def test_read_json_returns_none_on_bad_inputs(tmp_path):
    # WHY: _read_json swallows missing/garbage/non-dict JSON and returns None.
    missing = tmp_path / "nope.json"
    assert ui_server._read_json(missing) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert ui_server._read_json(bad) is None
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, not a dict
    assert ui_server._read_json(arr) is None
    ok = tmp_path / "ok.json"
    ok.write_text('{"a": 1}', encoding="utf-8")
    assert ui_server._read_json(ok) == {"a": 1}


def test_read_events_missing_file_is_empty_and_tail_limited(tmp_path):
    # WHY: _read_events returns [] for a missing file and only the last `limit` lines.
    assert ui_server._read_events(tmp_path / "absent.jsonl") == []
    path = tmp_path / "events.jsonl"
    lines = [json.dumps({"i": i}) for i in range(10)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tail = ui_server._read_events(path, limit=3)
    assert [e["i"] for e in tail] == [7, 8, 9]


def test_tree_snapshot_marks_symlink_nodes(tmp_path, monkeypatch):
    # WHY: a symlink child is reported with type "symlink" and not descended into.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "real.txt").write_text("x\n", encoding="utf-8")
    link = tmp_path / "alias"
    try:
        link.symlink_to(tmp_path / "real.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    snap = ui_server.tree_snapshot("workspace")
    kinds = {child["name"]: child["type"] for child in snap["tree"]["children"]}
    assert kinds["alias"] == "symlink"
    assert kinds["real.txt"] == "file"


def test_tree_snapshot_prunes_hidden_project_dirs(tmp_path, monkeypatch):
    # WHY: project-scope tree omits IGNORED_DIRS (e.g. __pycache__) entirely.
    monkeypatch.setattr(ui_server, "PROJECT_DIR", tmp_path)
    (tmp_path / "keep.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "junk.pyc").write_bytes(b"\x00")
    snap = ui_server.tree_snapshot("project")
    names = {child["name"] for child in snap["tree"]["children"]}
    assert "keep.py" in names
    assert "__pycache__" not in names


def test_tree_snapshot_truncates_at_max_entries(tmp_path, monkeypatch):
    # WHY: the MAX_TREE_ENTRIES cap sets truncated=True and stops walking.
    monkeypatch.setattr(ui_server, "workspace_dir", lambda: tmp_path)
    monkeypatch.setattr(ui_server, "MAX_TREE_ENTRIES", 3)
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("x\n", encoding="utf-8")
    snap = ui_server.tree_snapshot("workspace")
    assert snap["truncated"] is True
    assert snap["entries"] == 3


def test_run_summary_survives_stat_oserror(tmp_path, monkeypatch):
    # WHY: _run_summary tolerates an OSError from stat() -> modified_at None, no crash.
    #      Use a Path subclass whose stat() raises only for THIS run dir.
    run = tmp_path / "20240101_000000_zzzz"
    run.mkdir()
    (run / "checkpoint.json").write_text(json.dumps({"task": "t", "step": 1}), encoding="utf-8")
    monkeypatch.setattr(ui_server, "runs_dir", lambda: tmp_path)

    real_stat = ui_server.Path.stat
    target = str(run)

    def patched_stat(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
        if str(self) == target:
            raise OSError("stat denied")
        return real_stat(self, *a, **k)

    monkeypatch.setattr(ui_server.Path, "stat", patched_stat)
    summary = ui_server._run_summary(run, StubController())
    assert summary["run_id"] == run.name
    assert summary["modified_at"] is None


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"prompt": "x" * (ui_server.MAX_PROMPT_CHARS + 1)}, "prompt exceeds"),
        ({"prompt": "ok", "system_prompt": "s" * (ui_server.MAX_SYSTEM_PROMPT_CHARS + 1)}, "system_prompt exceeds"),
        ({"prompt": "ok", "system_prompt": 12345}, "must be a string"),
    ],
)
def test_post_char_limit_and_type_branches(ui_server_with_stub, body, fragment):
    # WHY: cover the prompt/system_prompt size+type rejection branches over HTTP.
    base, controller, _ = ui_server_with_stub
    status, _, payload = _request(base, "/api/runs", body=body, headers={"Content-Type": "application/json"})
    assert status == 400
    assert fragment in payload["error"]
    assert controller.started == []
