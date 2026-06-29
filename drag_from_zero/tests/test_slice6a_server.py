"""Slice 6a — the HTTP/WS server adapter that serves the Agent-IDE UI.

Starts the real stdlib server on an ephemeral port and exercises the exact
contract the UI's Component class calls: /api/session, /api/runs/{id}[/reset|
/start|/artifacts|/artifact], and the WS event stream. A hand-rolled stdlib WS
client asserts the translated frames arrive. No browser, no extra deps.
"""
import json
import socket
import struct
import threading
import time
import urllib.request

import pytest

from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools
from dragzero.server import Run, make_server


def _responder(ctx):
    role, obs = ctx["role"], ctx["observations"]
    if role == "planner":
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": "coder", "subtask": "do x"}}
    if role == "coder":
        if not obs:
            return {"action": {"type": "tool", "tool": "read_file", "args": {"path": "src/x.ts"}}}
        if len(obs) == 1:
            return {"action": {"type": "tool", "tool": "write_file", "args": {"path": "out.txt", "content": "done"}}}
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _builder(tmp):
    def build():
        sandbox = FsSandbox(tmp)
        sandbox.write("src/x.ts", "export const x = 1\n")
        llm = FakeLLM(_responder)
        roster = Roster([Agent("planner", "planner", llm), Agent("coder", "coder", llm)])
        orch = Orchestrator(roster, tools=build_fs_tools(), sandbox=sandbox)
        return orch, roster.by_role_or_id("planner"), sandbox

    return build


@pytest.fixture
def server(tmp_path):
    run = Run(id="run-1", title="t", task="do the thing", builder=_builder(str(tmp_path)), pace=0.0)
    httpd = make_server(run, static_dir=str(tmp_path), host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield port
    httpd.shutdown()


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(port, path):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _await_done(port, rid="run-1"):
    for _ in range(200):
        st = _get(port, f"/api/runs/{rid}")
        if st["status"] in ("done", "blocked"):
            return st
        time.sleep(0.02)
    raise AssertionError("run did not finish")


# --- REST contract -------------------------------------------------------- #
def test_session_returns_graph_the_ui_can_render(server):
    s = _get(server, "/api/session")
    assert s["id"] == "run-1" and s["title"] == "t" and "graph" in s
    g = s["graph"]
    assert g["root"] is not None and any(n["id"] == g["root"] for n in g["nodes"])
    for n in g["nodes"]:  # the fields the UI reads without guards
        assert isinstance(n["done_when"], list)
        assert isinstance(n["children"], list)
        assert isinstance(n["depends_on"], list)
        assert "goal" in n and "mu" in n


def test_start_grows_and_completes_the_tree(server):
    _post(server, "/api/runs/run-1/reset")
    _post(server, "/api/runs/run-1/start")
    st = _await_done(server)
    assert st["status"] == "done"
    g = st["graph"]
    assert len(g["nodes"]) >= 2  # planner decomposed into a coder subtask
    assert any(e["kind"] == "child" for e in g["edges"])


def test_artifacts_list_and_read(server):
    _post(server, "/api/runs/run-1/reset")
    _post(server, "/api/runs/run-1/start")
    _await_done(server)
    arts = _get(server, "/api/runs/run-1/artifacts")
    paths = [a["path"] for a in arts]
    assert "out.txt" in paths
    assert _get(server, "/api/runs/run-1/artifact?path=out.txt")["content"] == "done"


def test_unknown_run_is_404(server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        _get(server, "/api/runs/nope")
    assert ei.value.code == 404


# --- WebSocket stream ----------------------------------------------------- #
def _ws_connect(port, path):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    req = (
        f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    assert b"101" in head.split(b"\r\n")[0], head
    return s, bytearray(rest)


def _read_frames(s, leftover, timeout=5):
    s.settimeout(timeout)
    frames = []

    def need(n):
        while len(leftover) < n:
            chunk = s.recv(4096)
            if not chunk:
                raise EOFError
            leftover.extend(chunk)
        out = bytes(leftover[:n])
        del leftover[:n]
        return out

    try:
        while True:
            b0 = need(1)[0]
            b1 = need(1)[0]
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", need(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", need(8))[0]
            payload = need(ln) if ln else b""
            if (b0 & 0x0F) == 0x8:  # close
                break
            frames.append(json.loads(payload.decode()))
            if frames[-1].get("type") == "run_finished":
                break
    except (socket.timeout, EOFError):
        pass
    return frames


def test_ws_streams_translated_frames(server):
    _post(server, "/api/runs/run-1/reset")
    _post(server, "/api/runs/run-1/start")
    s, leftover = _ws_connect(server, "/api/runs/run-1/events")
    frames = _read_frames(s, leftover)
    s.close()

    kinds = [f.get("type") for f in frames]
    assert "snapshot" in kinds
    assert "run_finished" in kinds

    ev = [f["data"]["type"] for f in frames if f.get("type") == "event"]
    assert "run_start" in ev
    assert "activate" in ev          # a task started
    assert "decompose" in ev         # planner spawned the coder subtask
    assert "propose" in ev           # coder called a tool
    assert "verdict" in ev           # a task completed

    # the final snapshot the UI would render is a coherent graph
    snaps = [f["graph"] for f in frames if f.get("type") == "snapshot"]
    assert snaps[-1]["root"] is not None and len(snaps[-1]["nodes"]) >= 2
