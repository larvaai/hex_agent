"""E2E anti-gaming: a 'done' CLAIM with no artifact reads code-FAIL through the real Run path.

End-to-end the way the UI drives it: Run.start() spins the orchestrator on a daemon thread,
then _final_status / build_graph re-derive the verdict over the sandbox. A coder that claims
solo-done WITHOUT writing report.md must come back blocked (root verdict FAIL); the only
thing that flips it to PASS is the file actually landing on disk during the run.
"""
import time

import pytest

from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools
from dragzero.server import Run

_DONE_WHEN = {"__root__": [{"check": "file_exists", "artifact": "report.md"}]}


def _await_done(run, tries=200, pause=0.02):
    for _ in range(tries):
        if run.done:
            return
        time.sleep(pause)
    raise AssertionError("run did not finish")


# --- scenario 1: claim done, write nothing -> code FAILs the gate ----------- #
def _liar_builder(tmp):
    """A single coder whose FakeLLM goes solo immediately — no tool, no file written."""

    def responder(ctx):
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}

    def build():
        sandbox = FsSandbox(tmp)
        llm = FakeLLM(responder)
        roster = Roster([Agent("coder", "coder", llm)])
        orch = Orchestrator(roster, tools=build_fs_tools(), sandbox=sandbox)
        return orch, roster.by_role_or_id("coder"), sandbox

    return build


def test_claim_without_artifact_reads_fail(tmp_path):
    run = Run(id="r", title="t", task="write the report",
              builder=_liar_builder(str(tmp_path)), pace=0.0, done_when=_DONE_WHEN)
    run.reset()
    run.start()
    _await_done(run)

    # the orchestrator did finish (the model said solo-done)...
    assert run.done is True
    # ...but code looked at disk: report.md is missing, so the gate FAILs.
    assert run.status == "blocked"

    g = run.graph()
    root = next(n for n in g["nodes"] if n["id"] == g["root"])
    assert root["verdict"] == "FAIL"                 # code overrides the "done" claim
    assert root["runtime"]["status"] == "blocked"    # the FAIL drives the UI status

    # the disk really is empty — the claim was hollow
    assert "report.md" not in [a["path"] for a in run.artifacts()]


# --- scenario 2: actually write the artifact -> the gate PASSes ------------- #
def _honest_builder(tmp):
    """A coder that writes report.md (nonempty) via the write_file tool, then goes solo."""

    def responder(ctx):
        if not ctx["observations"]:
            return {"action": {"type": "tool", "tool": "write_file",
                               "args": {"path": "report.md", "content": "# report\nall green\n"}}}
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}

    def build():
        sandbox = FsSandbox(tmp)
        llm = FakeLLM(responder)
        roster = Roster([Agent("coder", "coder", llm)])
        orch = Orchestrator(roster, tools=build_fs_tools(), sandbox=sandbox)
        return orch, roster.by_role_or_id("coder"), sandbox

    return build


def test_written_artifact_flips_to_pass(tmp_path):
    run = Run(id="r", title="t", task="write the report",
              builder=_honest_builder(str(tmp_path)), pace=0.0, done_when=_DONE_WHEN)
    run.reset()
    run.start()
    _await_done(run)

    assert run.done is True
    # Run stamps _activated_at at start(), so the file written during the run is FRESH.
    assert run.status == "done"

    g = run.graph()
    root = next(n for n in g["nodes"] if n["id"] == g["root"])
    assert root["verdict"] == "PASS"
    assert root["runtime"]["status"] == "done"

    # and the artifact is genuinely on disk, nonempty
    assert "report.md" in [a["path"] for a in run.artifacts()]
    assert run.read_artifact("report.md").strip() != ""
