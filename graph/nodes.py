"""Graph nodes: agent (LLM -> action via discipline) and tool (execute via kernel). Epic E05."""
from __future__ import annotations

from typing import Any, Callable

from core.kernel import AgentKernel
from discipline import JsonGateError, build_retry_message, condense, parse_action
from graph.state import AgentState

SYSTEM_PROMPT = (
    "You are a tool-using agent. Respond with exactly ONE JSON object, no markdown, no prose:\n"
    '  {"action": "tool", "tool": "<name>", "args": {...}}  to call a tool, or\n'
    '  {"action": "final", "message": "<answer>"}  to finish.\n'
    "Use only tools that exist. After enough evidence, return a final answer."
)


def agent_node(state: AgentState, *, llm_call: Callable[..., str], model: str | None = None) -> dict[str, Any]:
    """Build the prompt, call the LLM, parse the action via the discipline gate."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": state.task}]
    messages += state.messages
    raw = llm_call(messages, model=model)
    try:
        return parse_action(raw)
    except JsonGateError as exc:
        return {"action": "retry", "error": str(exc), "retry_message": build_retry_message(exc)}


def tool_node(action: dict[str, Any], *, kernel: AgentKernel) -> Any:
    """Execute the requested tool through the kernel and condense the result."""
    name = str(action.get("tool", ""))
    args = action.get("args") or {}
    result = kernel.execute_tool(name, args if isinstance(args, dict) else {})
    return condense(result)
