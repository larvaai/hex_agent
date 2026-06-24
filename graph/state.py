"""Serializable LangGraph state and the codec for the microkernel's in-memory state."""
from __future__ import annotations

import dataclasses
from typing import Any, TypedDict

from core.schemas import TaskEnvelope
from discipline import Budget


class AgentState(TypedDict, total=False):
    """Authoritative, checkpointed state for one agent run.

    Runtime services such as the kernel, LLM client, and SQLite connection are
    intentionally excluded. Nodes receive those through closures when the graph
    is compiled, keeping every checkpoint serializable and restart-safe.
    """

    schema_version: int
    run_id: str
    task_id: str
    task: str
    context: dict[str, Any]
    messages: list[dict[str, str]]
    budget: dict[str, Any]
    kernel_state: dict[str, Any]
    model: str | None
    last_action: dict[str, Any] | None
    route: str
    final: str | None
    outcome: dict[str, Any] | None
    status: str
    error: str | None


def encode_kernel_state(state: dict[str, Any]) -> dict[str, Any]:
    """Convert the kernel snapshot to primitives accepted by every checkpointer."""
    encoded = dict(state)
    task = encoded.get("current_task")
    if isinstance(task, TaskEnvelope):
        encoded["current_task"] = {"__task__": task.as_dict()}
    return encoded


def decode_kernel_state(state: dict[str, Any]) -> dict[str, Any]:
    """Restore dataclass values after loading a graph checkpoint."""
    decoded = dict(state)
    task = decoded.get("current_task")
    if isinstance(task, dict) and isinstance(task.get("__task__"), dict):
        decoded["current_task"] = TaskEnvelope.from_dict(task["__task__"])
    return decoded


def budget_to_dict(budget: Budget) -> dict[str, Any]:
    return dataclasses.asdict(budget)


def budget_from_state(state: AgentState) -> Budget:
    raw = dict(state.get("budget") or {})
    allowed = {field.name for field in dataclasses.fields(Budget)}
    return Budget(**{key: value for key, value in raw.items() if key in allowed})


def new_agent_state(
    *,
    run_id: str,
    task: TaskEnvelope,
    messages: list[dict[str, str]],
    budget: Budget,
    kernel_state: dict[str, Any],
    model: str | None = None,
) -> AgentState:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": task.task_id,
        "task": task.user_request,
        "context": dict(task.context),
        "messages": list(messages),
        "budget": budget_to_dict(budget),
        "kernel_state": encode_kernel_state(kernel_state),
        "model": model,
        "last_action": None,
        "route": "guard",
        "final": None,
        "outcome": None,
        "status": "running",
        "error": None,
    }
