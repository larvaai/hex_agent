"""Public run/resume facade backed by the single compiled LangGraph."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from core.kernel import AgentKernel
from core.ports import DelegationServicePort
from core.schemas import TaskEnvelope
from core.session import KernelSession, SessionFactory, SessionIdentity
from discipline import Budget
from graph.runtime import build_agent_graph
from graph.state import AgentState, budget_from_state, decode_session_state, new_agent_state
from orchestrator.checkpoint import (
    checkpoint_db_path,
    load_checkpoint,
    open_checkpointer,
    save_graph_projection,
)

DEFAULT_SYSTEM = (
    "You are an agent. Think, then act. Reply with EXACTLY ONE JSON object and nothing else.\n"
    'Tool call:  {"action":"tool","tool":"<name>","args":{...}}\n'
    'Finish:     {"action":"final","message":"<answer>","finish_reason":"done"}'
)


def _delegation_prompt(service: DelegationServicePort | None) -> str:
    if service is None:
        return ""
    targets = ", ".join(service.available_targets())
    return (
        f"\nDelegation targets: {targets}. "
        'Delegate: {"action":"delegate","target":"<listed target>",'
        '"spec":{"objective":"<work>","input_context":{}},"policy":{}}'
    )


def _config(run_id: str, budget: Budget) -> dict[str, Any]:
    # Parse errors now gate on the CONSECUTIVE streak (reset on every good parse), so a run can
    # legitimately absorb up to max_parse_errors retries BEFORE EACH of its max_steps actions.
    # The graph node budget must cover that worst case or recursion_limit trips before the loop's
    # own budget does. Per real step: guard+agent (2) + up to max_parse_errors*(agent+guard) + tool+guard.
    return {
        "configurable": {"thread_id": run_id},
        "recursion_limit": max(150, budget.max_steps * (2 * budget.max_parse_errors + 4) + 40),
    }


def _outcome(state: AgentState) -> dict[str, Any]:
    outcome = state.get("outcome")
    if isinstance(outcome, dict):
        return outcome
    return {
        "task_id": state.get("task_id"),
        "status": state.get("status", "incomplete"),
        "result": state.get("final"),
    }


def _sync_budget(target: Budget, state: AgentState) -> None:
    persisted = budget_from_state(state)
    target.steps = persisted.steps
    target.parse_errors = persisted.parse_errors
    target._tool_calls = dict(persisted._tool_calls)


def _stream(
    graph,
    graph_input: AgentState | None,
    *,
    config: dict[str, Any],
    projection: bool,
) -> AgentState:
    final_state: AgentState | None = graph_input
    try:
        for values in graph.stream(graph_input, config, stream_mode="values"):
            final_state = values
            save_graph_projection(values, enabled=projection)
    except Exception:
        if projection:
            snapshot = graph.get_state(config)
            if snapshot.values:
                save_graph_projection(snapshot.values, enabled=True)
        raise
    if final_state is None:
        snapshot = graph.get_state(config)
        final_state = snapshot.values
    return final_state


def run(
    kernel: AgentKernel,
    user_request: str,
    *,
    budget: Budget | None = None,
    system_prompt: str = DEFAULT_SYSTEM,
    context: dict[str, Any] | None = None,
    run_id: str | None = None,
    checkpoint: bool = True,
    session: KernelSession | None = None,
    delegation_service: DelegationServicePort | None = None,
) -> dict[str, Any]:
    """Start a task and drive the compiled graph to a terminal state."""
    active_session = session or SessionFactory(kernel=kernel).create_root(
        user_request,
        context=context,
        run_id=run_id,
    )
    if active_session.kernel is not kernel:
        raise ValueError("Provided session belongs to a different kernel.")
    current_task = active_session.state.get("current_task")
    if not isinstance(current_task, TaskEnvelope) or current_task.user_request != user_request:
        raise ValueError("Provided session does not own the requested task.")
    if run_id is not None and active_session.identity.run_id != run_id:
        raise ValueError("Provided session run_id does not match the requested run_id.")
    active_budget = budget or Budget.from_env()
    rid = active_session.identity.run_id
    prompt = system_prompt + _delegation_prompt(delegation_service)
    initial = new_agent_state(
        session=active_session,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_request},
        ],
        budget=active_budget,
    )
    config = _config(rid, active_budget)
    if not checkpoint:
        graph = build_agent_graph(
            session=active_session,
            delegation_service=delegation_service,
        )
        state = _stream(graph, initial, config=config, projection=False)
        _sync_budget(active_budget, state)
        return _outcome(state)

    with open_checkpointer(rid) as saver:
        graph = build_agent_graph(
            session=active_session,
            checkpointer=saver,
            delegation_service=delegation_service,
        )
        state = _stream(graph, initial, config=config, projection=True)
        _sync_budget(active_budget, state)
        return _outcome(state)


def _legacy_state(kernel: AgentKernel, run_id: str) -> AgentState | dict[str, Any]:
    """Read an old JSON checkpoint once so pre-LangGraph runs remain resumable."""
    checkpoint = load_checkpoint(run_id)
    if checkpoint is None or checkpoint.backend != "legacy-json":
        raise FileNotFoundError(f"No checkpoint for run_id={run_id!r}")
    if checkpoint.status != "running":
        return checkpoint.state.get("last_result") or {
            "task_id": None,
            "status": checkpoint.status,
            "result": None,
        }

    task = checkpoint.state.get("current_task")
    if not isinstance(task, TaskEnvelope):
        task = TaskEnvelope(user_request=checkpoint.task, task_id=run_id)
        checkpoint.state["current_task"] = task
    raw_budget = dict(checkpoint.budget)
    fields = {item.name for item in dataclasses.fields(Budget)}
    budget = Budget(**{key: value for key, value in raw_budget.items() if key in fields})
    identity = SessionIdentity(
        session_id=task.task_id,
        run_id=run_id,
        task_id=task.task_id,
        agent_id="agent:root",
    )
    factory = SessionFactory(kernel=kernel)
    session = factory.restore(
        identity=identity,
        state=checkpoint.state,
        allowed_capabilities=frozenset(item["name"] for item in kernel.registry.list_tools()),
    )
    return new_agent_state(
        session=session,
        messages=list(checkpoint.messages),
        budget=budget,
    )


def _restore_persisted_session(
    kernel: AgentKernel,
    run_id: str,
    persisted: AgentState,
) -> KernelSession:
    raw_session_state = persisted.get("session_state") or persisted.get("kernel_state") or {}
    session_state = decode_session_state(raw_session_state)
    identity_raw = persisted.get("session_identity")
    if isinstance(identity_raw, dict):
        identity = SessionIdentity.from_dict(identity_raw)
    else:
        task = session_state.get("current_task")
        task_id = str(persisted.get("task_id") or getattr(task, "task_id", run_id))
        identity = SessionIdentity(
            session_id=task_id,
            run_id=run_id,
            task_id=task_id,
            agent_id="agent:root",
        )
    allowed = persisted.get("allowed_capabilities")
    if allowed is None:
        allowed = [item["name"] for item in kernel.registry.list_tools()]
    return SessionFactory(kernel=kernel).restore(
        identity=identity,
        state=session_state,
        allowed_capabilities=frozenset(allowed),
    )


def resume(
    kernel: AgentKernel,
    run_id: str,
    *,
    checkpoint: bool = True,
    delegation_service: DelegationServicePort | None = None,
) -> dict[str, Any]:
    """Resume the next pending LangGraph node using the same thread/run ID."""
    db_path: Path = checkpoint_db_path(run_id)
    if not db_path.exists():
        migrated = _legacy_state(kernel, run_id)
        if "schema_version" not in migrated:
            return migrated
        budget = budget_from_state(migrated)
        session = _restore_persisted_session(kernel, run_id, migrated)
        with open_checkpointer(run_id) as saver:
            graph = build_agent_graph(
                session=session,
                checkpointer=saver,
                delegation_service=delegation_service,
            )
            state = _stream(
                graph,
                migrated,
                config=_config(run_id, budget),
                projection=checkpoint,
            )
            return _outcome(state)

    with open_checkpointer(run_id) as saver:
        bootstrap_config = {"configurable": {"thread_id": run_id}}
        # Compile once with a placeholder session only after reading raw state is impossible;
        # modern checkpoints always carry identity, so read them with the saver directly.
        raw = saver.get_tuple(bootstrap_config)
        if raw is None:
            raise FileNotFoundError(f"No checkpoint for run_id={run_id!r}")
        persisted: AgentState = dict(raw.checkpoint.get("channel_values") or {})
        session = _restore_persisted_session(kernel, run_id, persisted)
        graph = build_agent_graph(
            session=session,
            checkpointer=saver,
            delegation_service=delegation_service,
        )
        snapshot = graph.get_state(bootstrap_config)
        if not snapshot.values:
            raise FileNotFoundError(f"No checkpoint for run_id={run_id!r}")
        persisted = snapshot.values
        if persisted.get("status") != "running" or not snapshot.next:
            return _outcome(persisted)
        budget = budget_from_state(persisted)
        state = _stream(
            graph,
            None,
            config=_config(run_id, budget),
            projection=checkpoint,
        )
        return _outcome(state)
