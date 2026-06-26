"""Smoke: demo.py / run_eval.py / run_server.py entrypoints import and run without crashing.

Repo root is on sys.path (conftest), so these are top-level modules. Deterministic:
FakeLLM only, no --real, ephemeral server port, no sleeps.
"""
import json
import threading
import urllib.request

import pytest

import demo
import run_eval
from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.eval import render_report, run_suite
from dragzero.server import Run, make_server


# --- demo.py -------------------------------------------------------------- #
def test_demo_main_runs_and_prints_tree(capsys):
    demo.main()  # must not raise on the deterministic FakeLLM script
    out = capsys.readouterr().out
    assert out.strip()  # printed something
    assert "execution tree" in out
    assert "event log" in out
    # the planner delegates to the researcher in demo.SCRIPT — both land in the tree
    assert "gather 3 sources" in out


def test_demo_script_is_a_by_role_callable():
    # demo.SCRIPT is built via by_role(...) -> a callable the FakeLLM consumes
    assert callable(demo.SCRIPT)
    planner = demo.SCRIPT({"role": "planner"})
    assert planner["decision"]["mode"] == "delegate"
    assert planner["decision"]["target"] == "researcher"


# --- run_eval.py ---------------------------------------------------------- #
def test_run_eval_deterministic_suite_renders_report():
    # use the module's own deterministic factory + SUITE — the no-`--real` path
    results = run_suite(run_eval.SUITE, run_eval._deterministic_factory, trials=1)
    report = render_report(results)
    assert isinstance(report, str) and report.strip()
    # both scenario names from run_eval.SUITE appear in the rendered report
    assert "fix-bug" in report
    assert "trivial-answer" in report
    # the report header columns include a pass% column
    assert "pass%" in report


def test_run_eval_factory_planner_delegates_to_coder():
    llm = run_eval._deterministic_factory(0)
    assert isinstance(llm, FakeLLM)
    planner = llm.complete({"role": "planner", "task": "x", "observations": []})
    assert planner["decision"]["mode"] == "delegate"
    assert planner["decision"]["target"] == "coder"


# --- run_server.py / dragzero.server -------------------------------------- #
def _solo_builder():
    """Minimal single solo-agent run — no tools, no sandbox, finishes immediately."""
    def build():
        llm = FakeLLM(lambda ctx: {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}})
        roster = Roster([Agent("solo", "planner", llm)])
        orch = Orchestrator(roster)
        return orch, roster.by_role_or_id("planner"), None

    return build


@pytest.fixture
def server(tmp_path):
    run = Run(id="run-1", title="smoke", task="do the thing", builder=_solo_builder(), pace=0.0)
    httpd = make_server(run, static_dir=str(tmp_path), host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield port
    httpd.shutdown()


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def test_make_server_session_returns_json_graph(server):
    s = _get(server, "/api/session")
    assert s["id"] == "run-1"
    assert s["title"] == "smoke"
    assert "graph" in s
    # the graph is the UI shape: {root, nodes, edges}
    g = s["graph"]
    assert set(g) == {"root", "nodes", "edges"}
    # the seeded root task is present as a node
    assert g["root"] is not None
    assert any(n["id"] == g["root"] for n in g["nodes"])


def test_make_server_run_endpoint_returns_status_and_graph(server):
    st = _get(server, "/api/runs/run-1")
    assert "graph" in st
    assert st["status"] == "created"  # not started yet
