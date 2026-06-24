"""Public run/resume facade backed by the single compiled LangGraph."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from core.kernel import AgentKernel
from core.schemas import TaskEnvelope
from discipline import Budget
from graph.runtime import build_agent_graph
from graph.state import AgentState, budget_from_state, decode_kernel_state, new_agent_state
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


def _config(run_id: str, budget: Budget) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": run_id},
        "recursion_limit": max(100, budget.max_steps * 4 + budget.max_parse_errors * 3 + 20),
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
) -> dict[str, Any]:
    """Start a task and drive the compiled graph to a terminal state."""
    task = kernel.accept_task(user_request, context)
    active_budget = budget or Budget()
    rid = run_id or task.task_id
    initial = new_agent_state(
        run_id=rid,
        task=task,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
        ],
        budget=active_budget,
        kernel_state=kernel.state.snapshot(),
    )
    config = _config(rid, active_budget)
    if not checkpoint:
        graph = build_agent_graph(kernel=kernel)
        state = _stream(graph, initial, config=config, projection=False)
        _sync_budget(active_budget, state)
        return _outcome(state)

    with open_checkpointer(rid) as saver:
        graph = build_agent_graph(kernel=kernel, checkpointer=saver)
        state = _stream(graph, initial, config=config, projection=True)
        _sync_budget(active_budget, state)
        return _outcome(state)


def _legacy_state(kernel: AgentKernel, run_id: str) -> AgentState | dict[str, Any]:
    """Read an old JSON checkpoint once so pre-LangGraph runs remain resumable."""
    checkpoint = load_checkpoint(run_id)
    if checkpoint is None or checkpoint.backend != "legacy-json":
        raise FileNotFoundError(f"No checkpoint for run_id={run_id!r}")
    kernel.state.restore(checkpoint.state)
    if checkpoint.status != "running":
        return kernel.state.get("last_result") or {
            "task_id": None,
            "status": checkpoint.status,
            "result": None,
        }

    task = kernel.state.get("current_task")
    if not isinstance(task, TaskEnvelope):
        task = TaskEnvelope(user_request=checkpoint.task, task_id=run_id)
        kernel.state.set("current_task", task)
    raw_budget = dict(checkpoint.budget)
    fields = {item.name for item in dataclasses.fields(Budget)}
    budget = Budget(**{key: value for key, value in raw_budget.items() if key in fields})
    return new_agent_state(
        run_id=run_id,
        task=task,
        messages=list(checkpoint.messages),
        budget=budget,
        kernel_state=kernel.state.snapshot(),
    )


def resume(kernel: AgentKernel, run_id: str, *, checkpoint: bool = True) -> dict[str, Any]:
    """Resume the next pending LangGraph node using the same thread/run ID."""
    db_path: Path = checkpoint_db_path(run_id)
    if not db_path.exists():
        migrated = _legacy_state(kernel, run_id)
        if "schema_version" not in migrated:
            return migrated
        budget = budget_from_state(migrated)
        with open_checkpointer(run_id) as saver:
            graph = build_agent_graph(kernel=kernel, checkpointer=saver)
            state = _stream(
                graph,
                migrated,
                config=_config(run_id, budget),
                projection=checkpoint,
            )
            return _outcome(state)

    with open_checkpointer(run_id) as saver:
        graph = build_agent_graph(kernel=kernel, checkpointer=saver)
        bootstrap_config = {"configurable": {"thread_id": run_id}}
        snapshot = graph.get_state(bootstrap_config)
        if not snapshot.values:
            raise FileNotFoundError(f"No checkpoint for run_id={run_id!r}")
        persisted: AgentState = snapshot.values
        kernel.state.restore(decode_kernel_state(persisted.get("kernel_state") or {}))
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
