"""Shared, frozen capability runtime; per-run state and lifecycle live in KernelSession."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from core.events import EventBus
from core.registry import CapabilityRegistry
from core.schemas import CapabilityResult, ToolCallContext, ToolRequest


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_deep_freeze(item) for item in value)
    return value


class _LatchedNext:
    """One-shot proxy around the inner handler. Runs it at most once; later calls replay the
    first outcome (result or exception) WITHOUT re-executing. Guards a fail-open middleware that
    raises *after* already invoking nxt from double-running the tool (FM-HIGH, non-idempotent)."""

    __slots__ = ("_nxt", "_ran", "_result", "_exc")

    def __init__(self, nxt) -> None:
        self._nxt = nxt
        self._ran = False
        self._result: Any = None
        self._exc: Exception | None = None

    def __call__(self, request: ToolRequest) -> dict[str, Any]:
        if not self._ran:
            self._ran = True
            try:
                self._result = self._nxt(request)
            except Exception as exc:  # store so the skip-fallback replays, never re-runs
                self._exc = exc
        if self._exc is not None:
            raise self._exc
        return self._result


def _wrap(middleware, nxt, on_skip=None):
    """Bind one middleware around the next handler (avoids late-binding closure bug).

    Default posture is **fail-closed**: a raising middleware propagates to the kernel boundary
    (ok=False). A middleware that opts in with ``fail_open = True`` (advisory — telemetry/condense)
    is **skipped** when it raises: the chain continues with the inner result. Its ``nxt`` is latched
    (one-shot) so a post-nxt raise cannot re-execute the tool. Only the fail-open branch latches —
    fail-closed (incl. Retry, which calls nxt repeatedly by design) gets the raw ``nxt``.
    """
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> dict[str, Any]:
            return middleware(request, nxt)

        return handler

    def handler(request: ToolRequest) -> dict[str, Any]:
        latched = _LatchedNext(nxt)
        try:
            return middleware(request, latched)
        except Exception as exc:  # advisory failed → skip it, keep the (latched) inner result
            if on_skip is not None:
                on_skip(middleware, exc)
            return latched(request)

    return handler


@dataclass
class AgentKernel:
    """
    Minimal living core. Owns shared events, capability lookup, and execution.
    Per-run state and task lifecycle belong to KernelSession.
    Concrete behavior lives behind ports/adapters in the registry; cross-cutting
    behavior lives in middleware around the single execute_tool chokepoint.
    """

    registry: CapabilityRegistry
    events: EventBus
    config: Mapping[str, Any] = field(default_factory=dict)
    _middlewares: list = field(default_factory=list)
    _frozen: bool = False

    def freeze(self) -> None:
        """Freeze shared mutable configuration before the first session starts."""
        if self._frozen:
            return
        self.registry.freeze()
        self.config = _deep_freeze(copy.deepcopy(dict(self.config)))
        self._frozen = True

    # ----- capability chokepoint -----
    def use(self, middleware) -> None:
        """Register a ToolMiddleware. Registration order = outer -> inner."""
        if self._frozen:
            raise RuntimeError("Middleware pipeline is frozen for active sessions.")
        self._middlewares.append(middleware)

    def execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        context: ToolCallContext | None = None,
    ) -> dict[str, Any]:
        # Deep-copy args so a tool can never mutate the caller's object through request.args.
        request = ToolRequest(name=tool_name, args=copy.deepcopy(args) if args else {}, context=context)
        lineage = context.event_fields() if context is not None else {
            "run_id": None,
            "task_id": None,
            "session_id": None,
            "parent_session_id": None,
            "delegation_id": None,
            "actor_id": None,
        }
        self.events.publish(
            "tool.requested",
            {**lineage, "tool": request.name, "request_id": request.request_id, "args": request.args},
        )

        if context is not None and context.allowed_capabilities is not None:
            if request.name not in context.allowed_capabilities:
                envelope = CapabilityResult(
                    ok=False,
                    capability=request.name,
                    error=f"Capability outside session scope: {request.name}",
                    metadata={
                        **lineage,
                        "request_id": request.request_id,
                        "scope_block": True,
                    },
                ).as_dict()
                self.events.publish(
                    "tool.failed",
                    {
                        **lineage,
                        "tool": request.name,
                        "request_id": request.request_id,
                        "ok": False,
                        "error": envelope["error"],
                    },
                )
                return envelope

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
                    **lineage,
                    "request_id": req.request_id,
                    "executor": getattr(resolution.executor, "name", resolution.executor.__class__.__name__),
                    "kind": resolution.descriptor.kind,
                    "idempotent": resolution.descriptor.idempotent,
                    "risk": resolution.descriptor.risk,
                },
            ).as_dict()

        def on_skip(mw: Any, exc: Exception) -> None:
            # A fail-open (advisory) middleware raised and was skipped — make it observable.
            self.events.publish(
                "middleware.skipped",
                {
                    **lineage,
                    "tool": request.name,
                    "request_id": request.request_id,
                    "middleware": getattr(mw, "name", type(mw).__name__),
                    "error": str(exc),
                },
            )

        handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler, on_skip=on_skip)
        try:
            envelope = handler(request)
        except Exception as exc:  # a middleware must never crash the kernel boundary
            envelope = CapabilityResult(
                ok=False,
                capability=request.name,
                error=str(exc),
                metadata={**lineage, "request_id": request.request_id, "kernel_error": True},
            ).as_dict()

        if not isinstance(envelope, dict):  # a misbehaving middleware must not crash the kernel
            envelope = {
                "ok": False, "capability": request.name, "feature": None, "data": {},
                "error": f"Middleware returned {type(envelope).__name__}, expected dict.", "metadata": {},
            }
        meta = envelope.setdefault("metadata", {})
        for key, value in lineage.items():
            meta.setdefault(key, value)
        meta.setdefault("request_id", request.request_id)

        self.events.publish(
            "tool.completed" if envelope.get("ok") else "tool.failed",
            {
                **lineage,
                "tool": request.name,
                "request_id": request.request_id,
                "ok": bool(envelope.get("ok")),
                "error": envelope.get("error"),
            },
        )
        return envelope

    def describe_capabilities(self) -> dict[str, Any]:
        return {"features": self.registry.list_features(), "tools": self.registry.list_tools()}
