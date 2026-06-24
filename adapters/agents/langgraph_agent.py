"""Concrete DelegationPort implemented by the existing session-bound LangGraph."""
from __future__ import annotations

import uuid

from langgraph.checkpoint.memory import InMemorySaver

from core.ports import ProgressSink
from core.schemas import (
    ArtifactEnvelope,
    DelegationProgress,
    DelegationRequest,
    DelegationResult,
)
from core.session import KernelSession
from discipline import Budget
from graph.runtime import COMPAT_SYSTEM_PROMPT, build_agent_graph
from graph.state import AgentState, budget_from_state, new_agent_state


class LangGraphDelegationAgent:
    """Sequential local child agent; persistence/recursive delegation are intentionally disabled in v1."""

    def __init__(self, target: str = "agent:general") -> None:
        self.name = target
        self.target = target

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(
        self,
        request: DelegationRequest,
        child_session: KernelSession,
        progress_sink: ProgressSink,
    ) -> DelegationResult:
        initial = new_agent_state(
            session=child_session,
            messages=[
                {"role": "system", "content": COMPAT_SYSTEM_PROMPT},
                {"role": "user", "content": request.spec.objective},
            ],
            budget=Budget(max_steps=request.policy.max_steps),
        )
        graph = build_agent_graph(
            session=child_session,
            checkpointer=InMemorySaver(),
            delegation_service=None,
        )
        config = {
            "configurable": {"thread_id": child_session.identity.session_id},
            "recursion_limit": max(100, request.policy.max_steps * 4 + 20),
        }
        final_state: AgentState = initial
        emitted_step = 0
        artifacts: list[ArtifactEnvelope] = []
        for values in graph.stream(initial, config, stream_mode="values"):
            final_state = values
            step = budget_from_state(values).steps
            if step <= emitted_step:
                continue
            emitted_step = step
            artifact = ArtifactEnvelope(
                artifact_id=uuid.uuid4().hex,
                kind="agent_step",
                payload={
                    "step": step,
                    "action": dict(values.get("last_action") or {}),
                    "status": values.get("status", "running"),
                },
            )
            artifacts.append(artifact)
            progress_sink(
                DelegationProgress(
                    delegation_id=request.delegation_id,
                    sequence=len(artifacts),
                    event_id=uuid.uuid4().hex,
                    artifact=artifact,
                )
            )

        status = str(final_state.get("status") or "failed")
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success" if status == "completed" else "failed",
            artifacts=tuple(artifacts),
            summary={
                "target": request.target,
                "child_session_id": child_session.identity.session_id,
                "steps": budget_from_state(final_state).steps,
                "final": final_state.get("final"),
            },
            error=final_state.get("error") if status != "completed" else None,
        )
