"""Slice 4 — tool execution + filesystem sandbox.

Agents run a bounded ReAct loop; tool calls are first-class events. The sandbox
confines all paths to a root. Everything stays deterministic on FakeLLM, and the
tool-less path is byte-identical to Slice 1 (proved by the earlier suites).
"""
import pytest

from dragzero import Agent, EventType, FakeLLM, Orchestrator, Roster, ToolRegistry, reduce
from dragzero.adapters.tools_fs import (
    FsSandbox,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
    build_fs_tools,
)


def _tool(name, **args):
    return {"action": {"type": "tool", "tool": name, "args": args}}


def _solo():
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _read_then_solo(path):
    """Responder: step 0 reads a file, step 1 concludes solo."""
    def responder(ctx):
        return _tool("read_file", path=path) if not ctx["observations"] else _solo()
    return FakeLLM(responder)


def _orch(tools, sandbox, llm_roster):
    return Orchestrator(Roster(llm_roster), tools=tools, sandbox=sandbox)


def test_agent_calls_tool_then_completes(tmp_path):
    (tmp_path / "config.py").write_text("PORT = 8080\n")
    llm = _read_then_solo("config.py")
    orch = _orch(build_fs_tools(), FsSandbox(tmp_path), [Agent("a1", "coder", llm)])
    log = orch.run("inspect config")

    assert EventType.TOOL_CALLED in log.types()
    result = log.of_type(EventType.TOOL_RESULT)[0]
    assert result.payload["tool"] == "read_file" and result.payload["ok"] is True
    assert "PORT = 8080" in result.payload["output"]

    root, _ = reduce(log.events())
    assert root.status == "done"
    assert root.tools == [{"tool": "read_file", "ok": True}]


def test_write_then_read_roundtrips_through_sandbox(tmp_path):
    def responder(ctx):
        obs = ctx["observations"]
        if not obs:
            return _tool("write_file", path="out.txt", content="hello sandbox")
        if len(obs) == 1:
            return _tool("read_file", path="out.txt")
        return _solo()

    orch = _orch(build_fs_tools(), FsSandbox(tmp_path), [Agent("a1", "coder", FakeLLM(responder))])
    log = orch.run("write then read")

    reads = [e for e in log.of_type(EventType.TOOL_RESULT) if e.payload["tool"] == "read_file"]
    assert reads[0].payload["output"] == "hello sandbox"
    assert (tmp_path / "out.txt").read_text() == "hello sandbox"


def test_sandbox_blocks_path_escape(tmp_path):
    llm = _read_then_solo("../../etc/passwd")
    orch = _orch(build_fs_tools(), FsSandbox(tmp_path), [Agent("a1", "coder", llm)])
    log = orch.run("try to escape")

    result = log.of_type(EventType.TOOL_RESULT)[0]
    assert result.payload["ok"] is False
    assert "escapes sandbox" in result.payload["error"]
    root, _ = reduce(log.events())
    assert root.status == "done"  # the agent saw the error and finished anyway


def test_unknown_tool_is_graceful(tmp_path):
    def responder(ctx):
        return _tool("nuke_everything") if not ctx["observations"] else _solo()

    orch = _orch(build_fs_tools(), FsSandbox(tmp_path), [Agent("a1", "coder", FakeLLM(responder))])
    log = orch.run("call a missing tool")

    result = log.of_type(EventType.TOOL_RESULT)[0]
    assert result.payload["ok"] is False and "unknown tool" in result.payload["error"]
    root, _ = reduce(log.events())
    assert root.status == "done"


def test_no_sandbox_means_tools_unavailable():
    # tools registered but no sandbox -> tool calls fail safely
    def responder(ctx):
        return _tool("read_file", path="x") if not ctx["observations"] else _solo()

    orch = Orchestrator(Roster([Agent("a1", "coder", FakeLLM(responder))]), tools=build_fs_tools(), sandbox=None)
    log = orch.run("no sandbox")
    assert log.of_type(EventType.TOOL_RESULT)[0].payload["error"] == "no sandbox configured"


def test_max_tool_steps_guard_stops_runaway(tmp_path):
    # a model that only ever calls tools, never concludes
    llm = FakeLLM(lambda ctx: _tool("list_dir"))
    orch = Orchestrator(
        Roster([Agent("a1", "coder", llm)]),
        tools=build_fs_tools(),
        sandbox=FsSandbox(tmp_path),
        max_tool_steps=3,
    )
    log = orch.run("loop forever")

    failed = log.of_type(EventType.TASK_FAILED)
    assert failed and failed[0].payload["error"] == "max_tool_steps exceeded"
    assert len(log.of_type(EventType.TOOL_CALLED)) == 3
    root, _ = reduce(log.events())
    assert root.status == "failed"


def test_tool_loop_does_not_affect_toolless_runs():
    # no tools, no sandbox -> identical to Slice 1: one plan, no tool events
    llm = FakeLLM(lambda ctx: _solo())
    log = Orchestrator(Roster([Agent("a1", "planner", llm)])).run("just answer")
    assert EventType.TOOL_CALLED not in log.types()
    assert len(log.of_type(EventType.PLAN_PRODUCED)) == 1


def test_eval_scores_tool_usage(tmp_path):
    from dragzero.eval import Scenario, run_scenario
    from dragzero.eval.scorers import completed, tool_succeeded, used_tool

    (tmp_path / "config.py").write_text("PORT = 8080\n")

    def good(_):
        return _read_then_solo("config.py")

    def lazy(_):
        return FakeLLM(lambda ctx: _solo())  # never reads the file

    scn = Scenario(
        name="inspect",
        task="Inspect config.py",
        roles=["coder"],
        scorers=[used_tool("read_file"), tool_succeeded("read_file"), completed()],
        tools=[ReadFileTool(), WriteFileTool(), ListDirTool()],
        sandbox_factory=lambda: FsSandbox(tmp_path),
    )

    good_agg = run_scenario(scn, good, trials=2).aggregate()
    assert good_agg["used:read_file"].pass_rate == 1.0
    assert good_agg["tool_ok:read_file"].pass_rate == 1.0

    lazy_agg = run_scenario(scn, lazy, trials=2).aggregate()
    assert lazy_agg["used:read_file"].pass_rate == 0.0  # the gauge catches the lazy model
    assert lazy_agg["completed"].pass_rate == 1.0
