"""Scorer primitives — the harness ships the gauges, you compose the rubric.

Each factory returns a callable `(EvalContext) -> ScoreResult` carrying a
`.score_name` so a crashed trial can still be attributed. Scorers read the event
log and the projected tree only — never private orchestrator state.
"""
from __future__ import annotations

from ..contracts import TaskStatus
from ..events import EventType
from ..live_view import render_log
from .model import ScoreResult

_RAN = {TaskStatus.RUNNING.value, TaskStatus.DONE.value}


def _named(fn, name):
    fn.score_name = name
    return fn


def expects_delegation_to(role, name=None):
    """1.0 if some subtask was delegated to `role`."""
    nm = name or f"delegates_to:{role}"

    def scorer(ctx):
        hits = [e for e in ctx.log if e.type == EventType.SUBTASK_SPAWNED and e.payload.get("target") == role]
        ok = len(hits) > 0
        return ScoreResult(nm, 1.0 if ok else 0.0, ok, f"{len(hits)} delegation(s) to {role!r}")

    return _named(scorer, nm)


def expects_solo(name="solves_solo"):
    """1.0 if the task was handled without any delegation."""

    def scorer(ctx):
        n = len(ctx.log.of_type(EventType.SUBTASK_SPAWNED))
        ok = n == 0
        return ScoreResult(name, 1.0 if ok else 0.0, ok, f"{n} delegation(s)")

    return _named(scorer, name)


def reached_role(role, name=None):
    """1.0 if an agent of `role` actually started/finished a task."""
    nm = name or f"reached:{role}"

    def scorer(ctx):
        hit = False
        for node in ctx.nodes.values():
            if node.agent_id and node.status in _RAN:
                agent = ctx.orchestrator.roster.get(node.agent_id)
                if agent and agent.role == role:
                    hit = True
                    break
        return ScoreResult(nm, 1.0 if hit else 0.0, hit, f"role {role!r} {'reached' if hit else 'not reached'}")

    return _named(scorer, nm)


def completed(name="completed"):
    """1.0 if the root finished (done), 0.0 if failed / halted / still waiting."""

    def scorer(ctx):
        status = ctx.root.status if ctx.root else None
        ok = status == TaskStatus.DONE.value
        return ScoreResult(name, 1.0 if ok else 0.0, ok, f"root status={status}")

    return _named(scorer, name)


def max_plan_calls(n, name=None):
    """1.0 if the run used at most `n` plan/LLM calls (penalises over-delegation)."""
    nm = name or f"<= {n} plan calls"

    def scorer(ctx):
        c = len(ctx.log.of_type(EventType.PLAN_PRODUCED))
        ok = c <= n
        return ScoreResult(nm, 1.0 if ok else 0.0, ok, f"{c} plan calls (limit {n})")

    return _named(scorer, nm)


def no_fallback(name="no_llm_fallback"):
    """1.0 if no decision was a safe-fallback (the local adapter couldn't parse).

    Reads it straight off the event log: the fallback decision carries a
    `reasoning` of "fallback: ...".
    """

    def scorer(ctx):
        bad = sum(
            1
            for e in ctx.log.of_type(EventType.DELEGATION_DECIDED)
            if str(e.payload["decision"].get("reasoning", "")).startswith("fallback:")
        )
        ok = bad == 0
        return ScoreResult(name, 1.0 if ok else 0.0, ok, f"{bad} fallback decision(s)")

    return _named(scorer, name)


def used_tool(tool, name=None):
    """1.0 if the agent actually called `tool` at least once."""
    nm = name or f"used:{tool}"

    def scorer(ctx):
        calls = [e for e in ctx.log if e.type == EventType.TOOL_CALLED and e.payload.get("tool") == tool]
        ok = len(calls) > 0
        return ScoreResult(nm, 1.0 if ok else 0.0, ok, f"{len(calls)} call(s) to {tool!r}")

    return _named(scorer, nm)


def tool_succeeded(tool, name=None):
    """1.0 if a call to `tool` returned ok."""
    nm = name or f"tool_ok:{tool}"

    def scorer(ctx):
        results = [e for e in ctx.log if e.type == EventType.TOOL_RESULT and e.payload.get("tool") == tool]
        ok = any(e.payload.get("ok") for e in results)
        return ScoreResult(nm, 1.0 if ok else 0.0, ok, f"{len(results)} result(s) for {tool!r}")

    return _named(scorer, nm)


def llm_judge(judge_llm, rubric, name="judge", threshold=0.6):
    """Non-deterministic scorer: a judge model scores the trace 0..1.

    `judge_llm` is any object with `.complete(ctx) -> {"score": float, "reason": str}`.
    Kept optional so the deterministic suite never needs weights.
    """

    def scorer(ctx):
        trace = render_log(ctx.log.events())
        prompt = {
            "role": "judge",
            "task": f"{rubric}\n\nTASK: {ctx.scenario.task}\nTRACE:\n{trace}",
            "depth": 0,
        }
        resp = judge_llm.complete(prompt)
        try:
            score = float(resp.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        return ScoreResult(name, score, score >= threshold, str(resp.get("reason", "")))

    return _named(scorer, name)
