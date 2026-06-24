"""Compile the single-agent LangGraph; no handwritten agent loop lives here."""
from __future__ import annotations

from functools import partial
from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor, ToolRequest
from discipline import Budget
from graph.nodes import agent_node, fail_node, finish_node, guard_node, tool_node
from graph.state import AgentState, budget_from_state, new_agent_state
from observability import EventLogger, attach_to_bus

COMPAT_SYSTEM_PROMPT = (
    "You are a tool-using agent. Respond with exactly ONE JSON object, no markdown, no prose:\n"
    '  {"action": "tool", "tool": "<name>", "args": {...}}  to call a tool, or\n'
    '  {"action": "final", "message": "<answer>"}  to finish.\n'
    "Use only tools that exist. After enough evidence, return a final answer."
)


def _route(state: AgentState) -> str:
    return str(state.get("route") or "fail")


def build_agent_graph(*, kernel: AgentKernel, checkpointer=None):
    """Build and compile the sole orchestration graph around a runtime kernel."""
    builder = StateGraph(AgentState)
    builder.add_node("guard", partial(guard_node, kernel=kernel))
    builder.add_node("agent", partial(agent_node, kernel=kernel))
    builder.add_node("tool", partial(tool_node, kernel=kernel))
    builder.add_node("finish", partial(finish_node, kernel=kernel))
    builder.add_node("fail", partial(fail_node, kernel=kernel))

    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", _route, {"agent": "agent", "fail": "fail"})
    builder.add_conditional_edges(
        "agent",
        _route,
        {"tool": "tool", "finish": "finish", "guard": "guard", "fail": "fail"},
    )
    builder.add_conditional_edges("tool", _route, {"guard": "guard", "fail": "fail"})
    builder.add_conditional_edges("finish", _route, {"guard": "guard", "end": END})
    builder.add_edge("fail", END)
    return builder.compile(checkpointer=checkpointer, name="core-agent")


class _CallableLLMTool:
    """Compatibility adapter for the old run_agent(..., llm_call=...) test seam."""

    name = "callable_llm_tool"

    def __init__(self, llm_call: Callable[..., str]) -> None:
        self.llm_call = llm_call

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        args = request.args
        return {
            "ok": True,
            "content": self.llm_call(args.get("messages", []), model=args.get("model")),
        }


def run_agent(
    task: str,
    *,
    kernel: AgentKernel,
    llm_call: Callable[..., str],
    model: str | None = None,
    max_steps: int = 12,
    logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Backward-compatible facade implemented on the same compiled StateGraph."""
    feature = FeatureDescriptor(name="llm_callable", capabilities=("llm.chat",))
    kernel.registry.register_feature(feature)
    kernel.registry.register_tool("llm.chat", _CallableLLMTool(llm_call), feature_name=feature.name)

    if logger is None:
        logger = EventLogger()
        attach_to_bus(logger, kernel.events)
    task_envelope = kernel.accept_task(task)
    initial = new_agent_state(
        run_id=logger.run_id,
        task=task_envelope,
        messages=[
            {"role": "system", "content": COMPAT_SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ],
        budget=Budget(max_steps=max_steps),
        kernel_state=kernel.state.snapshot(),
        model=model,
    )
    graph = build_agent_graph(kernel=kernel, checkpointer=InMemorySaver())
    config = {
        "configurable": {"thread_id": logger.run_id},
        "recursion_limit": max(100, max_steps * 4 + 20),
    }
    final_state: AgentState = initial
    for final_state in graph.stream(initial, config, stream_mode="values"):
        pass
    budget = budget_from_state(final_state)
    status = str(final_state.get("status") or "incomplete")
    summary = logger.finish(status, steps=budget.steps)
    return {"final": final_state.get("final"), "steps": budget.steps, "run_id": summary["run_id"]}
