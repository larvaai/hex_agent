"""Serializable LangGraph state and codec for isolated KernelSession state."""
from __future__ import annotations

import dataclasses
from typing import Any, TypedDict

from core.schemas import TaskEnvelope
from core.session import KernelSession
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
    session_identity: dict[str, Any]
    allowed_capabilities: list[str]
    session_state: dict[str, Any]
    kernel_state: dict[str, Any]  # migration-only key from schema v1
    model: str | None
    last_action: dict[str, Any] | None
    route: str
    final: str | None
    outcome: dict[str, Any] | None
    status: str
    error: str | None
    active_delegation_id: str | None
    last_delegation_result: dict[str, Any] | None


def encode_session_state(state: dict[str, Any]) -> dict[str, Any]:
    """Convert a session snapshot to primitives accepted by every checkpointer."""
    encoded = dict(state)
    task = encoded.get("current_task")
    if isinstance(task, TaskEnvelope):
        encoded["current_task"] = {"__task__": task.as_dict()}
    return encoded


def decode_session_state(state: dict[str, Any]) -> dict[str, Any]:
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
    session: KernelSession,
    messages: list[dict[str, str]],
    budget: Budget,
    model: str | None = None,
) -> AgentState:
    task = session.state.get("current_task")
    if not isinstance(task, TaskEnvelope):
        raise ValueError("Cannot initialize graph state from an inactive session.")
    identity = session.identity
    return {
        "schema_version": 2,
        "run_id": identity.run_id,
        "task_id": identity.task_id,
        "task": task.user_request,
        "context": dict(task.context),
        "messages": list(messages),
        "budget": budget_to_dict(budget),
        "session_identity": identity.as_dict(),
        "allowed_capabilities": sorted(session.allowed_capabilities),
        "session_state": encode_session_state(session.state.snapshot()),
        "model": model,
        "last_action": None,
        "route": "guard",
        "final": None,
        "outcome": None,
        "status": "running",
        "error": None,
        "active_delegation_id": None,
        "last_delegation_result": None,
    }


# Compatibility aliases for pre-session checkpoints. New code must use session names.
encode_kernel_state = encode_session_state
decode_kernel_state = decode_session_state
