"""Supervisor data contracts — Agent O decisions + Context Broker packet. Epic E10.

These are the structured artifacts that flow on the Blackboard. Agent O emits a
``SessionPlan`` (team composition) and an ``OrchestratorDecision`` per round; the
Context Broker emits a ``ContextPacket`` per worker turn. Crucially the packet
carries NO scope — a worker's ``allowed_capabilities`` is set by O's
``AgentAssignment`` and applied via ``DelegationPolicy`` (see S10.14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.schemas import DelegationSpec
from discipline import JsonGateError, parse_json_object

VALID_DECISIONS = frozenset({"continue", "need_tool", "finished", "blocked", "failed"})


# ── team composition (S10.1) ────────────────────────────────────────────────
@dataclass(frozen=True)
class AgentSelection:
    agent_id: str
    reason: str


@dataclass(frozen=True)
class SessionPlan:
    selected: tuple[AgentSelection, ...]

    def agent_ids(self) -> tuple[str, ...]:
        return tuple(s.agent_id for s in self.selected)

    def as_dict(self) -> dict[str, Any]:
        return {"selected_agents": [{"agent_id": s.agent_id, "reason": s.reason} for s in self.selected]}


# ── orchestrator decision (S10.6/S10.8) ─────────────────────────────────────
@dataclass(frozen=True)
class AgentAssignment:
    agent_id: str
    objective: str
    scope_of_work: str = ""
    allowed_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrchestratorDecision:
    decision: str
    next_agent_calls: tuple[AgentAssignment, ...] = ()
    tool_requests: tuple[dict[str, Any], ...] = ()
    acceptance_status: tuple[dict[str, Any], ...] = ()
    progress_made: bool = False
    reason: str = ""
    final_output: dict[str, Any] | None = None


# ── context packet (S10.3/S10.4/S10.14) ─────────────────────────────────────
@dataclass(frozen=True)
class ContextPacket:
    target_agent_id: str
    objective: str
    briefing: str                       # the Broker writes this
    source_ids: tuple[str, ...]         # provenance into the store slice
    expected_output_schema: dict[str, Any] = field(default_factory=dict)

    def to_spec(self) -> DelegationSpec:
        """Map the packet onto a DelegationSpec. Scope is NOT here — O/policy owns it."""
        return DelegationSpec(
            objective=self.objective,
            input_context={"briefing": self.briefing, "source_ids": list(self.source_ids)},
            expected_output_schema=dict(self.expected_output_schema),
        )


# ── parsers (reuse the E02 json-gate) ───────────────────────────────────────
def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(str(v) for v in value)


def parse_session_plan(raw: str) -> SessionPlan:
    obj = parse_json_object(raw)
    rows = obj.get("selected_agents")
    if not isinstance(rows, list) or not rows:
        raise JsonGateError("SessionPlan must list at least one selected agent.", stage="schema")
    selected = tuple(
        AgentSelection(agent_id=str(r.get("agent_id", "")), reason=str(r.get("reason", "")))
        for r in rows
        if isinstance(r, dict) and r.get("agent_id")
    )
    if not selected:
        raise JsonGateError("SessionPlan has no valid agent_id entries.", stage="schema")
    return SessionPlan(selected=selected)


def parse_decision(raw: str) -> OrchestratorDecision:
    obj = parse_json_object(raw)
    decision = str(obj.get("decision", ""))
    if decision not in VALID_DECISIONS:
        raise JsonGateError(
            f"Decision must be one of {sorted(VALID_DECISIONS)}, got {decision!r}.", stage="schema"
        )
    calls = tuple(
        AgentAssignment(
            agent_id=str(c.get("agent_id", "")),
            objective=str(c.get("objective", "")),
            scope_of_work=str(c.get("scope_of_work", "")),
            allowed_capabilities=_as_str_tuple(c.get("allowed_capabilities")),
        )
        for c in (obj.get("next_agent_calls") or [])
        if isinstance(c, dict) and c.get("agent_id")
    )
    return OrchestratorDecision(
        decision=decision,
        next_agent_calls=calls,
        tool_requests=tuple(t for t in (obj.get("tool_requests") or []) if isinstance(t, dict)),
        acceptance_status=tuple(a for a in (obj.get("acceptance_status") or []) if isinstance(a, dict)),
        progress_made=bool(obj.get("progress_made", False)),
        reason=str(obj.get("reason", "")),
        final_output=obj.get("final_output") if isinstance(obj.get("final_output"), dict) else None,
    )
