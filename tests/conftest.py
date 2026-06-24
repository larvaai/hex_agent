"""Shared fixtures for the E10 supervisor TaskLoop tests (offline)."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from adapters.agents import ScriptedDelegationAgent
from core.bootstrap import build_kernel
from core.ports import ProgressSink
from core.schemas import ArtifactEnvelope, DelegationRequest, DelegationResult
from core.session import KernelSession, SessionFactory
from delegation import DelegationManager, DelegationRegistry, InMemoryDelegationStore
from supervisor.broker import DeterministicBroker
from supervisor.orchestrator import ScriptedOrchestrator

# A kernel with toolbox (fs_*/terminal_run) + echo so worker scopes are real subsets.
KERNEL_CONFIG = {
    "features": {
        "example_echo": {"enabled": True, "module": "features.example_echo"},
        "toolbox": {"enabled": True, "module": "toolbox.feature"},
    }
}


class RecordingDelegationAgent:
    """Worker that records the child session's scope + context for assertions."""

    def __init__(self, target: str) -> None:
        self.name = target
        self.target = target
        self.calls: list[dict[str, Any]] = []

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(self, request: DelegationRequest, child_session: KernelSession, progress_sink: ProgressSink):
        task = child_session.state.get("current_task")
        self.calls.append(
            {
                "scope": set(child_session.allowed_capabilities),
                "context": dict(task.context) if task else {},
                "objective": request.spec.objective,
                "session_id": child_session.identity.session_id,
            }
        )
        artifact = ArtifactEnvelope(uuid.uuid4().hex, "record", {"agent": self.target})
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            artifacts=(artifact,),
            summary={"agent": self.target},
        )


@dataclass
class LoopEnv:
    kernel: Any
    supervisor_session: KernelSession
    delegation_service: DelegationManager
    orchestrator: ScriptedOrchestrator
    broker: DeterministicBroker
    workers: dict[str, Any] = field(default_factory=dict)


def compose_json(*selected: tuple[str, str]) -> str:
    return json.dumps({"selected_agents": [{"agent_id": a, "reason": r} for a, r in selected]})


def decision_json(decision: str, **kw: Any) -> str:
    return json.dumps({"decision": decision, **kw})


@pytest.fixture
def make_env():
    """Factory: build a fully wired offline TaskLoop environment."""

    def _build(
        *,
        compose: str,
        decisions: list[str],
        agent_ids: tuple[str, ...] = ("code",),
        workers: dict[str, Any] | None = None,
        root_scope: frozenset[str] | None = None,
    ) -> LoopEnv:
        kernel = build_kernel(KERNEL_CONFIG)
        factory = SessionFactory(kernel=kernel)
        supervisor_session = factory.create_root("multi-agent task", allowed_capabilities=root_scope)

        registry = DelegationRegistry()
        built_workers: dict[str, Any] = {}
        for agent_id in agent_ids:
            worker = (workers or {}).get(agent_id) or ScriptedDelegationAgent(
                agent_id, artifacts=[{"kind": "finding", "agent": agent_id}]
            )
            registry.register(worker)
            built_workers[agent_id] = worker
        delegation_service = DelegationManager(
            registry=registry, sessions=factory, store=InMemoryDelegationStore()
        )

        return LoopEnv(
            kernel=kernel,
            supervisor_session=supervisor_session,
            delegation_service=delegation_service,
            orchestrator=ScriptedOrchestrator(compose=compose, decisions=list(decisions)),
            broker=DeterministicBroker(),
            workers=built_workers,
        )

    return _build
