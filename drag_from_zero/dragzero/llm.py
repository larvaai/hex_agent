"""The LLM seam.

Slice 1 ships only a deterministic FakeLLM so harness invariants are testable.
Slice 2 plugs a real local LLM (llama.cpp / LM Studio) in behind `.complete()`
without touching the orchestrator.
"""
from __future__ import annotations

from typing import Callable, Optional, Protocol


class LLM(Protocol):
    def complete(self, ctx: dict) -> dict:
        """ctx = {agent_id, role, task, depth} -> {"plan": {...}, "decision": {...}}."""
        ...


class FakeLLM:
    """Deterministic, scripted. `responder(ctx)` returns the plan+decision dict."""

    def __init__(self, responder: Callable[[dict], dict]) -> None:
        self._responder = responder
        self.calls: list[dict] = []

    def complete(self, ctx: dict) -> dict:
        self.calls.append(ctx)
        return self._responder(ctx)


def by_role(table: dict, default: Optional[dict] = None) -> Callable[[dict], dict]:
    """Build a responder that dispatches on ctx['role']. Values may be dicts or callables."""

    def responder(ctx: dict) -> dict:
        resp = table.get(ctx["role"], default)
        if resp is None:
            raise KeyError(f"FakeLLM: no scripted response for role {ctx['role']!r}")
        return resp(ctx) if callable(resp) else resp

    return responder
