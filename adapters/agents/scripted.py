"""Deterministic delegation adapter for tests and local architecture smoke runs."""
from __future__ import annotations

import uuid
from typing import Any

from core.ports import ProgressSink
from core.schemas import (
    ArtifactEnvelope,
    DelegationProgress,
    DelegationRequest,
    DelegationResult,
)
from core.session import KernelSession


class ScriptedDelegationAgent:
    def __init__(self, target: str, artifacts: list[dict[str, Any]] | None = None) -> None:
        self.name = target
        self.target = target
        self.artifacts = list(artifacts or [])

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(
        self,
        request: DelegationRequest,
        child_session: KernelSession,
        progress_sink: ProgressSink,
    ) -> DelegationResult:
        emitted: list[ArtifactEnvelope] = []
        for sequence, payload in enumerate(self.artifacts, start=1):
            artifact = ArtifactEnvelope(
                artifact_id=uuid.uuid4().hex,
                kind=str(payload.get("kind") or "scripted"),
                payload=dict(payload),
            )
            emitted.append(artifact)
            progress_sink(
                DelegationProgress(
                    delegation_id=request.delegation_id,
                    sequence=sequence,
                    event_id=uuid.uuid4().hex,
                    artifact=artifact,
                )
            )
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            artifacts=tuple(emitted),
            summary={
                "target": request.target,
                "objective": request.spec.objective,
                "artifact_count": len(emitted),
                "child_session_id": child_session.identity.session_id,
            },
        )
