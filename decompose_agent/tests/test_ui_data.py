"""The UI bridge feeds the Agent-IDE prototype LIVE backend state (no mock)."""
from __future__ import annotations

from decompose_agent import ui_data


def test_agents_are_the_live_node_graph_on_the_ui_slots():
    agents = ui_data.build_project_data()["AGENTS"]
    # the 5 hardcoded UI slot ids stay (the UI's edges/chips reference them)
    assert [a["id"] for a in agents] == ["orchestrator", "planner", "coder", "reviewer", "tester"]
    # filled with the real rag tree's nodes, all PASS (green) after a real solve()
    assert {a["name"] for a in agents} == {"rag", "corpus", "index", "queries", "eval"}
    assert all(a["status"] == "done" and a["color"] == "#3fb9a6" for a in agents)
    # each carries the real worker IDENTITY + real done_when rendered as rules/skills
    assert all("local worker" in a["prompt"] for a in agents)
    assert any("row_count_gte" in r for a in agents for r in a["rules"])
    assert any("row_count_gte" in a["skills"] for a in agents)


def test_project_is_the_real_backend_source_not_the_mock():
    project = ui_data.build_project_data()["PROJECT"]
    assert project["name"] == "decompose_agent"
    assert "decompose_agent/solve.py" in project["files"]
    assert "decompose_agent/gates.py" in project["files"]
    # the UI's hardcoded entry/chip paths are aliased onto real files → no empty panels
    assert project["files"]["src/auth/session.ts"] == project["files"]["decompose_agent/solve.py"]
    assert project["files"]["tests/auth.test.ts"] == project["files"]["decompose_agent/tests/test_solve_recurse.py"]


def test_virtual_chips_carry_real_run_output():
    virtual = ui_data.build_project_data()["VIRTUAL"]
    assert "ai.rag" in virtual["plan.json"]      # the live tree as JSON
    assert "ai.rag" in virtual["report.md"]      # the run report
    assert "Gate-1" in virtual["review.md"]


def test_project_data_js_is_an_importable_es_module():
    js = ui_data.build_project_data_js()
    assert js.startswith("// Generated live")
    for name in ("export const PROJECT = {", "export const AGENTS = [", "export const VIRTUAL = {"):
        assert name in js


def test_agents_carry_node_id_for_live_event_mapping():
    agents = ui_data.build_project_data()["AGENTS"]
    assert {a["nodeId"] for a in agents} == {"ai.rag", "ai.rag.corpus", "ai.rag.index", "ai.rag.queries", "ai.rag.eval"}


def test_journal_sink_streams_each_record(tmp_path):
    from decompose_agent.journal import Journal
    seen = []
    Journal(tmp_path, "r", sink=seen.append).append("n1", {"event": "activated"})
    assert seen[0]["node"] == "n1" and seen[0]["event"] == "activated"


def test_server_solve_into_streams_live_and_finishes_done(tmp_path):
    from decompose_agent import server
    events = []
    final = server._solve_into(server.DEFAULT_TREE, server.DEFAULT_ROOT, events.append)
    kinds = {e["event"] for e in events}
    assert "activated" in kinds and "attempt" in kinds          # live per-node events
    assert all("action" not in e and "reasons" not in e for e in events)  # slimmed (no heavy payload)
    assert final["blocked"] is None and all(s == "done" for s in final["nodes"].values())
