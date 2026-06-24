"""Composition helper for the default local delegation target."""
from __future__ import annotations

from adapters.agents import LangGraphDelegationAgent
from core.kernel import AgentKernel
from core.ports import DelegationServicePort
from core.session import SessionFactory
from delegation.manager import DelegationManager
from delegation.registry import DelegationRegistry
from delegation.store import InMemoryDelegationStore


def create_delegation_service(kernel: AgentKernel) -> DelegationServicePort | None:
    config = dict(kernel.config.get("delegation") or {})
    if not config.get("enabled", False):
        return None
    target = str(config.get("default_target") or "agent:general")
    registry = DelegationRegistry()
    registry.register(LangGraphDelegationAgent(target))
    return DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=InMemoryDelegationStore(),
    )
