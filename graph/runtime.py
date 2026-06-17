"""Single-agent graph runtime: agent<->tool loop with discipline, budget, finish-gate, events. Epic E05.

Single-agent = one agent node + one tool node. Multi-agent (E10) reuses the same nodes/loop by
adding role nodes + a router; the loop and discipline below do not change.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from core.kernel import AgentKernel
from discipline import Budget, check_finish
from graph.nodes import agent_node, tool_node
from graph.state import AgentState
from observability import EventLogger, attach_to_bus


def run_agent(
    task: str,
    *,
    kernel: AgentKernel,
    llm_call: Callable[..., str],
    model: str | None = None,
    max_steps: int = 12,
    logger: EventLogger | None = None,
) -> dict[str, Any]:
    state = AgentState(task=task)
    if logger is None:
        logger = EventLogger()
        attach_to_bus(logger, kernel.events)
    budget = Budget(max_steps=max_steps)
    kernel.accept_task(task)

    while True:
        if budget.step_exceeded():
            state.final = state.final or "Stopped: step budget exceeded."
            logger.emit("StateEvent", status="budget_exceeded", step=state.step)
            break

        budget.record_step()
        logger.count("steps")
        state.step += 1

        action = agent_node(state, llm_call=llm_call, model=model)
        logger.count("llm_calls")
        kind = action.get("action")
        logger.emit("MessageEvent", role="assistant", step=state.step, action=kind)

        if kind == "retry":
            budget.record_parse_error()
            logger.count("parse_errors")
            if budget.parse_exceeded():
                state.final = "Stopped: too many invalid JSON responses."
                logger.emit("StateEvent", status="parse_budget_exceeded")
                break
            state.messages.append({"role": "user", "content": action.get("retry_message", "Return valid JSON.")})
            continue

        if kind == "final":
            gate = check_finish(
                {"code_changed": state.code_changed, "validation_passed": state.validation_passed},
                action.get("finish_reason"),
            )
            if not gate["allowed"]:
                logger.count("finish_gate_blocks")
                logger.emit("StateEvent", status="finish_gate_blocked", reason=gate["reason"])
                state.messages.append({"role": "user", "content": "Finish blocked: " + gate["reason"]})
                continue
            state.final = str(action.get("message", ""))
            logger.emit("ActionEvent", action="final", step=state.step)
            break

        if kind == "tool":
            key = Budget.tool_key(str(action.get("tool", "")), action.get("args") or {})
            budget.record_tool_call(key)
            logger.emit("ActionEvent", action="tool", tool=action.get("tool"), step=state.step)
            if budget.same_tool_exceeded(key):
                state.final = "Stopped: repeated the same tool call too many times."
                logger.emit("StateEvent", status="tool_loop", tool=action.get("tool"))
                break
            observation = tool_node(action, kernel=kernel)
            logger.count("condensed")
            state.messages.append({"role": "user", "content": "OBSERVATION: " + json.dumps(observation, ensure_ascii=False)})
            continue

        # unknown action shape
        state.messages.append({"role": "user", "content": "Unknown action; use action=tool or action=final."})

    summary = logger.finish("completed" if state.final else "incomplete", steps=state.step)
    return {"final": state.final, "steps": state.step, "run_id": summary["run_id"]}
