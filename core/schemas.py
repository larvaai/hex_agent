"""Core data contracts: TaskEnvelope, ToolRequest, CapabilityResult envelope, FeatureDescriptor. Epic E01."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

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
    context: "ToolCallContext | None" = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True)
class ToolCallContext:
    """Immutable session lineage and scope; never forwarded as tool arguments."""

    run_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    parent_session_id: str | None = None
    delegation_id: str | None = None
    actor_id: str | None = None
    allowed_capabilities: frozenset[str] | None = None

    def event_fields(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "delegation_id": self.delegation_id,
            "actor_id": self.actor_id,
        }


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


@dataclass(frozen=True)
class DelegationSpec:
    objective: str
    input_context: dict[str, Any] = field(default_factory=dict)
    # E10 additions (backward compatible — both default to empty):
    expected_output_schema: dict[str, Any] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DelegationSpec":
        return cls(
            objective=str(data.get("objective", "")),
            input_context=dict(data.get("input_context") or {}),
            expected_output_schema=dict(data.get("expected_output_schema") or {}),
            constraints=tuple(str(c) for c in (data.get("constraints") or ())),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "input_context": dict(self.input_context),
            "expected_output_schema": dict(self.expected_output_schema),
            "constraints": list(self.constraints),
        }


@dataclass(frozen=True)
class DelegationPolicy:
    max_steps: int = 20
    max_depth: int = 3
    allowed_capabilities: frozenset[str] = frozenset()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DelegationPolicy":
        raw = data or {}
        return cls(
            max_steps=int(raw.get("max_steps", 20)),
            max_depth=int(raw.get("max_depth", 3)),
            allowed_capabilities=frozenset(str(item) for item in raw.get("allowed_capabilities") or ()),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_depth": self.max_depth,
            "allowed_capabilities": sorted(self.allowed_capabilities),
        }


@dataclass(frozen=True)
class DelegationRequest:
    delegation_id: str
    parent_session_id: str
    parent_task_id: str
    target: str
    spec: DelegationSpec
    policy: DelegationPolicy

    def as_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "parent_session_id": self.parent_session_id,
            "parent_task_id": self.parent_task_id,
            "target": self.target,
            "spec": self.spec.as_dict(),
            "policy": self.policy.as_dict(),
        }


@dataclass(frozen=True)
class ArtifactEnvelope:
    artifact_id: str
    kind: str
    payload: dict[str, Any]
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "schema_version": self.schema_version,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class DelegationProgress:
    delegation_id: str
    sequence: int
    event_id: str
    artifact: ArtifactEnvelope
    status: Literal["running", "waiting", "blocked"] = "running"

    def as_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "sequence": self.sequence,
            "event_id": self.event_id,
            "artifact": self.artifact.as_dict(),
            "status": self.status,
        }


@dataclass(frozen=True)
class DelegationResult:
    delegation_id: str
    parent_task_id: str
    outcome: Literal["success", "failed", "rejected", "timeout"]
    artifacts: tuple[ArtifactEnvelope, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "parent_task_id": self.parent_task_id,
            "outcome": self.outcome,
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "summary": dict(self.summary),
            "error": self.error,
        }
