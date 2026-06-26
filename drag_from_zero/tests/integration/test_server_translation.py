"""Pure server-side translation: build_graph / translate_event / _final_status, no socket.

The over-the-wire path lives in tests/test_slice6a_server.py; here we drive the three
pure functions directly off a hand-built EventLog (and a sandbox for the gate tests).
"""
import pytest

from dragzero import EventLog, EventType, reduce
from dragzero.events import Event
from dragzero.adapters.tools_fs import FsSandbox
from dragzero.server import build_graph, translate_event, _final_status


# --- log builders --------------------------------------------------------- #
def _root_event(task_id="root", description="ship the thing"):
    return Event(EventType.ROOT_TASK_CREATED, task_id=task_id,
                 payload={"description": description})


def _log_root_child_complete():
    """root started -> spawns a child (agent=coder) -> child writes -> both complete."""
    log = EventLog()
    log.append(_root_event())
    log.append(Event(EventType.TASK_STARTED, task_id="root", agent_id="planner"))
    log.append(Event(EventType.SUBTASK_SPAWNED, task_id="child", agent_id="coder",
                     payload={"parent": "root", "subtask": "write the file"}))
    log.append(Event(EventType.TASK_STARTED, task_id="child", agent_id="coder"))
    log.append(Event(EventType.TOOL_CALLED, task_id="child",
                     payload={"tool": "write_file", "args": {"path": "out.txt"}}))
    log.append(Event(EventType.TOOL_RESULT, task_id="child",
                     payload={"tool": "write_file", "ok": True}))
    log.append(Event(EventType.TASK_COMPLETED, task_id="child", payload={"result": "done"}))
    log.append(Event(EventType.TASK_COMPLETED, task_id="root", payload={"result": "done"}))
    return log


def _log_completed_root():
    log = EventLog()
    log.append(_root_event())
    log.append(Event(EventType.TASK_STARTED, task_id="root", agent_id="planner"))
    log.append(Event(EventType.TASK_COMPLETED, task_id="root", payload={"result": "done"}))
    return log


# --- build_graph: shape + mu + edges (no spec, no sandbox) ---------------- #
def test_build_graph_shape_and_fields():
    g = build_graph(_log_root_child_complete())
    assert set(g) == {"root", "nodes", "edges"}
    assert g["root"] == "root"
    for n in g["nodes"]:
        assert isinstance(n["goal"], str)
        assert isinstance(n["mu"], int)
        assert isinstance(n["done_when"], list)
        assert n["verdict"] == "unverified"   # no spec => honest unverified
        assert n["depends_on"] == []
        assert isinstance(n["children"], list)
        assert set(n["runtime"]) == {"status", "agent"}


def test_build_graph_mu_no_spec_is_subtree_node_count():
    g = build_graph(_log_root_child_complete())
    by_id = {n["id"]: n for n in g["nodes"]}
    # no spec => every node's local mu == 1, so a node's mu == size of its subtree.
    assert by_id["child"]["mu"] == 1                  # leaf
    assert by_id["root"]["mu"] == len(g["nodes"])     # root subtree == whole tree (2)
    assert by_id["root"]["mu"] == 2


def test_build_graph_child_yields_child_edge():
    g = build_graph(_log_root_child_complete())
    child_edges = [e for e in g["edges"] if e["kind"] == "child"]
    assert {"source": "root", "target": "child", "kind": "child"} in child_edges
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id["root"]["children"] == ["child"]


def test_build_graph_empty_log_is_null_graph():
    assert build_graph(EventLog()) == {"root": None, "nodes": [], "edges": []}


# --- translate_event: our vocabulary -> the UI's ------------------------- #
def test_translate_task_started_is_activate():
    out = translate_event(Event(EventType.TASK_STARTED, task_id="root"))
    assert [f["data"]["type"] for f in out] == ["activate"]
    assert out[0]["data"]["node_id"] == "root"


def test_translate_tool_called_is_propose():
    ev = Event(EventType.TOOL_CALLED, task_id="child",
               payload={"tool": "write_file", "args": {"path": "out.txt"}})
    out = translate_event(ev)
    assert [f["data"]["type"] for f in out] == ["propose"]
    assert "write_file" in out[0]["data"]["payload"]["action"]


def test_translate_subtask_spawned_is_decompose_on_parent():
    ev = Event(EventType.SUBTASK_SPAWNED, task_id="child", agent_id="coder",
               payload={"parent": "root", "subtask": "do x"})
    out = translate_event(ev)
    assert [f["data"]["type"] for f in out] == ["decompose"]
    assert out[0]["data"]["node_id"] == "root"          # node_id is the PARENT
    assert out[0]["data"]["payload"]["children"] == ["child"]


def test_translate_task_waiting_is_block():
    ev = Event(EventType.TASK_WAITING, task_id="root", payload={"target": "child"})
    out = translate_event(ev)
    assert [f["data"]["type"] for f in out] == ["block"]


def test_translate_task_completed_no_verdict_fn_passes_true():
    ev = Event(EventType.TASK_COMPLETED, task_id="root", payload={"result": "done"})
    out = translate_event(ev)
    assert [f["data"]["type"] for f in out] == ["verdict"]
    assert out[0]["data"]["payload"]["passed"] is True


def test_translate_task_failed_is_verdict_passed_false():
    ev = Event(EventType.TASK_FAILED, task_id="root", payload={"error": "boom"})
    out = translate_event(ev)
    assert [f["data"]["type"] for f in out] == ["verdict"]
    assert out[0]["data"]["payload"]["passed"] is False


def test_translate_hook_blocked_is_block():
    ev = Event(EventType.HOOK_BLOCKED, task_id="root", payload={"reason": "nope"})
    out = translate_event(ev)
    assert [f["data"]["type"] for f in out] == ["block"]


def test_translate_budget_exceeded_is_block():
    ev = Event(EventType.BUDGET_EXCEEDED, task_id="root", payload={"used": 5, "limit": 4})
    out = translate_event(ev)
    assert [f["data"]["type"] for f in out] == ["block"]


def test_translate_untranslated_type_is_empty():
    # PLAN_PRODUCED has no UI mapping -> no frames.
    assert translate_event(Event(EventType.PLAN_PRODUCED, task_id="root")) == []


# --- build_graph with a spec: code re-derives the verdict over the sandbox - #
def test_completed_node_missing_artifact_fails_and_blocks(tmp_path):
    sandbox = FsSandbox(str(tmp_path))           # artifact NOT written
    spec = {"__root__": [{"check": "file_exists", "artifact": "out.txt"}]}
    g = build_graph(_log_completed_root(), sandbox=sandbox, spec=spec)
    root = next(n for n in g["nodes"] if n["id"] == "root")
    assert root["verdict"] == "FAIL"               # code overrides the model's "done" claim
    assert root["runtime"]["status"] == "blocked"


def test_completed_node_with_artifact_passes_and_is_done(tmp_path):
    sandbox = FsSandbox(str(tmp_path))
    sandbox.write("out.txt", "real content\n")     # non-empty artifact present
    spec = {"__root__": [{"check": "file_exists", "artifact": "out.txt"}]}
    g = build_graph(_log_completed_root(), sandbox=sandbox, spec=spec)
    root = next(n for n in g["nodes"] if n["id"] == "root")
    assert root["verdict"] == "PASS"
    assert root["runtime"]["status"] == "done"


def test_spec_keyed_by_agent_id(tmp_path):
    """A child node's gate is found via its agent_id when not keyed by node id."""
    sandbox = FsSandbox(str(tmp_path))
    sandbox.write("out.txt", "written\n")
    spec = {"coder": [{"check": "file_exists", "artifact": "out.txt"}]}
    g = build_graph(_log_root_child_complete(), sandbox=sandbox, spec=spec)
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id["child"]["verdict"] == "PASS"       # matched by agent_id "coder"
    assert by_id["root"]["verdict"] == "unverified"  # root has no authored criteria


# --- _final_status -------------------------------------------------------- #
def test_final_status_completed_root_no_spec_is_done():
    assert _final_status(_log_completed_root()) == "done"
