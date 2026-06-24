"""CapabilityRegistry + NullToolPort — resolve a tool name to an executor, with graceful fallback. Epic E01."""
from __future__ import annotations

from typing import Any, NamedTuple

from core.schemas import FeatureDescriptor, ToolRequest


class ToolResolution(NamedTuple):
    executor: Any
    feature: str | None


class NullToolPort:
    """Keeps the kernel alive when a tool is missing."""

    name = "null_tool"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {
            "ok": False,
            "tool": request.name,
            "missing_capability": True,
            "error": f"No tool capability is registered for '{request.name}'.",
        }


class CapabilityRegistry:
    """Exact registration wins; optional fallback; else NullToolPort."""

    def __init__(self, *, null_tool: Any = None) -> None:
        self._tools: dict[str, Any] = {}
        self._features: dict[str, FeatureDescriptor] = {}
        self._tool_features: dict[str, str] = {}
        self._fallback: Any = None
        self._fallback_feature: str | None = None
        self._null = null_tool or NullToolPort()
        self._frozen = False

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError("Capability registry is frozen for active sessions.")

    def freeze(self) -> None:
        self._frozen = True

    def register_feature(self, descriptor: FeatureDescriptor) -> None:
        self._ensure_mutable()
        self._features[descriptor.name] = descriptor

    def register_tool(self, name: str, executor: Any, *, feature_name: str | None = None) -> None:
        self._ensure_mutable()
        self._tools[name] = executor
        if feature_name:
            self._tool_features[name] = feature_name

    def register_tools(self, names, executor: Any, *, feature_name: str | None = None) -> None:
        for name in names:
            self.register_tool(name, executor, feature_name=feature_name)

    def set_fallback_tool_executor(self, executor: Any, *, feature_name: str | None = None) -> None:
        self._ensure_mutable()
        self._fallback = executor
        self._fallback_feature = feature_name if executor is not None else None

    def resolve_tool(self, name: str) -> ToolResolution:
        if name in self._tools:
            return ToolResolution(self._tools[name], self._tool_features.get(name))
        if self._fallback is not None:
            return ToolResolution(self._fallback, self._fallback_feature)
        return ToolResolution(self._null, None)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"name": n, "feature": self._tool_features.get(n)} for n in sorted(self._tools)]

    def list_features(self) -> list[dict[str, Any]]:
        return [d.as_dict() for d in self._features.values()]
