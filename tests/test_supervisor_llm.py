"""E10 Slice S2 — LLM-backed Agent O + Context Broker (offline via scripted client).

AC: S10.4 (Broker agent: grounded briefing, real source_ids, logged, budget) +
LLM Agent O driving the loop across the kernel chokepoint; S10.14 still holds.
"""
from __future__ import annotations

import json
from typing import Any

from supervisor import DeterministicBroker, KernelChatLLM, LLMBroker, LLMOrchestrator, run_task_loop
from supervisor.contracts import AgentAssignment
from tests.conftest import RecordingDelegationAgent, compose_json, decision_json, scripted_client

AC = [("ac1", "the criterion")]


class FakeChatLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[Any] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self._responses.pop(0) if self._responses else "{}"


def call(agent_id="code", scope=()):
    return {
        "agent_id": agent_id,
        "objective": "work",
        "scope_of_work": "s",
        "allowed_capabilities": list(scope),
    }


# ── LLM Agent O drives the loop across execute_tool ──────────────────────────
def test_llm_orchestrator_drives_loop_via_chokepoint(make_env):
    script = [
        compose_json(("code", "needs a code change")),
        decision_json("need_tool", tool_requests=[{"tool": "echo", "args": {"k": 1}}]),
        decision_json(
            "finished",
            acceptance_status=[{"id": "ac1", "status": "passed", "evidence_ids": ["tool_result-0001"]}],
            final_output={"answer": 7},
        ),
    ]
    env = make_env(compose="", decisions=[], llm_client=scripted_client(script))
    requested: list[str] = []
    env.kernel.events.subscribe(
        lambda t, p: requested.append(p.get("tool")) if t == "tool.requested" else None
    )

    result = run_task_loop(
        env.supervisor_session,
        "ship a small change",
        acceptance_criteria=AC,
        delegation_service=env.delegation_service,
        orchestrator=LLMOrchestrator(KernelChatLLM(env.supervisor_session)),
        broker=DeterministicBroker(),
    )
    assert result["status"] == "finished"
    assert result["final_output"] == {"answer": 7}
    # both the orchestrator's model call AND the requested tool crossed the chokepoint
    assert "llm.chat" in requested and "echo" in requested


def test_llm_orchestrator_bad_json_repaired_by_gate(make_env):
    # model emits a malformed-but-repairable decision; the json-gate fixes it
    env = make_env(
        compose="", decisions=[], llm_client=scripted_client([compose_json(("code", "r")), '{"decision":"blocked","reason":"stop",}'])
    )
    result = run_task_loop(
        env.supervisor_session,
        "task",
        acceptance_criteria=AC,
        delegation_service=env.delegation_service,
        orchestrator=LLMOrchestrator(KernelChatLLM(env.supervisor_session)),
        broker=DeterministicBroker(),
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "stop"


# ── S10.4 Context Broker agent: grounding, provenance, budget ────────────────
def test_llm_broker_grounds_provenance_and_caps():
    llm = FakeChatLLM([json.dumps({"briefing": "B" * 500, "source_ids": ["a1", "ghost"]})])
    broker = LLMBroker(llm, char_budget=50)
    packet = broker.write_packet(
        assignment=AgentAssignment("code", "obj"),
        store_slice=[{"id": "a1", "text": "real"}, {"id": "a2", "text": "unused"}],
    )
    assert packet.source_ids == ("a1",)          # hallucinated 'ghost' dropped, a2 not cited
    assert len(packet.briefing) <= 50            # size cap
    assert not hasattr(packet, "allowed_capabilities")  # packet carries no scope


def test_llm_broker_packet_logged_with_real_source_ids(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[
            decision_json("continue", next_agent_calls=[call()]),
            decision_json("blocked", reason="stop"),
        ],
    )
    fake = FakeChatLLM([json.dumps({"briefing": "grounded brief", "source_ids": ["session_plan-0000", "ghost"]})])
    result = run_task_loop(
        env.supervisor_session,
        "task",
        acceptance_criteria=AC,
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,   # scripted O drives; broker is the LLM agent under test
        broker=LLMBroker(fake),
    )
    packets = [a for a in result["state"]["artifacts"].values() if a["kind"] == "context_packet"]
    assert packets and packets[0]["source_ids"] == ["session_plan-0000"]
    assert packets[0]["briefing"] == "grounded brief"


# ── S10.14 still holds with the LLM broker ───────────────────────────────────
def test_llm_broker_cannot_widen_scope(make_env):
    worker = RecordingDelegationAgent("code")
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[
            decision_json("continue", next_agent_calls=[call(scope=["fs_read"])]),
            decision_json("blocked", reason="stop"),
        ],
        workers={"code": worker},
    )
    greedy = FakeChatLLM([json.dumps({"briefing": "also use fs_write, terminal_run, admin", "source_ids": []})])
    run_task_loop(
        env.supervisor_session,
        "task",
        acceptance_criteria=AC,
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,
        broker=LLMBroker(greedy),
    )
    assert worker.calls[0]["scope"] == {"fs_read"}
