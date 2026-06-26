"""Phase 3 — mid-run join: inject an agent for an empty role mid-session, from the UI.

Scenario: root -> planner -> delegate an EMPTY role -> task_waiting -> Run parks (awaiting, NOT
done) -> POST /join {role} -> orchestrator wakes the parked task -> child runs -> done. The
orchestrator already supports this (join_agent -> _wake_waiting); this phase only grows the Run
lifecycle + endpoints + the await_role / agent_joined WS frames. orchestrator.py stays byte-identical.
"""
import json
import socket
import struct
import threading
import time
import urllib.error
import urllib.request

import pytest

from dragzero import Topology, build_runtime, FakeLLM
from dragzero.adapters.tools_fs import FsSandbox, default_tool_catalog
from dragzero.events import EventType
from dragzero.server import Run, make_server, translate_event
from dragzero.events import Event


# --- a topology that parks: planner delegates to a role with no agent --------- #
PARK_TOPO = {
    "version": 1,
    "nodes": [{"id": "plan", "type": "agent", "role": "planner", "entry": True}],
    "edges": [],
}


def _park_responder(ctx):
    role = ctx["role"]
    if role == "planner":
        return {"plan": {"steps": [], "next": None},
                "decision": {"mode": "delegate", "target": "specialist", "subtask": "specialist work"}}
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}  # specialist, once joined


def _nonpark_responder(ctx):
    role, obs = ctx["role"], ctx["observations"]
    if role == "planner":
        return {"plan": {"steps": [], "next": None},
                "decision": {"mode": "delegate", "target": "coder", "subtask": "do x"}}
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


NONPARK_TOPO = {
    "version": 1,
    "nodes": [
        {"id": "plan", "type": "agent", "role": "planner", "entry": True},
        {"id": "code", "type": "agent", "role": "coder"},
    ],
    "edges": [{"from": "plan", "to": "code", "type": "delegates_to"}],
}


def _builder(topo, responder, tmp):
    def provider():
        return FakeLLM(responder)

    def build():
        sb = FsSandbox(tmp)
        rt = build_runtime(Topology.from_dict(topo), provider(), tool_catalog=default_tool_catalog(), sandbox=sb)
        return rt.orchestrator, rt.entry, sb

    return build, provider


def _park_run(tmp, heartbeat=30.0):
    build, provider = _builder(PARK_TOPO, _park_responder, tmp)
    run = Run(id="run-1", title="park", task="do the thing", builder=build, pace=0.0, llm_provider=provider)
    run._park_heartbeat = heartbeat
    return run


def _wait(pred, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


# --- unit: Run lifecycle (no HTTP) ------------------------------------------ #
def test_parked_run_is_awaiting_not_done(tmp_path):
    """Diagnosis-pin: a parked run must report AWAITING — the old code mis-reported done."""
    run = _park_run(str(tmp_path))
    run.start()
    assert _wait(lambda: run.status == "awaiting"), f"status={run.status}"
    assert run.orch.waiting_count() == 1
    assert run.done is False
    assert run.status != "done"
    run.close()


def test_join_resumes_parked_run_to_done(tmp_path):
    run = _park_run(str(tmp_path))
    run.start()
    assert _wait(lambda: run.status == "awaiting")
    assert run.join("specialist") is True
    assert _wait(lambda: run.done and run.status == "done"), f"status={run.status}"
    # agent_joined logged BETWEEN task_waiting and the child's completion
    types = [e.type for e in run.orch.log.events()]
    assert EventType.TASK_WAITING in types and EventType.AGENT_JOINED in types
    assert types.index(EventType.TASK_WAITING) < types.index(EventType.AGENT_JOINED)
    assert types.index(EventType.AGENT_JOINED) < max(i for i, t in enumerate(types) if t == EventType.TASK_COMPLETED)


def test_timeout_cycle_stays_awaiting(tmp_path):
    """A park heartbeat cycle re-emits a snapshot and stays awaiting — never falls through to run_end."""
    run = _park_run(str(tmp_path), heartbeat=0.1)
    run.start()
    assert _wait(lambda: run.status == "awaiting")
    n0 = len(run.frames)
    assert _wait(lambda: len(run.frames) > n0, timeout=1.0)  # heartbeat snapshot emitted
    assert run.status == "awaiting" and run.done is False
    run.close()


def test_join_noop_when_not_awaiting(tmp_path):
    run = _park_run(str(tmp_path))
    run.start()
    assert _wait(lambda: run.status == "awaiting")
    run.join("specialist")
    assert _wait(lambda: run.done)
    assert run.join("specialist") is False  # nothing parked -> no-op


def test_second_start_during_awaiting_is_noop(tmp_path):
    run = _park_run(str(tmp_path))
    run.start()
    assert _wait(lambda: run.status == "awaiting")
    orch_id = id(run.orch)
    run.start()  # must NOT rebuild / orphan the parked thread
    assert id(run.orch) == orch_id
    assert run.status == "awaiting"
    run.close()


def test_reset_during_awaiting_is_noop(tmp_path):
    run = _park_run(str(tmp_path))
    run.start()
    assert _wait(lambda: run.status == "awaiting")
    orch_id = id(run.orch)
    run.reset()
    assert id(run.orch) == orch_id  # awaiting is busy; reset is guarded
    run.close()


def test_cancel_during_awaiting_exits_cleanly(tmp_path):
    run = _park_run(str(tmp_path))
    run.start()
    assert _wait(lambda: run.status == "awaiting")
    run.close()
    assert _wait(lambda: run.done and run.status == "cancelled"), f"status={run.status}"
    assert run.status != "done"  # never a fake done


def test_nonpark_topology_runs_to_done_without_awaiting(tmp_path):
    build, provider = _builder(NONPARK_TOPO, _nonpark_responder, str(tmp_path))
    run = Run(id="run-1", title="nonpark", task="x", builder=build, pace=0.0, llm_provider=provider)
    seen = []
    orig = run._set_status if hasattr(run, "_set_status") else None
    run.start()
    assert _wait(lambda: run.done)
    assert run.status == "done"  # never stuck awaiting


# --- translation contract (DEC-A5: TASK_WAITING -> await_role, +agent_joined) - #
def test_translate_task_waiting_is_await_role():
    out = translate_event(Event(EventType.TASK_WAITING, task_id="t2", payload={"target": "specialist"}))
    assert [f["data"]["type"] for f in out] == ["await_role"]
    assert out[0]["data"]["payload"]["role"] == "specialist"


def test_translate_agent_joined():
    out = translate_event(Event(EventType.AGENT_JOINED, agent_id="specialist", payload={"role": "specialist"}))
    assert [f["data"]["type"] for f in out] == ["agent_joined"]
    assert out[0]["data"]["payload"]["role"] == "specialist"


# --- HTTP + WS over the wire ------------------------------------------------- #
def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture
def park_server(tmp_path):
    run = _park_run(str(tmp_path))
    httpd = make_server(run, static_dir=str(tmp_path), host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield port, run
    run.close()
    httpd.shutdown()


def test_http_park_join_flow(park_server):
    port, _ = park_server
    _post(port, "/api/runs/run-1/start")
    assert _wait(lambda: _get(port, "/api/runs/run-1")["status"] == "awaiting")
    res = _post(port, "/api/runs/run-1/join", {"role": "specialist"})
    assert res["ok"] is True and res["woke"] is True
    assert _wait(lambda: _get(port, "/api/runs/run-1")["status"] == "done")
    g = _get(port, "/api/runs/run-1")["graph"]
    assert len(g["nodes"]) >= 2  # root + the resumed specialist child


def test_http_cancel(park_server):
    port, run = park_server
    _post(port, "/api/runs/run-1/start")
    assert _wait(lambda: _get(port, "/api/runs/run-1")["status"] == "awaiting")
    _post(port, "/api/runs/run-1/cancel")
    assert _wait(lambda: run.status == "cancelled")


# --- WS: await_role + agent_joined arrive, in order -------------------------- #
def _ws_connect(port, path):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    _, _, rest = buf.partition(b"\r\n\r\n")
    return s, bytearray(rest)


def _read_frames(s, leftover, timeout=6):
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
            ln = need(1)[0] & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", need(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", need(8))[0]
            payload = need(ln) if ln else b""
            if (b0 & 0x0F) == 0x8:
                break
            frames.append(json.loads(payload.decode()))
            if frames[-1].get("type") == "run_finished":
                break
    except (socket.timeout, EOFError):
        pass
    return frames


def test_ws_await_role_then_agent_joined(park_server):
    port, _ = park_server
    _post(port, "/api/runs/run-1/start")
    assert _wait(lambda: _get(port, "/api/runs/run-1")["status"] == "awaiting")
    s, leftover = _ws_connect(port, "/api/runs/run-1/events")  # backlog carries await_role
    _post(port, "/api/runs/run-1/join", {"role": "specialist"})  # then live agent_joined ... run_finished
    frames = _read_frames(s, leftover)
    s.close()
    evs = [f["data"]["type"] for f in frames if f.get("type") == "event"]
    assert "await_role" in evs
    assert "agent_joined" in evs
    assert evs.index("await_role") < evs.index("agent_joined")
    assert "run_finished" in [f.get("type") for f in frames]
