"""Per-run state/lifecycle isolation over a shared, frozen AgentKernel."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from core.schemas import TaskEnvelope, ToolCallContext
from core.state import StateStore

if TYPE_CHECKING:
    from core.kernel import AgentKernel


@dataclass(frozen=True)
class SessionIdentity:
    session_id: str
    run_id: str
    task_id: str
    agent_id: str
    parent_session_id: str | None = None
    delegation_id: str | None = None
    depth: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "parent_session_id": self.parent_session_id,
            "delegation_id": self.delegation_id,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionIdentity":
        return cls(
            session_id=str(data["session_id"]),
            run_id=str(data["run_id"]),
            task_id=str(data["task_id"]),
            agent_id=str(data.get("agent_id") or "agent:root"),
            parent_session_id=data.get("parent_session_id"),
            delegation_id=data.get("delegation_id"),
            depth=int(data.get("depth", 0)),
        )


@dataclass
class KernelSession:
    """Owns one task's mutable state; shared services remain on the kernel."""

    kernel: "AgentKernel"
    identity: SessionIdentity
    state: StateStore
    allowed_capabilities: frozenset[str]
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def is_active(self) -> bool:
        return not self._closed and isinstance(self.state.get("current_task"), TaskEnvelope)

    def call_context(self) -> ToolCallContext:
        identity = self.identity
        return ToolCallContext(
            run_id=identity.run_id,
            task_id=identity.task_id,
            session_id=identity.session_id,
            parent_session_id=identity.parent_session_id,
            delegation_id=identity.delegation_id,
            actor_id=identity.agent_id,
            allowed_capabilities=self.allowed_capabilities,
        )

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.is_active:
            return {
                "ok": False,
                "capability": tool_name,
                "feature": None,
                "data": {},
                "error": "Session is not active.",
                "metadata": {**self.call_context().event_fields(), "session_closed": True},
            }
        return self.kernel.execute_tool(tool_name, args, context=self.call_context())

    def complete_task(self, result: Any = None, *, status: str = "completed") -> dict[str, Any]:
        if not self.is_active:
            raise RuntimeError("Session task lifecycle is already closed.")
        outcome = {"task_id": self.identity.task_id, "status": status, "result": result}
        self.state.set("last_result", outcome)
        self.state.set("current_task", None)
        self._closed = True
        self.kernel.events.publish(
            "task.completed" if status == "completed" else "task.failed",
            {**self.call_context().event_fields(), "status": status},
        )
        return outcome

    def fail_task(self, reason: str, **extra: Any) -> dict[str, Any]:
        return self.complete_task({"reason": reason, **extra}, status="failed")


class SessionFactory:
    """The only constructor for root/child sessions; AgentKernel never creates sessions."""

    def __init__(self, *, kernel: "AgentKernel") -> None:
        self.kernel = kernel

    def _effective_root_scope(self, requested: frozenset[str] | None) -> frozenset[str]:
        available = frozenset(item["name"] for item in self.kernel.registry.list_tools())
        if requested is None:
            return available
        if not requested <= available:
            unknown = sorted(requested - available)
            raise ValueError(f"Root session requested unknown capabilities: {unknown}")
        return requested

    def create_root(
        self,
        user_request: str,
        *,
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
        agent_id: str = "agent:root",
        allowed_capabilities: frozenset[str] | None = None,
        task_id: str | None = None,
    ) -> KernelSession:
        task = TaskEnvelope(
            user_request=user_request,
            context=context or {},
            task_id=task_id or uuid.uuid4().hex,
        )
        identity = SessionIdentity(
            session_id=uuid.uuid4().hex,
            run_id=run_id or task.task_id,
            task_id=task.task_id,
            agent_id=agent_id,
        )
        scope = self._effective_root_scope(allowed_capabilities)
        self.kernel.freeze()
        state = StateStore()
        state.set("current_task", task)
        session = KernelSession(self.kernel, identity, state, scope)
        self.kernel.events.publish("task.accepted", session.call_context().event_fields())
        return session

    def create_child(
        self,
        parent: KernelSession,
        *,
        delegation_id: str,
        target: str,
        user_request: str,
        context: dict[str, Any] | None = None,
        requested_scope: frozenset[str] | None = None,
    ) -> KernelSession:
        if not parent.is_active:
            raise RuntimeError("Cannot create a child from an inactive parent session.")
        scope = parent.allowed_capabilities if not requested_scope else requested_scope
        if not scope <= parent.allowed_capabilities:
            raise PermissionError("Child capability scope must be a subset of the parent scope.")
        task = TaskEnvelope(
            user_request=user_request,
            context=context or {},
            metadata={
                "parent_session_id": parent.identity.session_id,
                "delegation_id": delegation_id,
            },
        )
        identity = SessionIdentity(
            session_id=uuid.uuid4().hex,
            run_id=parent.identity.run_id,
            task_id=task.task_id,
            agent_id=target,
            parent_session_id=parent.identity.session_id,
            delegation_id=delegation_id,
            depth=parent.identity.depth + 1,
        )
        state = StateStore()
        state.set("current_task", task)
        session = KernelSession(self.kernel, identity, state, frozenset(scope))
        self.kernel.events.publish("task.accepted", session.call_context().event_fields())
        return session

    def restore(
        self,
        *,
        identity: SessionIdentity,
        state: dict[str, Any],
        allowed_capabilities: frozenset[str],
    ) -> KernelSession:
        self.kernel.freeze()
        if not allowed_capabilities <= self._effective_root_scope(None):
            raise ValueError("Persisted session contains capabilities unavailable in this runtime.")
        store = StateStore()
        store.restore(state)
        session = KernelSession(self.kernel, identity, store, allowed_capabilities)
        if not isinstance(store.get("current_task"), TaskEnvelope):
            session._closed = True
        return session
