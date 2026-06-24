"""Agent O — the orchestrator/judge. Epic E10.

O composes the team and emits one structured decision per round. It NEVER calls a
tool directly (a ``need_tool`` decision is executed by the supervisor through
``execute_tool``). In S1 a ``ScriptedOrchestrator`` returns canned JSON so the loop
plumbing is tested offline; S2 swaps in an ``llm.chat``-backed orchestrator that
emits the same JSON parsed by the same json-gate.
"""
from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OrchestratorPort(Protocol):
    def compose_team(self, *, task: str, available_roles: tuple[dict[str, Any], ...]) -> str: ...
    def decide(self, *, state_view: dict[str, Any]) -> str: ...


class ScriptedOrchestrator:
    """Deterministic O for offline tests: canned compose + a queue of decisions."""

    def __init__(self, *, compose: str, decisions: list[str]) -> None:
        self._compose = compose
        self._decisions = list(decisions)
        self.compose_calls = 0
        self.decide_calls = 0

    def compose_team(self, *, task: str, available_roles: tuple[dict[str, Any], ...]) -> str:
        self.compose_calls += 1
        return self._compose

    def decide(self, *, state_view: dict[str, Any]) -> str:
        self.decide_calls += 1
        if self._decisions:
            return self._decisions.pop(0)
        # Ran out of script: terminate rather than loop forever.
        return json.dumps({"decision": "blocked", "reason": "orchestrator script exhausted"})
