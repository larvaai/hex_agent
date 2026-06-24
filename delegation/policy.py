"""Delegation depth, budget, and capability-scope enforcement."""
from __future__ import annotations

from core.schemas import DelegationPolicy
from core.session import KernelSession


class DelegationPolicyEngine:
    def __init__(self, *, max_steps: int = 100, max_depth: int = 8) -> None:
        self.max_steps = max_steps
        self.max_depth = max_depth

    def validate(
        self,
        parent: KernelSession,
        requested: DelegationPolicy | None,
    ) -> DelegationPolicy:
        policy = requested or DelegationPolicy()
        if policy.max_steps < 1 or policy.max_steps > self.max_steps:
            raise ValueError(f"Delegation max_steps must be between 1 and {self.max_steps}.")
        if policy.max_depth < 1 or policy.max_depth > self.max_depth:
            raise ValueError(f"Delegation max_depth must be between 1 and {self.max_depth}.")
        if parent.identity.depth + 1 > policy.max_depth:
            raise PermissionError("Delegation depth limit exceeded.")
        scope = policy.allowed_capabilities or parent.allowed_capabilities
        if not scope <= parent.allowed_capabilities:
            raise PermissionError("Delegation capability scope exceeds the parent scope.")
        return DelegationPolicy(
            max_steps=policy.max_steps,
            max_depth=policy.max_depth,
            allowed_capabilities=frozenset(scope),
        )
