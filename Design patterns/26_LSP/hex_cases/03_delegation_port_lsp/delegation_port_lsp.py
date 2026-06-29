"""
LSP case 03 — DelegationPort: LangGraphDelegationAgent & ScriptedDelegationAgent thay thế nhau.

Bản DISTILL TRUNG THỰC (chỉ stdlib) của port-adapter DelegationPort trong hex_agent.

NGUỒN THẬT đã mở kiểm chứng (đường dẫn tương đối so với /Users/uspro/Desktop/namnson/hex_agent):
  - core/ports.py:19-26                   ToolPort(Protocol) — họ port giống nhau (tham chiếu)
  - core/ports.py:32-45                   DelegationPort(Protocol): name; can_handle(target)->bool;
                                          run(request, child_session, progress_sink) -> DelegationResult
  - adapters/agents/langgraph_agent.py:21-95  LangGraphDelegationAgent — production: chạy LangGraph,
                                              stream progress, trả DelegationResult outcome success|failed
  - adapters/agents/langgraph_agent.py:82-95  outcome = 'success' if status=='completed' else 'failed'
                                              (KHÔNG raise khi task fail — báo qua field outcome)
  - adapters/agents/scripted.py:17-59     ScriptedDelegationAgent — test: phát artifact hardcode,
                                          cùng interface, outcome='success' (tất định)
  - tests/test_supervisor_loop.py:144-147 isinstance(LangGraphDelegationAgent(...), DelegationPort)

CONTRACT của DelegationPort (cái mà TaskLoop dựa vào):
  - name              : str định danh agent.
  - can_handle(target): bool — agent có nhận target này không.
  - run(...)          : LUÔN trả DelegationResult với:
                          outcome ∈ {"success", "failed"}  (nhị phân),
                          artifacts là tuple,
                          summary là dict.
  - Exception         : task FAIL bình thường KHÔNG raise — báo bằng outcome='failed'.
                        progress_sink được gọi 0+ lần.
LSP: hai impl rất khác nội tạng (LangGraph stream vs hàng đợi scripted) cùng giữ envelope
     DelegationResult -> TaskLoop gom artifact giống nhau, không if/elif theo loại agent.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


# ───────────────────────── value types (distill core/schemas) ──────────────
@dataclass(frozen=True)
class DelegationSpec:
    objective: str


@dataclass(frozen=True)
class DelegationRequest:
    delegation_id: str
    parent_task_id: str
    target: str
    spec: DelegationSpec


@dataclass(frozen=True)
class ArtifactEnvelope:
    artifact_id: str
    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DelegationProgress:
    delegation_id: str
    sequence: int
    artifact: ArtifactEnvelope


@dataclass(frozen=True)
class DelegationResult:
    delegation_id: str
    parent_task_id: str
    outcome: str  # invariant: "success" | "failed"
    artifacts: tuple[ArtifactEnvelope, ...]
    summary: dict[str, Any]
    error: str | None = None


@dataclass
class ChildSession:
    """Đứng thay KernelSession; chỉ giữ session_id cho summary."""
    session_id: str


ProgressSink = Callable[[DelegationProgress], None]


# ───────────────────────── ABSTRACTION (supertype) ─────────────────────────
# Distill của core/ports.py:32-45.
@runtime_checkable
class DelegationPort(Protocol):
    name: str

    def can_handle(self, target: str) -> bool: ...
    def run(self, request: DelegationRequest, child_session: ChildSession,
            progress_sink: ProgressSink) -> DelegationResult: ...


# ───────────────────────── SUBTYPE 1: production (LangGraph) ───────────────
# Distill của adapters/agents/langgraph_agent.py:21-95.
# Thay graph.stream() nặng bằng một "fake graph" stdlib nhưng GIỮ contract:
# stream từng step -> emit artifact + gọi progress_sink -> map status thành outcome.
class _FakeGraph:
    """Đứng thay build_agent_graph().stream(): phát ra N step rồi 'completed' hoặc 'failed'."""

    def __init__(self, *, steps: int, final_status: str) -> None:
        self._steps = steps
        self._final_status = final_status

    def stream(self):
        for i in range(1, self._steps + 1):
            status = "running" if i < self._steps else self._final_status
            yield {"step": i, "action": {"tool": f"step_{i}"}, "status": status}


class LangGraphDelegationAgent:
    """Agent con production: chạy graph, stream progress (nội tạng phức tạp)."""

    def __init__(self, target: str = "agent:general", *, steps: int = 2, final_status: str = "completed") -> None:
        self.name = target
        self.target = target
        self._steps = steps
        self._final_status = final_status

    def can_handle(self, target: str) -> bool:  # langgraph_agent.py:28-29
        return target == self.target

    def run(self, request: DelegationRequest, child_session: ChildSession,
            progress_sink: ProgressSink) -> DelegationResult:
        graph = _FakeGraph(steps=self._steps, final_status=self._final_status)
        artifacts: list[ArtifactEnvelope] = []
        status = "failed"
        for values in graph.stream():  # langgraph_agent.py:57 (graph.stream)
            status = values["status"]
            artifact = ArtifactEnvelope(
                artifact_id=uuid.uuid4().hex, kind="agent_step",
                payload={"step": values["step"], "action": values["action"], "status": status},
            )
            artifacts.append(artifact)
            progress_sink(DelegationProgress(request.delegation_id, len(artifacts), artifact))
        # langgraph_agent.py:82-95 — map status -> outcome; KHÔNG raise khi failed.
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success" if status == "completed" else "failed",
            artifacts=tuple(artifacts),
            summary={"target": request.target, "child_session_id": child_session.session_id,
                     "steps": len(artifacts)},
            error=None if status == "completed" else f"ended with status={status}",
        )


# ───────────────────────── SUBTYPE 2: test (Scripted) ──────────────────────
# Distill của adapters/agents/scripted.py:17-59.
class ScriptedDelegationAgent:
    """Agent con tất định cho test: phát artifact hardcode, cùng envelope DelegationResult."""

    def __init__(self, target: str, artifacts: list[dict[str, Any]] | None = None) -> None:
        self.name = target
        self.target = target
        self.artifacts = list(artifacts or [])

    def can_handle(self, target: str) -> bool:  # scripted.py:23-24
        return target == self.target

    def run(self, request: DelegationRequest, child_session: ChildSession,
            progress_sink: ProgressSink) -> DelegationResult:
        emitted: list[ArtifactEnvelope] = []
        for sequence, payload in enumerate(self.artifacts, start=1):  # scripted.py:33
            artifact = ArtifactEnvelope(
                artifact_id=uuid.uuid4().hex, kind=str(payload.get("kind") or "scripted"),
                payload=dict(payload),
            )
            emitted.append(artifact)
            progress_sink(DelegationProgress(request.delegation_id, sequence, artifact))
        # scripted.py:48-59 — outcome luôn 'success' (tất định cho test).
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            artifacts=tuple(emitted),
            summary={"target": request.target, "objective": request.spec.objective,
                     "artifact_count": len(emitted), "child_session_id": child_session.session_id},
        )


# ───────────────────────── CALLER (depend on abstraction) ──────────────────
# Distill rút gọn của supervisor TaskLoop + delegation registry.
@dataclass
class DelegationRegistry:
    agents: list[DelegationPort] = field(default_factory=list)

    def resolve(self, target: str) -> DelegationPort:
        for a in self.agents:
            if a.can_handle(target):  # gọi qua abstraction, không isinstance
                return a
        raise KeyError(f"no agent handles target {target!r}")


class TaskLoop:
    """Supervisor gom artifact từ agent con — KHÔNG biết agent là loại nào."""

    def __init__(self, registry: DelegationRegistry) -> None:
        self._registry = registry
        self.events: list[str] = []

    def delegate(self, target: str, objective: str) -> dict:
        agent = self._registry.resolve(target)
        request = DelegationRequest(uuid.uuid4().hex, "parent-task", target, DelegationSpec(objective))
        child = ChildSession(session_id=uuid.uuid4().hex)
        sink: ProgressSink = lambda p: self.events.append(f"progress#{p.sequence}")  # noqa: E731
        result = agent.run(request, child, sink)
        # Plumbing GIỐNG HỆT cho mọi agent: chỉ đọc envelope, không branch theo loại.
        assert result.outcome in ("success", "failed"), "outcome phải nhị phân"
        return {"outcome": result.outcome, "artifacts": len(result.artifacts), "summary": result.summary}


# ───────────────────────── LISKOV CONTRACT TEST (abstract) ─────────────────
def liskov_contract(agent: DelegationPort) -> None:
    """Bộ test contract chạy y hệt trên MỌI delegation agent."""
    assert isinstance(agent, DelegationPort), "phải thỏa DelegationPort"
    assert isinstance(agent.name, str), "name phải là str"
    assert agent.can_handle(agent.target) is True, "can_handle target của chính nó -> True"
    request = DelegationRequest("d1", "p1", agent.target, DelegationSpec("làm việc"))
    seen: list[int] = []
    result = agent.run(request, ChildSession("sess-1"), lambda p: seen.append(p.sequence))
    assert isinstance(result, DelegationResult), "run() phải trả DelegationResult"
    assert result.outcome in ("success", "failed"), "outcome ∈ {success, failed}"
    assert isinstance(result.artifacts, tuple), "artifacts là tuple"
    assert isinstance(result.summary, dict), "summary là dict"
    # progress_sink được gọi đúng số artifact đã phát (0+).
    assert seen == list(range(1, len(result.artifacts) + 1)), "progress phát tuần tự theo artifact"


def demo() -> None:
    print("=" * 72)
    print("LSP case 03 — DelegationPort: LangGraph & Scripted agent swap")
    print("=" * 72)

    lang_ok = LangGraphDelegationAgent("agent:general", steps=2, final_status="completed")
    scripted = ScriptedDelegationAgent("agent:general", artifacts=[{"kind": "note", "text": "done"}])

    print("\n[1] Liskov contract test trên CẢ HAI agent (cùng 1 bộ assert):")
    for name, ag in (("LangGraphDelegationAgent", lang_ok), ("ScriptedDelegationAgent", scripted)):
        liskov_contract(ag)
        print(f"    - {name:24s}: PASS")

    print("\n[2] TaskLoop phụ thuộc abstraction — plumbing GIỐNG HỆT khi swap agent:")
    for name, ag in (("LangGraph", lang_ok), ("Scripted", scripted)):
        loop = TaskLoop(DelegationRegistry([ag]))
        res = loop.delegate("agent:general", "viết hàm cộng")
        print(f"    - TaskLoop(agent={name:9s}).delegate -> outcome={res['outcome']!r}, "
              f"artifacts={res['artifacts']}, progress_events={loop.events}")

    print("\n[3] CONTRACT về exception: task FAIL -> outcome='failed', KHÔNG raise:")
    lang_fail = LangGraphDelegationAgent("agent:general", steps=2, final_status="aborted")
    loop = TaskLoop(DelegationRegistry([lang_fail]))
    res = loop.delegate("agent:general", "việc sẽ hỏng")
    print(f"    - LangGraph kết thúc status='aborted' -> outcome={res['outcome']!r} (báo qua field, không exception)")
    assert res["outcome"] == "failed"

    print("\n[4] ĐỐI CHỨNG — agent VI PHẠM exception contract (raise thay vì outcome='failed'):")

    class CrashingAgent:
        name = "agent:general"
        target = "agent:general"

        def can_handle(self, target: str) -> bool:
            return target == self.target

        def run(self, request, child_session, progress_sink) -> DelegationResult:
            raise RuntimeError("delegation blew up")  # ← mở rộng exception ngoài hợp đồng

    loop = TaskLoop(DelegationRegistry([CrashingAgent()]))
    try:
        loop.delegate("agent:general", "việc")
        raise AssertionError("đáng lẽ crash")
    except RuntimeError:
        print("    - run() raise RuntimeError -> THOÁT khỏi TaskLoop -> supervisor crash giữa vòng lặp.")
        print("      TaskLoop không try/except RuntimeError (hợp đồng nói task fail báo qua outcome).")
        print("      => Subtype raise exception lạ = vi phạm LSP; ép caller phải biết loại agent.")

    print("\nTẤT CẢ ASSERT PASS. ✅")


if __name__ == "__main__":
    demo()
