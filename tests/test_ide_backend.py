"""Tests for the live IDE backend (ui/ide): file jail, diff, session fold, event bridge.

The IDE backend is the load-bearing new surface — it lets the browser write to disk and runs the
agent — so the path jail and the redaction-preserving event path are pinned here. All offline: no
LLM, no real agent run; the runner is exercised only through its pure pieces.
"""
from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection

import pytest

from control.snapshot import build_snapshot


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    # ui.ide.files calls workspace_dir() (which reads the env) on every op, so the override takes
    # effect without reloading — no module reload, no duplicate FileOpError class.
    import ui.ide.files as files

    return ws, files


# ── path jail ────────────────────────────────────────────────────────────────
@pytest.mark.security
@pytest.mark.parametrize("evil", ["../escape.txt", "..\\win.txt", "C:/abs.txt", "/etc/passwd"])
def test_jail_rejects_escapes(workspace, evil):
    _, files = workspace
    with pytest.raises(files.FileOpError):
        files.read_file("workspace", evil)
    with pytest.raises(files.FileOpError):
        files.write_file("workspace", evil, "x")


@pytest.mark.security
@pytest.mark.parametrize("name", [".env", ".env.local", ".env.production", ".npmrc", ".git-credentials", "id_rsa", "id_ecdsa", "secret.pem"])
def test_sensitive_files_blocked(workspace, name):
    ws, files = workspace
    (ws / name).write_text("SECRET=1", encoding="utf-8")
    with pytest.raises(files.FileOpError):
        files.read_file("workspace", name)
    with pytest.raises(files.FileOpError):
        files.write_file("workspace", name, "x")


# ── CRUD + diff ──────────────────────────────────────────────────────────────
def test_write_read_roundtrip_normalizes_crlf(workspace):
    _, files = workspace
    files.create_path("workspace", "a/b.py", "file")
    files.write_file("workspace", "a/b.py", "x = 1\r\ny = 2\r\n")
    got = files.read_file("workspace", "a/b.py")
    assert got["content"] == "x = 1\ny = 2\n"
    assert got["language"] == "python"


def test_rename_and_delete(workspace):
    _, files = workspace
    files.create_path("workspace", "old.txt", "file")
    files.rename_path("workspace", "old.txt", "new.txt")
    assert files.read_file("workspace", "new.txt")["name"] == "new.txt"
    files.delete_path("workspace", "new.txt")
    with pytest.raises(files.FileOpError):
        files.read_file("workspace", "new.txt")


def test_diff_added_modified_deleted(workspace):
    ws, files = workspace
    (ws / "keep.txt").write_text("one\ntwo\n", encoding="utf-8")
    (ws / "gone.txt").write_text("bye\n", encoding="utf-8")
    baseline = files.snapshot_baseline("workspace")
    # mutate: add, modify, delete
    files.write_file("workspace", "fresh.txt", "new\n")
    files.write_file("workspace", "keep.txt", "one\ntwo\nthree\n")
    files.delete_path("workspace", "gone.txt")
    diffs = {d["path"]: d for d in files.compute_diffs(baseline, "workspace")}
    assert diffs["fresh.txt"]["status"] == "added"
    assert diffs["keep.txt"]["status"] == "modified" and diffs["keep.txt"]["additions"] == 1
    assert diffs["gone.txt"]["status"] == "deleted"
    assert "+three" in diffs["keep.txt"]["diff"]


# ── session: seq + redaction + fold ──────────────────────────────────────────
def test_session_emit_redacts_and_folds():
    from ui.ide.session import IdeSession

    s = IdeSession("t1_demo")
    s.emit("loop.team_composed", {"selected": ["agent:root"]})
    # a secret in the payload must be masked in the streamed ui_payload (never raw)
    s.emit("loop.tool", {"tool": "fs_write", "ok": True, "status": "ok", "api_key": "sk-123"})
    events = s.events()
    assert [e["seq"] for e in events] == [1, 2]
    tool_ui = events[1]["ui_payload"]
    assert tool_ui["api_key"] == "[REDACTED]"
    snap = build_snapshot(events, session_id="t1_demo")
    assert snap.status == "waiting_tool"
    assert any(a.agent_id == "agent:root" for a in snap.agents)


# ── bridge: tool.requested+completed → one loop.tool with the path ───────────
def test_bridge_correlates_path_and_emits_one_tool_event():
    from ui.ide.bridge import KernelEventBridge
    from ui.ide.session import IdeSession

    s = IdeSession("t1_demo")
    bridge = KernelEventBridge(s)
    bridge.subscriber("tool.requested", {"request_id": "r1", "tool": "fs_write", "args": {"path": "src/app.py"}})
    bridge.subscriber("tool.completed", {"request_id": "r1", "tool": "fs_write", "ok": True})
    loop_tools = [e for e in s.events() if e["event_type"] == "loop.tool"]
    assert len(loop_tools) == 1
    assert loop_tools[0]["ui_payload"] == {"tool": "fs_write", "ok": True, "status": "ok", "path": "src/app.py"}


# ── server: token gate + file write over a real socket ───────────────────────
@pytest.mark.integration
def test_server_command_token_and_file_write(workspace):
    import ui.ide.server as server_mod

    server = server_mod.IdeControlServer(("127.0.0.1", 0), token="tok", session_id="t1_demo")
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        # bad token on the command channel → 401
        bad = _post(port, "/api/commands", {"command_type": "SubmitPrompt"}, token="wrong")
        assert bad[0] == 401

        # the FILE surface also requires the token (no token → 401), not just the command channel
        assert _request(port, "PUT", "/api/files/write",
                        {"scope": "workspace", "path": "x.txt", "content": "no"}, token=None)[0] == 401
        assert _get(port, "/api/files/read?scope=workspace&path=note.txt", token=None)[0] == 401
        assert _get(port, "/api/files/tree?scope=workspace", token=None)[0] == 401

        # with the token: write then read back
        wrote = _request(port, "PUT", "/api/files/write",
                         {"scope": "workspace", "path": "note.txt", "content": "hi\n"}, token="tok")
        assert wrote[0] == 200 and wrote[1]["ok"] is True
        read = _get(port, "/api/files/read?scope=workspace&path=note.txt", token="tok")
        assert read[1]["content"] == "hi\n"

        # traversal rejected (token present, jail fires)
        evil = _get(port, "/api/files/read?scope=workspace&path=../../etc/passwd", token="tok")
        assert evil[0] in (400, 403)
    finally:
        server.shutdown()
        server.server_close()


def _conn(port):
    return HTTPConnection("127.0.0.1", port, timeout=5)


def _request(port, method, path, body=None, token=None):
    conn = _conn(port)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Auth-Token"] = token
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, (json.loads(raw) if raw else {})


def _get(port, path, token=None):
    return _request(port, "GET", path, token=token)


def _post(port, path, body, token=None):
    return _request(port, "POST", path, body, token=token)
