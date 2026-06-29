"""Phase 6A — one real local-model run through the orchestrator. Asserts SHAPE, never content.

Opt-in (marker=real_llm): the root conftest skips this unless OPENAI_BASE_URL is set. A local
35B is non-deterministic, so we pin only the harness contract: the run TERMINATES (no hang,
no crash), every decision is well-formed, and fallbacks are SURFACED (not silently gating).
"""
import os

import pytest

from dragzero import Agent, Budget, EventType, Orchestrator, Roster, TaskStatus, reduce
from dragzero.adapters.llm_local import OpenAICompatLLM
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools

pytestmark = pytest.mark.real_llm

_VALID_MODES = {"solo", "delegate"}
_ALL_STATUSES = {s.value for s in TaskStatus}


def _llm(roles):
    return OpenAICompatLLM(
        base_url=os.environ["OPENAI_BASE_URL"],
        model=os.environ.get("MODEL", "local-model"),
        api_key=os.environ.get("OPENAI_API_KEY", "lm-studio"),
        roles=roles,
    )


def test_real_run_terminates_with_valid_shape(tmp_path):
    roles = ["coder", "reviewer", "tester"]
    llm = _llm(roles)
    roster = Roster([Agent("planner-1", "planner", llm)] + [Agent(f"{r}-1", r, llm) for r in roles])
    orch = Orchestrator(roster, budget=Budget(limit=8), tools=build_fs_tools(), sandbox=FsSandbox(str(tmp_path)))

    log = orch.run("Fix parse_config and add a test")  # returns => it did not hang

    assert orch.is_idle()
    root, _ = reduce(log.events())
    assert root is not None and root.status in _ALL_STATUSES

    # Harness shape contract (NOT model quality): the run RESOLVED in a bounded way — it
    # completed, failed, or halted on budget/max-steps. A real tool-using model can legitimately
    # loop tools until the budget halts WITHOUT ever emitting a terminal decision, so we do NOT
    # require >=1 decision — we require the run terminated safely.
    types = log.types()
    assert any(t in types for t in (EventType.TASK_COMPLETED, EventType.TASK_FAILED, EventType.BUDGET_EXCEEDED)), \
        "the run must resolve (complete / fail / budget-halt), never hang"

    # every decision the model DID produce must be well-formed (may be zero).
    decisions = [e.payload["decision"] for e in log.of_type(EventType.DELEGATION_DECIDED)]
    for d in decisions:
        assert d["mode"] in _VALID_MODES
        if d["mode"] == "delegate":
            assert d.get("target"), "a delegate decision must name a target role"

    # red-team #5: surface fallbacks + the termination reason as INFO, never gate on them.
    fallbacks = sum(1 for d in decisions if str(d.get("reasoning", "")).startswith("fallback:"))
    print(f"[real_llm] decisions={len(decisions)} fallbacks={fallbacks} root={root.status} "
          f"tool_calls={len(log.of_type(EventType.TOOL_CALLED))} "
          f"budget_halt={EventType.BUDGET_EXCEEDED in types} events={len(log)}")


@pytest.mark.xfail(reason="model quality, not harness: a well-behaved model produces no parse fallbacks", strict=False)
def test_real_run_has_no_fallbacks(tmp_path):
    """Happy-path quality signal: a sane model never trips the solo_fallback. xfail so a weak
    model doesn't fail CI — flip to a hard assert when pinning a known-good model."""
    llm = _llm(["coder", "reviewer", "tester"])
    roster = Roster([Agent("planner-1", "planner", llm), Agent("coder-1", "coder", llm)])
    orch = Orchestrator(roster, budget=Budget(limit=8))
    log = orch.run("What is 2 + 2?")
    decisions = [e.payload["decision"] for e in log.of_type(EventType.DELEGATION_DECIDED)]
    assert all(not str(d.get("reasoning", "")).startswith("fallback:") for d in decisions)
