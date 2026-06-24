"""Context Broker — writes a just-enough briefing per worker turn. Epic E10.

The Broker reads the next agent's objective + scope of work and a *store slice*
it is handed, then writes a ContextPacket grounded in that slice with provenance
(`source_ids`). Hard invariant (S10.14): the Broker shapes informational context
only — it can never set or widen a worker's capability scope. In S1 a
``DeterministicBroker`` exercises these invariants offline; S2 swaps in an
``llm.chat``-backed Broker (S10.4).
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from supervisor.contracts import AgentAssignment, ContextPacket


@runtime_checkable
class BrokerPort(Protocol):
    def write_packet(
        self, *, assignment: AgentAssignment, store_slice: list[dict[str, Any]]
    ) -> ContextPacket: ...


class DeterministicBroker:
    """Offline Broker: briefing built only from the given slice, with provenance.

    Guardrails honoured: grounded (only slice text), provenance (source_ids from
    slice), size-capped (char budget). It emits no scope field at all.
    """

    def __init__(self, *, char_budget: int = 1200) -> None:
        self.char_budget = char_budget

    def write_packet(
        self, *, assignment: AgentAssignment, store_slice: list[dict[str, Any]]
    ) -> ContextPacket:
        lines: list[str] = [f"Objective: {assignment.objective}"]
        if assignment.scope_of_work:
            lines.append(f"Scope of work: {assignment.scope_of_work}")
        source_ids: list[str] = []
        for item in store_slice:
            item_id = str(item.get("id") or "")
            text = str(item.get("text") or "")
            if not item_id:
                continue
            source_ids.append(item_id)
            lines.append(f"[{item_id}] {text}")
        briefing = "\n".join(lines)[: self.char_budget]
        return ContextPacket(
            target_agent_id=assignment.agent_id,
            objective=assignment.objective,
            briefing=briefing,
            source_ids=tuple(source_ids),
            expected_output_schema={},
        )
