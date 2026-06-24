"""Core data contracts: TaskEnvelope, ToolRequest, CapabilityResult envelope, FeatureDescriptor. Epic E01."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

_ENVELOPE_KEYS = {"ok", "capability", "feature", "data", "error", "metadata"}


@dataclass(frozen=True)
class TaskEnvelope:
    user_request: str
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def as_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "user_request": self.user_request,
                "context": dict(self.context), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskEnvelope":
        return cls(user_request=d.get("user_request", ""), context=dict(d.get("context") or {}),
                   metadata=dict(d.get("metadata") or {}), task_id=d.get("task_id") or uuid.uuid4().hex)


@dataclass(frozen=True)
class ToolRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)


def is_capability_result(result: Any) -> bool:
    return isinstance(result, dict) and _ENVELOPE_KEYS <= set(result)


@dataclass(frozen=True)
class CapabilityResult:
    """Uniform envelope every tool call returns."""

    ok: bool
    capability: str
    feature: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        *,
        capability: str,
        feature: str | None,
        result: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> "CapabilityResult":
        extra = dict(metadata or {})
        if is_capability_result(result):
            meta = dict(result.get("metadata") or {})
            meta.update(extra)
            return cls(
                ok=bool(result.get("ok")),
                capability=str(result.get("capability") or capability),
                feature=result.get("feature") if result.get("feature") is not None else feature,
                data=dict(result.get("data") or {}),
                error=result.get("error"),
                metadata=meta,
            )
        ok = bool(result.get("ok", False))
        error = None if ok else str(result.get("error") or "Capability execution failed.")
        data = {k: v for k, v in result.items() if k not in {"ok", "error", "metadata"}}
        meta = dict(result.get("metadata") or {})
        meta.update(extra)
        meta.setdefault("raw_keys", sorted(result))
        return cls(ok=ok, capability=capability, feature=feature, data=data, error=error, metadata=meta)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "capability": self.capability,
            "feature": self.feature,
            "data": dict(self.data),
            "error": self.error,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FeatureDescriptor:
    name: str
    version: str = "0.1"
    capabilities: tuple[str, ...] = ()
    enabled: bool = True
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "enabled": self.enabled,
            "description": self.description,
        }
