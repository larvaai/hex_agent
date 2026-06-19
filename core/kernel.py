"""AgentKernel — minimal core owning state, events, and capability execution. Epic E01."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.events import EventBus
from core.registry import CapabilityRegistry
from core.schemas import CapabilityResult, TaskEnvelope, ToolRequest
from core.state import StateStore


@dataclass
class AgentKernel:
    """
    Minimal living core. Owns state, events, capability lookup.
    Concrete behavior lives behind ports/adapters in the registry.
    """

    registry: CapabilityRegistry
    events: EventBus
    state: StateStore
    config: dict[str, Any] = field(default_factory=dict)

    def accept_task(self, user_request: str, context: dict[str, Any] | None = None) -> TaskEnvelope:
        task = TaskEnvelope(user_request=user_request, context=context or {})
        self.state.set("current_task", task)
        self.events.publish("task.accepted", {"task_id": task.task_id})
        return task

    def _current_task_id(self) -> str | None:
        task = self.state.get("current_task")
        return getattr(task, "task_id", None)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ToolRequest(name=tool_name, args=args or {})
        task_id = self._current_task_id()
        self.events.publish(
            "tool.requested",
            {"task_id": task_id, "tool": request.name, "request_id": request.request_id, "args": request.args},
        )

        resolution = self.registry.resolve_tool(request.name)
        try:
            result = resolution.executor.execute(request)
        except Exception as exc:  # a tool must never crash the kernel
            result = {"ok": False, "tool": request.name, "error": str(exc), "kernel_error": True}

        if not isinstance(result, dict):
            result = {
                "ok": False,
                "tool": request.name,
                "error": f"Tool returned {type(result).__name__}, expected dict.",
                "kernel_error": True,
            }

        envelope = CapabilityResult.from_raw(
            capability=request.name,
            feature=resolution.feature,
            result=result,
            metadata={
                "task_id": task_id,
                "request_id": request.request_id,
                "executor": getattr(resolution.executor, "name", resolution.executor.__class__.__name__),
            },
        ).as_dict()

        self.events.publish(
            "tool.completed" if envelope.get("ok") else "tool.failed",
            {
                "task_id": task_id,
                "tool": request.name,
                "request_id": request.request_id,
                "ok": bool(envelope.get("ok")),
                "error": envelope.get("error"),
            },
        )
        return envelope

    def describe_capabilities(self) -> dict[str, Any]:
        return {"features": self.registry.list_features(), "tools": self.registry.list_tools()}
