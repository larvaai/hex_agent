"""Compile the session-bound LangGraph; delegation remains an injected application port."""
from __future__ import annotations

from functools import partial
from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from core.kernel import AgentKernel
from core.ports import DelegationServicePort
from core.schemas import FeatureDescriptor, ToolRequest
from core.session import KernelSession, SessionFactory
from discipline import Budget
from graph.nodes import agent_node, delegation_node, fail_node, finish_node, guard_node, tool_node
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


def build_agent_graph(
    *,
    session: KernelSession,
    checkpointer=None,
    delegation_service: DelegationServicePort | None = None,
):
    """Build the sole orchestration graph around an isolated runtime session."""
    builder = StateGraph(AgentState)
    builder.add_node("guard", partial(guard_node, session=session))
    builder.add_node("agent", partial(agent_node, session=session))
    builder.add_node("tool", partial(tool_node, session=session))
    builder.add_node(
        "delegate",
        partial(delegation_node, session=session, delegation_service=delegation_service),
    )
    builder.add_node("finish", partial(finish_node, session=session))
    builder.add_node("fail", partial(fail_node, session=session))

    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", _route, {"agent": "agent", "fail": "fail"})
    builder.add_conditional_edges(
        "agent",
        _route,
        {
            "tool": "tool",
            "delegate": "delegate",
            "finish": "finish",
            "guard": "guard",
            "fail": "fail",
        },
    )
    builder.add_conditional_edges("tool", _route, {"guard": "guard", "fail": "fail"})
    builder.add_conditional_edges("delegate", _route, {"guard": "guard", "fail": "fail"})
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
    session = SessionFactory(kernel=kernel).create_root(
        task,
        run_id=logger.run_id,
        agent_id="agent:compat",
    )
    initial = new_agent_state(
        session=session,
        messages=[
            {"role": "system", "content": COMPAT_SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ],
        budget=Budget(max_steps=max_steps),
        model=model,
    )
    graph = build_agent_graph(session=session, checkpointer=InMemorySaver())
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
