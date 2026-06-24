"""LLM-backed Agent O + Context Broker (E10 Slice S2).

These are the live versions of the supervisor's two model agents. Both reach the
model through ``llm.chat`` — i.e. across ``AgentKernel.execute_tool`` — so their
calls are observed and disciplined like any other capability. Output is parsed by
the same json-gate that S1 used, so a malformed decision is repaired/re-prompted
identically.

Guardrails kept in CODE, never trusted to the model:
- Broker provenance: ``source_ids`` are intersected with the real slice ids
  (hallucinated ids are dropped).
- Broker size cap: the briefing is truncated to ``char_budget``.
- Broker scope: a ContextPacket has no scope field at all, so the Broker can
  never set or widen a worker's capability scope (S10.14).
"""
from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from core.session import KernelSession
from discipline import JsonGateError, parse_json_object
from supervisor.contracts import AgentAssignment, ContextPacket

COMPOSE_SYSTEM = (
    "You are Agent O, an orchestrator. Choose the MINIMUM set of agents needed for "
    "the task and give a one-line reason for each. Reply with EXACTLY ONE JSON object:\n"
    '{"selected_agents":[{"agent_id":"<id>","reason":"<why>"}]}'
)

DECIDE_SYSTEM = (
    "You are Agent O. Read the blackboard state and emit EXACTLY ONE JSON decision:\n"
    '{"decision":"continue|need_tool|finished|blocked|failed",'
    '"next_agent_calls":[{"agent_id":"..","objective":"..","scope_of_work":"..",'
    '"allowed_capabilities":[".."]}],'
    '"tool_requests":[{"tool":"..","args":{}}],'
    '"acceptance_status":[{"id":"..","status":"passed|failed|pending","evidence_ids":[".."]}],'
    '"final_output":{},"reason":".."}\n'
    "Mark a criterion 'passed' ONLY with real evidence_ids already on the blackboard. "
    "Reach 'finished' only when every criterion is passed with evidence; otherwise continue, "
    "request a tool, block, or fail. You never call a tool yourself — emit a need_tool decision."
)

BROKER_SYSTEM = (
    "You are the Context Broker. Write a just-enough briefing for the next agent using ONLY "
    "the provided context items — do not invent facts. Cite the ids of the items you used. "
    "Do NOT request tools or permissions. Reply with EXACTLY ONE JSON object:\n"
    '{"briefing":"<text>","source_ids":["<item id>"]}'
)


@runtime_checkable
class ChatLLM(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


class KernelChatLLM:
    """A ChatLLM that reaches the model via the kernel chokepoint (`llm.chat`)."""

    def __init__(self, session: KernelSession, *, model: str | None = None) -> None:
        self._session = session
        self._model = model

    def complete(self, messages: list[dict[str, str]]) -> str:
        response = self._session.execute_tool(
            "llm.chat", {"messages": messages, "model": self._model, "json_mode": True}
        )
        return str((response.get("data") or {}).get("content", ""))


class LLMOrchestrator:
    """Agent O backed by an LLM. Emits raw JSON parsed by the supervisor's json-gate."""

    def __init__(self, llm: ChatLLM) -> None:
        self._llm = llm

    def compose_team(self, *, task: str, available_roles: tuple[dict[str, Any], ...]) -> str:
        return self._llm.complete(
            [
                {"role": "system", "content": COMPOSE_SYSTEM},
                {"role": "user", "content": json.dumps({"task": task, "available_agents": list(available_roles)})},
            ]
        )

    def decide(self, *, state_view: dict[str, Any]) -> str:
        return self._llm.complete(
            [
                {"role": "system", "content": DECIDE_SYSTEM},
                {"role": "user", "content": json.dumps(state_view)},
            ]
        )


class LLMBroker:
    """Context Broker backed by an LLM, with code-enforced grounding/budget/scope."""

    def __init__(self, llm: ChatLLM, *, char_budget: int = 1200) -> None:
        self._llm = llm
        self.char_budget = char_budget

    def write_packet(
        self, *, assignment: AgentAssignment, store_slice: list[dict[str, Any]]
    ) -> ContextPacket:
        slice_ids = {str(item.get("id")) for item in store_slice if item.get("id")}
        raw = self._llm.complete(
            [
                {"role": "system", "content": BROKER_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "objective": assignment.objective,
                            "scope_of_work": assignment.scope_of_work,
                            "context_items": store_slice,
                        }
                    ),
                },
            ]
        )
        try:
            obj = parse_json_object(raw)
            briefing = str(obj.get("briefing", "")).strip()
            cited = [str(s) for s in (obj.get("source_ids") or [])]
        except JsonGateError:
            briefing, cited = "", []

        # Provenance guardrail: keep only ids that really exist in the slice.
        source_ids = tuple(s for s in cited if s in slice_ids)
        if not briefing:  # graceful fallback — the Broker is informational only
            briefing = f"Objective: {assignment.objective}"
        return ContextPacket(
            target_agent_id=assignment.agent_id,
            objective=assignment.objective,
            briefing=briefing[: self.char_budget],  # size cap
            source_ids=source_ids,
            expected_output_schema={},
        )
