"""
LSP case 04 — OrchestratorPort & BrokerPort: bản Scripted vs LLM-backed thay thế nhau.

Bản DISTILL TRUNG THỰC (chỉ stdlib) của hai cặp port-adapter trong supervisor hex_agent.

NGUỒN THẬT đã mở kiểm chứng (đường dẫn tương đối so với /Users/uspro/Desktop/namnson/hex_agent):
  - supervisor/orchestrator.py:15-18   OrchestratorPort(Protocol): compose_team(...)->str, decide(...)->str (JSON)
  - supervisor/orchestrator.py:21-39   ScriptedOrchestrator — JSON canned (S1, offline tests)
  - supervisor/broker.py:17-21         BrokerPort(Protocol): write_packet(assignment, store_slice) -> ContextPacket
  - supervisor/broker.py:24-55         DeterministicBroker — briefing chỉ từ slice + provenance source_ids
  - supervisor/llm.py:52-54            ChatLLM(Protocol): complete(messages) -> str
  - supervisor/llm.py:71-91            LLMOrchestrator — gọi llm.complete, GIỮ postcondition JSON như Scripted
  - supervisor/llm.py:94-137           LLMBroker — gọi LLM nhưng GUARDRAIL trong CODE
  - supervisor/llm.py:127-128          source_ids = giao của id LLM trả với id slice thật (bỏ id hallucinated)
  - supervisor/llm.py:134              briefing cắt theo char_budget (size cap)

CONTRACT mà TaskLoop dựa vào:
  - OrchestratorPort.compose_team/decide : LUÔN trả một chuỗi JSON parse được bởi json-gate.
  - BrokerPort.write_packet              : LUÔN trả ContextPacket với:
                                             briefing (str),
                                             source_ids ⊆ id của slice thật  (INVARIANT — chống hallucination),
                                             KHÔNG có field scope (Broker không bao giờ nới quyền worker).
LSP: Scripted (S1, tất định) và LLM-backed (S2, không tất định) cùng giữ postcondition ->
     TaskLoop parse JSON / đọc packet giống nhau, KHÔNG if/elif theo loại. Bất biến source_ids ⊆ slice
     được THỰC THI BẰNG CODE trong LLMBroker, KHÔNG tin LLM.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


# ───────────────────────── value types (distill supervisor/contracts) ──────
@dataclass(frozen=True)
class AgentAssignment:
    agent_id: str
    objective: str
    scope_of_work: str = ""


@dataclass(frozen=True)
class ContextPacket:
    target_agent_id: str
    objective: str
    briefing: str
    source_ids: tuple[str, ...]
    expected_output_schema: dict[str, Any]
    # CHÚ Ý: không có field 'scope' — Broker không thể nới quyền worker (supervisor/llm.py:13-14).


# ───────────────────────── ABSTRACTION: OrchestratorPort ───────────────────
# Distill của supervisor/orchestrator.py:15-18.
@runtime_checkable
class OrchestratorPort(Protocol):
    def compose_team(self, *, task: str, available_roles: tuple[dict[str, Any], ...]) -> str: ...
    def decide(self, *, state_view: dict[str, Any]) -> str: ...


# ───────────────────────── ABSTRACTION: BrokerPort ─────────────────────────
# Distill của supervisor/broker.py:17-21.
@runtime_checkable
class BrokerPort(Protocol):
    def write_packet(self, *, assignment: AgentAssignment, store_slice: list[dict[str, Any]]) -> ContextPacket: ...


# ───────────────────────── ABSTRACTION: ChatLLM ────────────────────────────
# Distill của supervisor/llm.py:52-54.
@runtime_checkable
class ChatLLM(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


# ───────────────────────── SUBTYPE: ScriptedOrchestrator (S1) ──────────────
# Distill của supervisor/orchestrator.py:21-39.
class ScriptedOrchestrator:
    def __init__(self, *, compose: str, decisions: list[str]) -> None:
        self._compose = compose
        self._decisions = list(decisions)

    def compose_team(self, *, task: str, available_roles: tuple[dict[str, Any], ...]) -> str:
        return self._compose  # JSON canned

    def decide(self, *, state_view: dict[str, Any]) -> str:
        if self._decisions:
            return self._decisions.pop(0)
        return json.dumps({"decision": "blocked", "reason": "orchestrator script exhausted"})


# ───────────────────────── SUBTYPE: LLMOrchestrator (S2) ───────────────────
# Distill của supervisor/llm.py:71-91 — cùng postcondition (trả JSON string) như Scripted.
class LLMOrchestrator:
    def __init__(self, llm: ChatLLM) -> None:
        self._llm = llm

    def compose_team(self, *, task: str, available_roles: tuple[dict[str, Any], ...]) -> str:
        return self._llm.complete([
            {"role": "system", "content": "compose"},
            {"role": "user", "content": json.dumps({"task": task})},
        ])

    def decide(self, *, state_view: dict[str, Any]) -> str:
        return self._llm.complete([
            {"role": "system", "content": "decide"},
            {"role": "user", "content": json.dumps(state_view)},
        ])


# ───────────────────────── SUBTYPE: DeterministicBroker (S1) ───────────────
# Distill của supervisor/broker.py:24-55.
class DeterministicBroker:
    def __init__(self, *, char_budget: int = 1200) -> None:
        self.char_budget = char_budget

    def write_packet(self, *, assignment: AgentAssignment, store_slice: list[dict[str, Any]]) -> ContextPacket:
        lines = [f"Objective: {assignment.objective}"]
        source_ids: list[str] = []
        for item in store_slice:
            item_id = str(item.get("id") or "")
            if not item_id:
                continue
            source_ids.append(item_id)
            lines.append(f"[{item_id}] {item.get('text', '')}")
        briefing = "\n".join(lines)[: self.char_budget]
        return ContextPacket(assignment.agent_id, assignment.objective, briefing, tuple(source_ids), {})


# ───────────────────────── SUBTYPE: LLMBroker (S2) ─────────────────────────
# Distill của supervisor/llm.py:94-137. GUARDRAIL bằng CODE, KHÔNG tin LLM.
class LLMBroker:
    def __init__(self, llm: ChatLLM, *, char_budget: int = 1200) -> None:
        self._llm = llm
        self.char_budget = char_budget

    def write_packet(self, *, assignment: AgentAssignment, store_slice: list[dict[str, Any]]) -> ContextPacket:
        slice_ids = {str(item.get("id")) for item in store_slice if item.get("id")}
        raw = self._llm.complete([
            {"role": "system", "content": "broker"},
            {"role": "user", "content": json.dumps({"objective": assignment.objective,
                                                     "context_items": store_slice})},
        ])
        try:
            obj = json.loads(raw)
            briefing = str(obj.get("briefing", "")).strip()
            cited = [str(s) for s in (obj.get("source_ids") or [])]
        except (json.JSONDecodeError, AttributeError):
            briefing, cited = "", []
        # supervisor/llm.py:127-128 — INVARIANT: chỉ giữ id thật có trong slice (bỏ id hallucinated).
        source_ids = tuple(s for s in cited if s in slice_ids)
        if not briefing:  # fallback nhẹ nhàng (llm.py:129-130)
            briefing = f"Objective: {assignment.objective}"
        return ContextPacket(assignment.agent_id, assignment.objective,
                             briefing[: self.char_budget], source_ids, {})  # size cap (llm.py:134)


# ───────────────────────── fake LLM (stdlib) ───────────────────────────────
class FakeLLM:
    """Đứng thay KernelChatLLM. Trả JSON định sẵn theo system message; có thể HALLUCINATE id."""

    def __init__(self, *, compose: str, decision: str, broker_reply: str) -> None:
        self._compose = compose
        self._decision = decision
        self._broker = broker_reply

    def complete(self, messages: list[dict[str, str]]) -> str:
        system = messages[0]["content"]
        return {"compose": self._compose, "decide": self._decision, "broker": self._broker}[system]


# ───────────────────────── CALLER (depend on abstractions) ─────────────────
def json_gate(raw: str) -> dict:
    """Distill của discipline.parse_json_object — parse JSON bất kể nguồn Scripted hay LLM."""
    return json.loads(raw)


class TaskLoop:
    """Supervisor: gọi orchestrator + broker qua abstraction, KHÔNG isinstance."""

    def __init__(self, orchestrator: OrchestratorPort, broker: BrokerPort) -> None:
        self._orch = orchestrator
        self._broker = broker

    def step(self, *, task: str, state_view: dict, assignment: AgentAssignment,
             store_slice: list[dict]) -> dict:
        compose = json_gate(self._orch.compose_team(task=task, available_roles=()))
        decision = json_gate(self._orch.decide(state_view=state_view))
        packet = self._broker.write_packet(assignment=assignment, store_slice=store_slice)
        # INVARIANT do caller dựa vào — đúng với MỌI broker impl:
        assert not hasattr(packet, "scope"), "ContextPacket không bao giờ có field scope"
        real_ids = {str(i.get("id")) for i in store_slice if i.get("id")}
        assert set(packet.source_ids) <= real_ids, "source_ids phải ⊆ id slice thật"
        return {"selected": compose.get("selected_agents", []),
                "decision": decision.get("decision"),
                "source_ids": list(packet.source_ids)}


def demo() -> None:
    print("=" * 72)
    print("LSP case 04 — OrchestratorPort & BrokerPort: Scripted vs LLM swap")
    print("=" * 72)

    slice_real = [{"id": "doc1", "text": "alpha"}, {"id": "doc2", "text": "beta"}]
    assignment = AgentAssignment("agent:code", "viết hàm cộng", "module math")

    # S1 — Scripted (tất định, offline).
    scripted_orch = ScriptedOrchestrator(
        compose=json.dumps({"selected_agents": ["code"]}),
        decisions=[json.dumps({"decision": "continue"})],
    )
    det_broker = DeterministicBroker()

    # S2 — LLM-backed. LLM cố ý HALLUCINATE id 'ghost' không có trong slice.
    fake_llm = FakeLLM(
        compose=json.dumps({"selected_agents": ["code"]}),
        decision=json.dumps({"decision": "continue"}),
        broker_reply=json.dumps({"briefing": "tóm tắt alpha/beta", "source_ids": ["doc1", "ghost"]}),
    )
    llm_orch = LLMOrchestrator(fake_llm)
    llm_broker = LLMBroker(fake_llm)

    print("\n[1] TaskLoop phụ thuộc abstraction — plumbing GIỐNG HỆT khi swap S1 <-> S2:")
    for label, orch, broker in (("S1 Scripted/Determ", scripted_orch, det_broker),
                                ("S2 LLM/LLM-backed", llm_orch, llm_broker)):
        loop = TaskLoop(orch, broker)
        res = loop.step(task="t", state_view={}, assignment=assignment, store_slice=slice_real)
        print(f"    - {label:20s}: selected={res['selected']}, decision={res['decision']!r}, "
              f"source_ids={res['source_ids']}")
        assert res["decision"] == "continue"

    print("\n[2] INVARIANT chống hallucination (supervisor/llm.py:127-128) — thực thi bằng CODE:")
    packet = llm_broker.write_packet(assignment=assignment, store_slice=slice_real)
    print(f"    - LLM trả source_ids=['doc1','ghost'] (ghost là id bịa).")
    print(f"    - LLMBroker giao với slice thật -> packet.source_ids={list(packet.source_ids)} ('ghost' bị loại).")
    assert "ghost" not in packet.source_ids, "id hallucinated phải bị loại"
    assert set(packet.source_ids) <= {"doc1", "doc2"}

    print("\n[3] CONTRACT về quyền: ContextPacket KHÔNG có field scope -> Broker không nới quyền worker:")
    assert not hasattr(packet, "scope")
    print("    - hasattr(packet, 'scope') =", hasattr(packet, "scope"), "(cả hai broker đều giữ bất biến này)")

    print("\n[4] ĐỐI CHỨNG — broker VI PHẠM invariant (để lọt id hallucinated, không lọc):")

    class NaiveBroker:
        """Tin LLM tuyệt đối: nhét thẳng source_ids LLM trả vào packet (không lọc)."""

        def write_packet(self, *, assignment: AgentAssignment, store_slice):
            return ContextPacket(assignment.agent_id, assignment.objective,
                                 "brief", ("doc1", "ghost"), {})  # 'ghost' không có trong slice!

    loop = TaskLoop(scripted_orch_clone := ScriptedOrchestrator(
        compose=json.dumps({"selected_agents": ["code"]}),
        decisions=[json.dumps({"decision": "continue"})]), NaiveBroker())
    try:
        loop.step(task="t", state_view={}, assignment=assignment, store_slice=slice_real)
        raise AssertionError("đáng lẽ vi phạm invariant")
    except AssertionError as exc:
        if "đáng lẽ" in str(exc):
            raise
        print(f"    - NaiveBroker để lọt 'ghost' -> TaskLoop bắt vi phạm invariant: {exc}")
        print("      => Subtype làm YẾU postcondition (source_ids ⊄ slice) = vi phạm LSP.")
        print("         LLMBroker thật KHÔNG yếu hợp đồng dù LLM hallucinate (guardrail trong code).")

    print("\nTẤT CẢ ASSERT PASS. ✅")


if __name__ == "__main__":
    demo()
