"""LangGraph nodes; every external action still crosses AgentKernel.execute_tool."""
from __future__ import annotations

import json
from typing import Any

from core.kernel import AgentKernel
from core.schemas import TaskEnvelope
from discipline import Budget, JsonGateError, build_retry_message, check_finish, parse_action
from graph.state import (
    AgentState,
    budget_from_state,
    budget_to_dict,
    decode_kernel_state,
    encode_kernel_state,
)


def _restore_kernel(state: AgentState, kernel: AgentKernel) -> None:
    snapshot = decode_kernel_state(state.get("kernel_state") or {})
    if state.get("status") == "running" and not isinstance(snapshot.get("current_task"), TaskEnvelope):
        snapshot["current_task"] = TaskEnvelope(
            user_request=str(state.get("task", "")),
            context=dict(state.get("context") or {}),
            task_id=str(state.get("task_id", "")),
        )
    kernel.state.restore(snapshot)


def _kernel_snapshot(kernel: AgentKernel) -> dict[str, Any]:
    return encode_kernel_state(kernel.state.snapshot())


def _emit(kernel: AgentKernel, topic: str, state: AgentState, **payload: Any) -> None:
    kernel.events.publish(
        topic,
        {
            "run_id": state.get("run_id"),
            "task_id": state.get("task_id"),
            "step": budget_from_state(state).steps,
            **payload,
        },
    )


def guard_node(state: AgentState, *, kernel: AgentKernel) -> dict[str, Any]:
    """Stop before the next LLM call once the valid-action budget is exhausted."""
    _restore_kernel(state, kernel)
    budget = budget_from_state(state)
    if budget.steps >= budget.max_steps:
        error = "step budget exceeded"
        _emit(kernel, "graph.budget_blocked", state, reason=error)
        return {"route": "fail", "error": error, "kernel_state": _kernel_snapshot(kernel)}
    return {"route": "agent", "kernel_state": _kernel_snapshot(kernel)}


def agent_node(state: AgentState, *, kernel: AgentKernel) -> dict[str, Any]:
    """Call the LLM capability, parse one action, and update loop discipline."""
    _restore_kernel(state, kernel)
    messages = list(state.get("messages") or [])
    response = kernel.execute_tool(
        "llm.chat",
        {"messages": messages, "model": state.get("model"), "json_mode": True},
    )
    content = str((response.get("data") or {}).get("content", ""))
    messages.append({"role": "assistant", "content": content})
    budget = budget_from_state(state)

    try:
        action = parse_action(content)
    except JsonGateError as exc:
        budget.record_parse_error()
        _emit(kernel, "graph.parse_error", state, error=str(exc), stage=exc.stage)
        if budget.parse_exceeded():
            return {
                "messages": messages,
                "budget": budget_to_dict(budget),
                "route": "fail",
                "error": "too many parse errors",
                "kernel_state": _kernel_snapshot(kernel),
            }
        messages.append({"role": "user", "content": build_retry_message(exc)})
        return {
            "messages": messages,
            "budget": budget_to_dict(budget),
            "route": "guard",
            "kernel_state": _kernel_snapshot(kernel),
        }

    budget.record_step()
    verb = str(action.get("action", ""))
    _emit(kernel, "graph.step", state, action=verb, next_step=budget.steps)
    update: dict[str, Any] = {
        "messages": messages,
        "budget": budget_to_dict(budget),
        "last_action": action,
        "kernel_state": _kernel_snapshot(kernel),
    }
    if verb == "tool":
        update["route"] = "tool"
    elif verb == "final":
        update["route"] = "finish"
    else:
        messages.append({"role": "user", "content": "Unknown 'action'. Use 'tool' or 'final'."})
        update["messages"] = messages
        update["route"] = "guard"
    return update


def tool_node(state: AgentState, *, kernel: AgentKernel) -> dict[str, Any]:
    """Execute a requested tool through the kernel and append its envelope to history."""
    _restore_kernel(state, kernel)
    action = dict(state.get("last_action") or {})
    name = str(action.get("tool", ""))
    args = action.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    budget = budget_from_state(state)
    key = Budget.tool_key(name, args)
    budget.record_tool_call(key)
    if budget.same_tool_exceeded(key):
        error = "repeated the same tool call too many times"
        _emit(kernel, "graph.budget_blocked", state, reason=error, tool=name)
        return {
            "budget": budget_to_dict(budget),
            "route": "fail",
            "error": error,
            "kernel_state": _kernel_snapshot(kernel),
        }

    result = kernel.execute_tool(name, args)
    messages = list(state.get("messages") or [])
    messages.append(
        {"role": "user", "content": json.dumps(result, ensure_ascii=False, default=str)}
    )
    return {
        "messages": messages,
        "budget": budget_to_dict(budget),
        "route": "guard",
        "kernel_state": _kernel_snapshot(kernel),
    }


def finish_node(state: AgentState, *, kernel: AgentKernel) -> dict[str, Any]:
    """Apply the shared finish gate, then close the kernel lifecycle exactly once."""
    _restore_kernel(state, kernel)
    action = dict(state.get("last_action") or {})
    gate = check_finish(kernel.state.as_dict(), action.get("finish_reason"))
    if not gate["allowed"]:
        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": str(gate["reason"])})
        _emit(kernel, "graph.finish_blocked", state, reason=gate["reason"])
        return {
            "messages": messages,
            "route": "guard",
            "kernel_state": _kernel_snapshot(kernel),
        }

    final = str(action.get("message", ""))
    outcome = kernel.complete_task(final)
    _emit(kernel, "graph.completed", state, status="completed")
    return {
        "final": final,
        "outcome": outcome,
        "status": "completed",
        "route": "end",
        "kernel_state": _kernel_snapshot(kernel),
    }


def fail_node(state: AgentState, *, kernel: AgentKernel) -> dict[str, Any]:
    """Close a failed run through the same kernel lifecycle used by successful runs."""
    _restore_kernel(state, kernel)
    budget = budget_from_state(state)
    reason = str(state.get("error") or "agent run failed")
    outcome = kernel.fail_task(reason, steps=budget.steps, parse_errors=budget.parse_errors)
    _emit(kernel, "graph.completed", state, status="failed", reason=reason)
    return {
        "outcome": outcome,
        "status": "failed",
        "route": "end",
        "kernel_state": _kernel_snapshot(kernel),
    }
