"""AgentKernel — minimal core: state, events, capability chokepoint, task lifecycle. Epic E01/E05."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.events import EventBus
from core.registry import CapabilityRegistry
from core.schemas import CapabilityResult, TaskEnvelope, ToolRequest
from core.state import StateStore


def _wrap(middleware, nxt):
    """Bind one middleware around the next handler (avoids late-binding closure bug)."""

    def handler(request: ToolRequest) -> dict[str, Any]:
        return middleware(request, nxt)

    return handler


@dataclass
class AgentKernel:
    """
    Minimal living core. Owns state, events, capability lookup, task lifecycle.
    Concrete behavior lives behind ports/adapters in the registry; cross-cutting
    behavior lives in middleware around the single execute_tool chokepoint.
    """

    registry: CapabilityRegistry
    events: EventBus
    state: StateStore
    config: dict[str, Any] = field(default_factory=dict)
    _middlewares: list = field(default_factory=list)

    # ----- task lifecycle -----
    def accept_task(self, user_request: str, context: dict[str, Any] | None = None) -> TaskEnvelope:
        task = TaskEnvelope(user_request=user_request, context=context or {})
        self.state.set("current_task", task)
        self.events.publish("task.accepted", {"task_id": task.task_id})
        return task

    def complete_task(self, result: Any = None, *, status: str = "completed") -> dict[str, Any]:
        task_id = self._current_task_id()
        outcome = {"task_id": task_id, "status": status, "result": result}
        self.state.set("last_result", outcome)
        self.state.set("current_task", None)
        self.events.publish(
            "task.completed" if status == "completed" else "task.failed",
            {"task_id": task_id, "status": status},
        )
        return outcome

    def fail_task(self, reason: str, **extra: Any) -> dict[str, Any]:
        return self.complete_task({"reason": reason, **extra}, status="failed")

    def _current_task_id(self) -> str | None:
        task = self.state.get("current_task")
        return getattr(task, "task_id", None)

    # ----- capability chokepoint -----
    def use(self, middleware) -> None:
        """Register a ToolMiddleware. Registration order = outer -> inner."""
        self._middlewares.append(middleware)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ToolRequest(name=tool_name, args=args or {})
        task_id = self._current_task_id()
        self.events.publish(
            "tool.requested",
            {"task_id": task_id, "tool": request.name, "request_id": request.request_id, "args": request.args},
        )

        def core(req: ToolRequest) -> dict[str, Any]:
            resolution = self.registry.resolve_tool(req.name)
            try:
                result = resolution.executor.execute(req)
            except Exception as exc:  # a tool must never crash the kernel
                result = {"ok": False, "tool": req.name, "error": str(exc), "kernel_error": True}
            if not isinstance(result, dict):
                result = {
                    "ok": False,
                    "tool": req.name,
                    "error": f"Tool returned {type(result).__name__}, expected dict.",
                    "kernel_error": True,
                }
            return CapabilityResult.from_raw(
                capability=req.name,
                feature=resolution.feature,
                result=result,
                metadata={
                    "task_id": task_id,
                    "request_id": req.request_id,
                    "executor": getattr(resolution.executor, "name", resolution.executor.__class__.__name__),
                },
            ).as_dict()

        handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler)
        envelope = handler(request)

        if not isinstance(envelope, dict):  # a misbehaving middleware must not crash the kernel
            envelope = {
                "ok": False, "capability": request.name, "feature": None, "data": {},
                "error": f"Middleware returned {type(envelope).__name__}, expected dict.", "metadata": {},
            }
        meta = envelope.setdefault("metadata", {})
        meta.setdefault("task_id", task_id)
        meta.setdefault("request_id", request.request_id)

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
