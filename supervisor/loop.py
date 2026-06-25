"""run_task_loop — the public Agent-O TaskLoop facade. Epic E10.

Drives compose_team → (o_decide → run_round/run_tool → judge_acceptance → guard)*
until a terminal status. The loop guard is mechanical and separate from O: it
terminates on max_rounds, on a round with no progress, or when O repeats the same
decision too many times. Worker turns run through DelegationManager (the E05
substrate via the delegation adapter); O never executes a tool directly.
"""
from __future__ import annotations

from typing import Any

from core.session import KernelSession
from discipline import Budget
from supervisor.contracts import OrchestratorDecision
from supervisor.graph import (
    SupervisorContext,
    compose_team,
    default_store_slice,
    judge_acceptance,
    o_decide,
    run_round,
    run_tool,
)
from supervisor.state import AcceptanceCheck, TaskLoopState, TaskLoopStatus, encode_taskloop_state


def _criteria(items: list[Any]) -> list[AcceptanceCheck]:
    checks: list[AcceptanceCheck] = []
    for item in items or []:
        if isinstance(item, AcceptanceCheck):
            checks.append(item)
        elif isinstance(item, dict):
            checks.append(AcceptanceCheck(id=str(item["id"]), text=str(item.get("text", ""))))
        else:  # (id, text) tuple
            cid, text = item
            checks.append(AcceptanceCheck(id=str(cid), text=str(text)))
    return checks


def _decision_signature(decision: OrchestratorDecision) -> str:
    agents = ",".join(sorted(a.agent_id for a in decision.next_agent_calls))
    tools = ",".join(sorted(str(t.get("tool") or t.get("name") or "") for t in decision.tool_requests))
    return f"{decision.decision}|{agents}|{tools}"


def _make_ctx(
    supervisor_session: KernelSession,
    *,
    delegation_service: Any,
    orchestrator: Any,
    broker: Any,
    agent_registry: Any | None,
    store_slice_provider: Any | None,
    checkpoint_store: Any | None,
) -> SupervisorContext:
    return SupervisorContext(
        supervisor_session=supervisor_session,
        delegation_service=delegation_service,
        orchestrator=orchestrator,
        broker=broker,
        agent_registry=agent_registry,
        store_slice_provider=store_slice_provider or default_store_slice,
        checkpoint=checkpoint_store.save if checkpoint_store is not None else None,
    )


def run_task_loop(
    supervisor_session: KernelSession,
    task: str,
    *,
    acceptance_criteria: list[Any],
    delegation_service: Any,
    orchestrator: Any,
    broker: Any,
    agent_registry: Any | None = None,
    max_rounds: int = 5,
    max_decision_repeats: int = 3,
    store_slice_provider: Any | None = None,
    budget: Budget | None = None,
    checkpoint_store: Any | None = None,
) -> dict[str, Any]:
    ctx = _make_ctx(
        supervisor_session,
        delegation_service=delegation_service,
        orchestrator=orchestrator,
        broker=broker,
        agent_registry=agent_registry,
        store_slice_provider=store_slice_provider,
        checkpoint_store=checkpoint_store,
    )
    state = TaskLoopState(
        session_id=supervisor_session.identity.session_id,
        task_id=supervisor_session.identity.task_id,
        max_rounds=max_rounds,
    )
    state.acceptance_checks = _criteria(acceptance_criteria)
    compose_team(state, ctx, task=task)
    ctx.save(state)
    return _drive(state, ctx, budget=budget or Budget(), max_decision_repeats=max_decision_repeats)


def resume_task_loop(
    supervisor_session: KernelSession,
    *,
    checkpoint_store: Any,
    delegation_service: Any,
    orchestrator: Any,
    broker: Any,
    agent_registry: Any | None = None,
    max_decision_repeats: int = 3,
    store_slice_provider: Any | None = None,
    budget: Budget | None = None,
) -> dict[str, Any]:
    """Restore the Blackboard from SQLite and continue from the next pending round."""
    state = checkpoint_store.load()
    if state is None:
        raise FileNotFoundError(f"No TaskLoop checkpoint for run_id={checkpoint_store.run_id!r}")
    # A checkpoint may only be resumed by the supervisor session that owns it — a
    # foreign session/task identity must never adopt another run's Blackboard.
    identity = supervisor_session.identity
    if state.session_id != identity.session_id or state.task_id != identity.task_id:
        raise ValueError(
            f"Checkpoint identity (session={state.session_id!r}, task={state.task_id!r}) does not "
            f"match the active supervisor session (session={identity.session_id!r}, task={identity.task_id!r})."
        )
    ctx = _make_ctx(
        supervisor_session,
        delegation_service=delegation_service,
        orchestrator=orchestrator,
        broker=broker,
        agent_registry=agent_registry,
        store_slice_provider=store_slice_provider,
        checkpoint_store=checkpoint_store,
    )
    if state.is_terminal:
        return _result(state)
    return _drive(state, ctx, budget=budget or Budget(), max_decision_repeats=max_decision_repeats)


def _drive(
    state: TaskLoopState, ctx: SupervisorContext, *, budget: Budget, max_decision_repeats: int
) -> dict[str, Any]:
    last_signature: str | None = None
    repeat_count = 0

    while not state.is_terminal:
        if state.round_no >= state.max_rounds:
            _terminate(state, ctx, TaskLoopStatus.BLOCKED, "max_rounds reached")
            break

        before_artifacts = len(state.artifacts)
        before_acceptance = state.acceptance_snapshot()

        decision = o_decide(state, ctx, budget=budget)
        if decision is None:
            _terminate(state, ctx, TaskLoopStatus.FAILED, "parse-error budget exceeded")
            break

        signature = _decision_signature(decision)
        repeat_count = repeat_count + 1 if signature == last_signature else 0
        last_signature = signature

        if decision.decision == "finished":
            judge_acceptance(state, ctx, decision)
            if state.all_accepted():
                state.final_output = decision.final_output or {}
                _terminate(state, ctx, TaskLoopStatus.FINISHED, decision.reason or "all criteria passed")
                break
            state.reason = "finish denied: acceptance criteria incomplete"
        elif decision.decision == "need_tool":
            run_tool(state, ctx, decision)
            judge_acceptance(state, ctx, decision)
        elif decision.decision == "continue":
            run_round(state, ctx, decision)
            judge_acceptance(state, ctx, decision)
        elif decision.decision in {"blocked", "failed"}:
            status = TaskLoopStatus.BLOCKED if decision.decision == "blocked" else TaskLoopStatus.FAILED
            _terminate(state, ctx, status, decision.reason or decision.decision)
            break

        state.round_no += 1
        ctx.save(state)  # checkpoint at each round boundary (S10.10)

        progressed = len(state.artifacts) > before_artifacts or state.acceptance_snapshot() != before_acceptance
        if not progressed:
            _terminate(state, ctx, TaskLoopStatus.BLOCKED, "no progress this round")
            break
        if repeat_count >= max_decision_repeats:
            _terminate(state, ctx, TaskLoopStatus.BLOCKED, "orchestrator repeated the same decision")
            break

    return _result(state)


def _terminate(state: TaskLoopState, ctx: SupervisorContext, status: TaskLoopStatus, reason: str) -> None:
    state.status = status.value
    state.reason = reason
    ctx.emit(f"loop.{status.value}", {"reason": reason, "rounds": state.round_no})
    ctx.save(state)


def _result(state: TaskLoopState) -> dict[str, Any]:
    return {
        "status": state.status,
        "task_id": state.task_id,
        "rounds": state.round_no,
        "reason": state.reason,
        "selected_agents": list(state.selected_agents),
        "final_output": state.final_output,
        "acceptance": [c.as_dict() for c in state.acceptance_checks],
        "state": encode_taskloop_state(state),
    }
