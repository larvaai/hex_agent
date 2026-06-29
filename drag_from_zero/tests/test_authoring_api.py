"""Phase 1 — authoring API boundary (topology CRUD + run-from-topology + multi-run).

Exercises the substrate-agnostic REST surface the React Flow UI reads/writes:
POST/GET /api/topology, POST /api/runs (from a posted topology), driven over the
wire by the same stdlib HTTP harness the Slice-6a tests use. The LLM is a
*factory* (callable minted per run) — two runs must never share one instance.
Core (orchestrator/read_model/topology/wiring) is untouched; this only opens
reader/factory endpoints around it.
"""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools
from dragzero.server import Run, make_server


# --- responders ----------------------------------------------------------- #
def _default_responder(ctx):
    role, obs = ctx["role"], ctx["observations"]
    if role == "planner":
        return {"plan": {"steps": [], "next": None},
                "decision": {"mode": "delegate", "target": "coder", "subtask": "do x"}}
    if role == "coder":
        if not obs:
            return {"action": {"type": "tool", "tool": "write_file", "args": {"path": "out.txt", "content": "done"}}}
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _default_run_builder(tmp):
    def build():
        sandbox = FsSandbox(tmp)
        llm = FakeLLM(_default_responder)
        roster = Roster([Agent("planner", "planner", llm), Agent("coder", "coder", llm)])
        orch = Orchestrator(roster, tools=build_fs_tools(), sandbox=sandbox)
        return orch, roster.by_role_or_id("planner"), sandbox

    return build


# --- fixtures ------------------------------------------------------------- #
@pytest.fixture
def server(tmp_path):
    """New-style server: a default run + a recording llm-factory for created runs."""
    created = []

    def provider():
        llm = FakeLLM(_default_responder)
        created.append(llm)
        return llm

    run = Run(id="run-1", title="default", task="do the thing",
              builder=_default_run_builder(str(tmp_path / "sb")), pace=0.0)
    httpd = make_server(run, static_dir=str(tmp_path), host="127.0.0.1", port=0,
                        llm_provider=provider)
    httpd.app.created_llms = created  # type: ignore[attr-defined]
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield port, created
    httpd.shutdown()


@pytest.fixture
def backcompat_server(tmp_path):
    """Old-style make_server(run, static_dir=...) — no new kwargs at all."""
    run = Run(id="run-1", title="t", task="do the thing",
              builder=_default_run_builder(str(tmp_path / "sb")), pace=0.0)
    httpd = make_server(run, static_dir=str(tmp_path), host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield port
    httpd.shutdown()


# --- stdlib HTTP helpers -------------------------------------------------- #
def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _post_expect(port, path, body):
    """POST that may 4xx; returns (code, body_dict)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _await_done(port, rid):
    for _ in range(300):
        st = _get(port, f"/api/runs/{rid}")
        if st["status"] in ("done", "blocked"):
            return st
        time.sleep(0.02)
    raise AssertionError("run did not finish")


# topology fragments --------------------------------------------------------- #
_AGENT_TOPO = {
    "version": 1,
    "nodes": [
        {"id": "plan", "type": "agent", "role": "planner", "entry": True, "ui": {"position": {"x": 10, "y": 20}}},
        {"id": "code", "type": "agent", "role": "coder", "ui": {"position": {"x": 200, "y": 20}}},
        {"id": "t_write", "type": "tool", "tool": "write_file"},
    ],
    "edges": [{"from": "plan", "to": "code", "type": "delegates_to"}],
}


# --- back-compat: the 5 old call sites must keep working ------------------ #
def test_backcompat_session_renders(backcompat_server):
    s = _get(backcompat_server, "/api/session")
    assert s["id"] == "run-1" and "graph" in s
    g = s["graph"]
    assert g["root"] is not None
    for n in g["nodes"]:  # the fields the UI reads without guards
        assert isinstance(n["done_when"], list)
        assert isinstance(n["children"], list)
        assert isinstance(n["depends_on"], list)
        assert "goal" in n and "mu" in n and "verdict" in n


# --- POST/GET /api/topology ----------------------------------------------- #
def test_post_topology_valid_returns_id_and_roundtrips(server):
    port, _ = server
    code, body = _post_expect(port, "/api/topology", _AGENT_TOPO)
    assert code == 200 and body["id"]
    got = _get(port, f"/api/topology/{body['id']}")
    assert got == _AGENT_TOPO  # exact round-trip, incl. node-level ui meta (DEC-A3)


def test_get_topology_lists_seeded_example(server):
    port, _ = server
    listing = _get(port, "/api/topology")
    assert isinstance(listing, list) and len(listing) >= 1
    assert all("id" in t for t in listing)


def test_post_topology_no_agents_is_422(server):
    port, _ = server
    bad = {"version": 1, "nodes": [{"id": "t", "type": "tool", "tool": "read_file"}], "edges": []}
    code, body = _post_expect(port, "/api/topology", bad)
    assert code == 422
    assert any("no agent" in e.lower() for e in body["errors"])


def test_post_topology_edge_to_unknown_node_is_422(server):
    port, _ = server
    bad = {"version": 1,
           "nodes": [{"id": "a", "type": "agent", "role": "planner"}],
           "edges": [{"from": "a", "to": "ghost", "type": "delegates_to"}]}
    code, body = _post_expect(port, "/api/topology", bad)
    assert code == 422
    assert any("unknown node" in e.lower() for e in body["errors"])


# --- POST /api/runs (run from a posted topology) -------------------------- #
def test_run_from_topology_id_runs_to_done(server):
    port, _ = server
    _, t = _post_expect(port, "/api/topology", _AGENT_TOPO)
    code, body = _post_expect(port, "/api/runs", {"topology_id": t["id"], "task": "build it"})
    assert code == 200
    rid = body["id"]
    assert rid != "run-1"
    _post(port, f"/api/runs/{rid}/start")
    st = _await_done(port, rid)
    assert st["status"] == "done"
    g = st["graph"]
    assert len(g["nodes"]) >= 2  # planner decomposed into a coder subtask
    assert any(e["kind"] == "child" for e in g["edges"])


def test_run_inline_topology_unknown_tool_is_422(server):
    port, _ = server
    bad = {"version": 1,
           "nodes": [{"id": "a", "type": "agent", "role": "planner", "entry": True},
                     {"id": "t", "type": "tool", "tool": "no_such_tool"}],
           "edges": []}
    code, body = _post_expect(port, "/api/runs", {"topology": bad, "task": "x"})
    assert code == 422
    assert any("no_such_tool" in e for e in body["errors"])


def test_run_artifacts_listed_and_readable(server):
    port, _ = server
    _, t = _post_expect(port, "/api/topology", _AGENT_TOPO)
    _, body = _post_expect(port, "/api/runs", {"topology_id": t["id"], "task": "build it"})
    rid = body["id"]
    _post(port, f"/api/runs/{rid}/start")
    _await_done(port, rid)
    arts = _get(port, f"/api/runs/{rid}/artifacts")
    assert "out.txt" in [a["path"] for a in arts]
    assert _get(port, f"/api/runs/{rid}/artifact?path=out.txt")["content"] == "done"


def test_multi_run_independent_ids_and_graphs(server):
    port, _ = server
    _, t = _post_expect(port, "/api/topology", _AGENT_TOPO)
    _, a = _post_expect(port, "/api/runs", {"topology_id": t["id"], "task": "one"})
    _, b = _post_expect(port, "/api/runs", {"topology_id": t["id"], "task": "two"})
    assert a["id"] != b["id"] and a["id"] != "run-1" and b["id"] != "run-1"
    # both render an independent graph
    assert _get(port, f"/api/runs/{a['id']}")["graph"]["root"] is not None
    assert _get(port, f"/api/runs/{b['id']}")["graph"]["root"] is not None


def test_provider_is_factory_distinct_per_run(server):
    port, created = server
    _, t = _post_expect(port, "/api/topology", _AGENT_TOPO)
    _post_expect(port, "/api/runs", {"topology_id": t["id"], "task": "one"})
    _post_expect(port, "/api/runs", {"topology_id": t["id"], "task": "two"})
    assert len(created) >= 2
    assert created[0] is not created[1]  # forbid a shared LLM instance across runs
    assert id(created[0]) != id(created[1])
