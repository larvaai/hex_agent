"""Sequential delegation chokepoint: policy, child session, progress, events, result."""
from __future__ import annotations

import uuid

from core.ports import DelegationStorePort
from core.schemas import (
    DelegationPolicy,
    DelegationProgress,
    DelegationRequest,
    DelegationResult,
    DelegationSpec,
)
from core.session import KernelSession, SessionFactory
from delegation.policy import DelegationPolicyEngine
from delegation.registry import DelegationRegistry


class DelegationManager:
    def __init__(
        self,
        *,
        registry: DelegationRegistry,
        sessions: SessionFactory,
        store: DelegationStorePort,
        policy: DelegationPolicyEngine | None = None,
    ) -> None:
        self.registry = registry
        self.sessions = sessions
        self.store = store
        self.policy = policy or DelegationPolicyEngine()
        self.registry.freeze()

    def available_targets(self) -> tuple[str, ...]:
        return self.registry.targets()

    @staticmethod
    def _event_fields(parent: KernelSession, delegation_id: str, target: str) -> dict:
        return {
            **parent.call_context().event_fields(),
            "delegation_id": delegation_id,
            "target": target,
        }

    def _finish(
        self,
        parent: KernelSession,
        target: str,
        result: DelegationResult,
    ) -> DelegationResult:
        self.store.finish(result)
        parent.kernel.events.publish(
            "delegation.finished",
            {
                **self._event_fields(parent, result.delegation_id, target),
                "outcome": result.outcome,
                "artifact_count": len(result.artifacts),
                "error": result.error,
            },
        )
        return result

    def delegate(
        self,
        parent_session: KernelSession,
        target: str,
        spec: DelegationSpec,
        policy: DelegationPolicy | None = None,
    ) -> DelegationResult:
        if not parent_session.is_active:
            raise RuntimeError("Cannot delegate from an inactive parent session.")
        if not target:
            raise ValueError("Delegation target must not be empty.")
        if not spec.objective:
            raise ValueError("Delegation objective must not be empty.")

        delegation_id = uuid.uuid4().hex
        requested_policy = policy or DelegationPolicy()
        try:
            active_policy = self.policy.validate(parent_session, requested_policy)
        except Exception as exc:
            request = DelegationRequest(
                delegation_id=delegation_id,
                parent_session_id=parent_session.identity.session_id,
                parent_task_id=parent_session.identity.task_id,
                target=target,
                spec=spec,
                policy=requested_policy,
            )
            self.store.start(request)
            parent_session.kernel.events.publish(
                "delegation.started",
                self._event_fields(parent_session, delegation_id, target),
            )
            return self._finish(
                parent_session,
                target,
                DelegationResult(
                    delegation_id=delegation_id,
                    parent_task_id=parent_session.identity.task_id,
                    outcome="rejected",
                    error=str(exc),
                ),
            )
        request = DelegationRequest(
            delegation_id=delegation_id,
            parent_session_id=parent_session.identity.session_id,
            parent_task_id=parent_session.identity.task_id,
            target=target,
            spec=spec,
            policy=active_policy,
        )
        self.store.start(request)
        parent_session.kernel.events.publish(
            "delegation.started",
            self._event_fields(parent_session, delegation_id, target),
        )

        try:
            handler = self.registry.resolve(target)
            child = self.sessions.create_child(
                parent_session,
                delegation_id=delegation_id,
                target=target,
                user_request=spec.objective,
                context=spec.input_context,
                requested_scope=active_policy.allowed_capabilities,
            )
            child.state.set("delegation_policy", active_policy.as_dict())
        except Exception as exc:
            return self._finish(
                parent_session,
                target,
                DelegationResult(
                    delegation_id=delegation_id,
                    parent_task_id=parent_session.identity.task_id,
                    outcome="rejected" if isinstance(exc, PermissionError) else "failed",
                    error=str(exc),
                ),
            )

        def progress_sink(progress: DelegationProgress) -> None:
            if progress.delegation_id != delegation_id:
                raise ValueError("Progress delegation_id does not match the active request.")
            if progress.sequence > active_policy.max_steps:
                raise ValueError("Delegation progress exceeded max_steps.")
            self.store.append_progress(progress)  # source of truth first
            child.kernel.events.publish(
                "delegation.progress",
                {
                    **child.call_context().event_fields(),
                    "event_id": progress.event_id,
                    "sequence": progress.sequence,
                    "status": progress.status,
                    "artifact": progress.artifact.as_dict(),
                },
            )

        try:
            result = handler.run(request, child, progress_sink)
            if result.delegation_id != delegation_id:
                raise ValueError("Delegation result ID does not match the request.")
            if result.parent_task_id != parent_session.identity.task_id:
                raise ValueError("Delegation result parent_task_id does not match the parent.")
            progress_artifacts = tuple(item.artifact for item in self.store.progress(delegation_id))
            seen = {artifact.artifact_id for artifact in progress_artifacts}
            artifacts = progress_artifacts + tuple(
                artifact for artifact in result.artifacts if artifact.artifact_id not in seen
            )
            result = DelegationResult(
                delegation_id=result.delegation_id,
                parent_task_id=result.parent_task_id,
                outcome=result.outcome,
                artifacts=artifacts,
                summary=result.summary,
                error=result.error,
            )
        except Exception as exc:
            result = DelegationResult(
                delegation_id=delegation_id,
                parent_task_id=parent_session.identity.task_id,
                outcome="failed",
                artifacts=tuple(item.artifact for item in self.store.progress(delegation_id)),
                error=str(exc),
            )

        if child.is_active:
            if result.outcome == "success":
                child.complete_task(result.as_dict())
            else:
                child.fail_task(result.error or result.outcome)
        return self._finish(parent_session, target, result)
