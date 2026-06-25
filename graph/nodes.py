"""LangGraph nodes; every external action still crosses AgentKernel.execute_tool."""
from __future__ import annotations

import json
from typing import Any

from core.ports import DelegationServicePort
from core.schemas import DelegationPolicy, DelegationSpec
from core.session import KernelSession
from discipline import Budget, JsonGateError, build_retry_message, check_finish, parse_action
from graph.state import (
    AgentState,
    budget_from_state,
    budget_to_dict,
    decode_session_state,
    encode_session_state,
)


def _restore_session(state: AgentState, session: KernelSession) -> None:
    raw = state.get("session_state") or state.get("kernel_state") or {}
    session.state.restore(decode_session_state(raw))


def _session_snapshot(session: KernelSession) -> dict[str, Any]:
    return encode_session_state(session.state.snapshot())


def _emit(session: KernelSession, topic: str, state: AgentState, **payload: Any) -> None:
    session.kernel.events.publish(
        topic,
        {
            **session.call_context().event_fields(),
            "step": budget_from_state(state).steps,
            **payload,
        },
    )


def guard_node(state: AgentState, *, session: KernelSession) -> dict[str, Any]:
    """Stop before the next LLM call once the valid-action budget is exhausted."""
    _restore_session(state, session)
    budget = budget_from_state(state)
    if budget.steps >= budget.max_steps:
        error = "step budget exceeded"
        _emit(session, "graph.budget_blocked", state, reason=error)
        return {"route": "fail", "error": error, "session_state": _session_snapshot(session)}
    return {"route": "agent", "session_state": _session_snapshot(session)}


def agent_node(state: AgentState, *, session: KernelSession) -> dict[str, Any]:
    """Call the LLM capability, parse one action, and update loop discipline."""
    _restore_session(state, session)
    messages = list(state.get("messages") or [])
    response = session.execute_tool(
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
        _emit(session, "graph.parse_error", state, error=str(exc), stage=exc.stage)
        if budget.parse_exceeded():
            return {
                "messages": messages,
                "budget": budget_to_dict(budget),
                "route": "fail",
                "error": "too many parse errors",
                "session_state": _session_snapshot(session),
            }
        messages.append({"role": "user", "content": build_retry_message(exc)})
        return {
            "messages": messages,
            "budget": budget_to_dict(budget),
            "route": "guard",
            "session_state": _session_snapshot(session),
        }

    budget.record_step()
    verb = str(action.get("action", ""))
    _emit(session, "graph.step", state, action=verb, next_step=budget.steps)
    update: dict[str, Any] = {
        "messages": messages,
        "budget": budget_to_dict(budget),
        "last_action": action,
        "session_state": _session_snapshot(session),
    }
    if verb == "tool":
        update["route"] = "tool"
    elif verb == "delegate":
        update["route"] = "delegate"
    elif verb == "final":
        update["route"] = "finish"
    else:
        messages.append({"role": "user", "content": "Unknown 'action'. Use 'tool' or 'final'."})
        update["messages"] = messages
        update["route"] = "guard"
    return update


def tool_node(state: AgentState, *, session: KernelSession) -> dict[str, Any]:
    """Execute a requested tool through the kernel and append its envelope to history."""
    _restore_session(state, session)
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
        _emit(session, "graph.budget_blocked", state, reason=error, tool=name)
        return {
            "budget": budget_to_dict(budget),
            "route": "fail",
            "error": error,
            "session_state": _session_snapshot(session),
        }

    result = session.execute_tool(name, args)
    messages = list(state.get("messages") or [])
    messages.append(
        {"role": "user", "content": json.dumps(result, ensure_ascii=False, default=str)}
    )
    return {
        "messages": messages,
        "budget": budget_to_dict(budget),
        "route": "guard",
        "session_state": _session_snapshot(session),
    }


def delegation_node(
    state: AgentState,
    *,
    session: KernelSession,
    delegation_service: DelegationServicePort | None,
) -> dict[str, Any]:
    """Call the framework-neutral delegation chokepoint and return a structured observation."""
    _restore_session(state, session)
    if delegation_service is None:
        return {
            "route": "fail",
            "error": "delegation is not configured",
            "session_state": _session_snapshot(session),
        }
    action = dict(state.get("last_action") or {})
    target = str(action.get("target", ""))
    spec_raw = action.get("spec") or {}
    policy_raw = action.get("policy") or {}
    if not target or not isinstance(spec_raw, dict) or not isinstance(policy_raw, dict):
        return {
            "route": "fail",
            "error": "delegate action requires target, object spec, and optional object policy",
            "session_state": _session_snapshot(session),
        }
    spec = DelegationSpec.from_dict(spec_raw)
    if not spec.objective:
        return {
            "route": "fail",
            "error": "delegation objective must not be empty",
            "session_state": _session_snapshot(session),
        }
    try:
        result = delegation_service.delegate(
            session,
            target,
            spec,
            DelegationPolicy.from_dict(policy_raw),
        )
    except Exception as exc:
        return {
            "route": "fail",
            "error": f"delegation failed at the application boundary: {exc}",
            "session_state": _session_snapshot(session),
        }
    observation = result.as_dict()
    messages = list(state.get("messages") or [])
    messages.append(
        {
            "role": "user",
            "content": "DELEGATION_RESULT: " + json.dumps(observation, ensure_ascii=False, default=str),
        }
    )
    return {
        "messages": messages,
        "active_delegation_id": None,
        "last_delegation_result": observation,
        "route": "guard",
        "session_state": _session_snapshot(session),
    }


def finish_node(state: AgentState, *, session: KernelSession) -> dict[str, Any]:
    """Apply the shared finish gate, then close the kernel lifecycle exactly once."""
    _restore_session(state, session)
    action = dict(state.get("last_action") or {})
    # An "error" finish (e.g. the LLM adapter exhausted retries) is a terminal failure,
    # not a completion — surface it through the fail path so the root cause is preserved
    # and the outcome status matches the UI's projection of an error final.
    if str(action.get("finish_reason")) == "error":
        reason = str(action.get("message", "")) or "agent finished with an error"
        outcome = session.fail_task(reason)
        _emit(session, "graph.completed", state, status="failed", reason=reason)
        return {
            "final": reason,
            "outcome": outcome,
            "status": "failed",
            "route": "end",
            "session_state": _session_snapshot(session),
        }
    gate = check_finish(session.state.as_dict(), action.get("finish_reason"))
    if not gate["allowed"]:
        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": str(gate["reason"])})
        _emit(session, "graph.finish_blocked", state, reason=gate["reason"])
        return {
            "messages": messages,
            "route": "guard",
            "session_state": _session_snapshot(session),
        }

    final = str(action.get("message", ""))
    outcome = session.complete_task(final)
    _emit(session, "graph.completed", state, status="completed")
    return {
        "final": final,
        "outcome": outcome,
        "status": "completed",
        "route": "end",
        "session_state": _session_snapshot(session),
    }


def fail_node(state: AgentState, *, session: KernelSession) -> dict[str, Any]:
    """Close a failed run through the same kernel lifecycle used by successful runs."""
    _restore_session(state, session)
    budget = budget_from_state(state)
    reason = str(state.get("error") or "agent run failed")
    outcome = session.fail_task(reason, steps=budget.steps, parse_errors=budget.parse_errors)
    _emit(session, "graph.completed", state, status="failed", reason=reason)
    return {
        "outcome": outcome,
        "status": "failed",
        "route": "end",
        "session_state": _session_snapshot(session),
    }
