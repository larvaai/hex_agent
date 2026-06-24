"""E05 — single-agent loop with checkpoint/resume. Drives the kernel; reuses discipline. Lives OUTSIDE the kernel."""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from core.kernel import AgentKernel
from discipline import Budget, JsonGateError, build_retry_message, check_finish, parse_action
from orchestrator.checkpoint import Checkpoint, load_checkpoint, save_checkpoint

DEFAULT_SYSTEM = (
    "You are an agent. Think, then act. Reply with EXACTLY ONE JSON object and nothing else.\n"
    'Tool call:  {"action":"tool","tool":"<name>","args":{...}}\n'
    'Finish:     {"action":"final","message":"<answer>","finish_reason":"done"}'
)


def run(kernel: AgentKernel, user_request: str, *, budget: Budget | None = None,
        system_prompt: str = DEFAULT_SYSTEM, context: dict[str, Any] | None = None,
        run_id: str | None = None, checkpoint: bool = True) -> dict[str, Any]:
    """Run a task to completion, checkpointing each step. run_id defaults to the task_id;
    pass the same id you gave EventLogger to co-locate checkpoint.json with events.jsonl."""
    task = kernel.accept_task(user_request, context)
    budget = budget or Budget()
    rid = run_id or task.task_id
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request}]
    return _drive(kernel, run_id=rid, task=user_request, messages=messages, budget=budget, checkpoint=checkpoint)


def resume(kernel: AgentKernel, run_id: str, *, checkpoint: bool = True) -> dict[str, Any]:
    """Reload a run's checkpoint and continue from where it stopped (same task_id preserved)."""
    cp = load_checkpoint(run_id)
    if cp is None:
        raise FileNotFoundError(f"No checkpoint for run_id={run_id!r}")
    kernel.state.restore(cp.state)
    if cp.status != "running":
        return kernel.state.get("last_result") or {"task_id": None, "status": cp.status, "result": None}
    budget = Budget(**cp.budget)
    return _drive(kernel, run_id=run_id, task=cp.task, messages=cp.messages, budget=budget, checkpoint=checkpoint)


def _drive(kernel: AgentKernel, *, run_id: str, task: str, messages: list[dict[str, str]],
           budget: Budget, checkpoint: bool) -> dict[str, Any]:
    def save(status: str = "running") -> None:
        save_checkpoint(
            Checkpoint(run_id=run_id, task=task, messages=messages,
                       budget=dataclasses.asdict(budget), state=kernel.state.snapshot(),
                       step=budget.steps, status=status),
            enabled=checkpoint,
        )

    save()  # checkpoint the starting point so even a step-1 crash is resumable
    while True:
        if budget.step_exceeded():
            out = kernel.fail_task("step budget exceeded", steps=budget.steps)
            save("failed")
            return out

        resp = kernel.execute_tool("llm.chat", {"messages": messages, "json_mode": True})
        content = (resp.get("data") or {}).get("content", "")
        messages.append({"role": "assistant", "content": content})

        try:
            action = parse_action(content)
        except JsonGateError as exc:
            budget.record_parse_error()
            if budget.parse_exceeded():
                out = kernel.fail_task("too many parse errors", parse_errors=budget.parse_errors)
                save("failed")
                return out
            messages.append({"role": "user", "content": build_retry_message(exc)})
            save()
            continue

        budget.record_step()
        verb = action.get("action")

        if verb == "final":
            gate = check_finish(kernel.state.as_dict(), action.get("finish_reason"))
            if not gate["allowed"]:
                messages.append({"role": "user", "content": gate["reason"]})
                save()
                continue
            out = kernel.complete_task(action.get("message"))
            save("completed")
            return out

        if verb == "tool":
            result = kernel.execute_tool(action.get("tool", ""), action.get("args", {}))
            messages.append({"role": "user", "content": json.dumps(result, ensure_ascii=False)})
            save()
            continue

        messages.append({"role": "user", "content": "Unknown 'action'. Use 'tool' or 'final'."})
        save()
