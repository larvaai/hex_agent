"""
Case 03 — Adapter: hai Delegation Agent (Scripted + "LangGraph") sau một Port
=============================================================================

Distill TRUNG THỰC từ hex_agent (Adapter / Structural):

  - core/ports.py:32-45
        DelegationPort (Protocol) — Target interface mà core kỳ vọng:
        name (str), can_handle(target) -> bool,
        run(request, child_session, progress_sink) -> DelegationResult.
        Core KHÔNG biết agent là thật (LangGraph) hay giả (scripted).

  - adapters/agents/scripted.py:17-59
        ScriptedDelegationAgent — Concrete Object Adapter bọc một list artifact
        ghi sẵn (test double tất định). Lặp artifacts, gọi progress_sink mỗi
        cái, trả DelegationResult.

  - adapters/agents/langgraph_agent.py:21-95
        LangGraphDelegationAgent — Concrete Object Adapter bọc một đồ thị
        langgraph (graph.stream). Dựng state, stream qua graph, phát progress,
        trả DelegationResult. Cùng Port despite nội tạng hoàn toàn khác.

  - adapters/agents/__init__.py:1-4
        Xuất cả hai adapter -> chứng tỏ chúng thay thế nhau được.

  - core/schemas.py:132-252
        DTO: DelegationSpec, DelegationPolicy, DelegationRequest,
        ArtifactEnvelope, DelegationProgress, DelegationResult.

File này CHỈ dùng thư viện chuẩn Python 3.14. KHÔNG import langgraph / hex_agent.
"Đồ thị LangGraph" thật (LLM + checkpointer) được thay bằng một generator
stdlib `_FakeGraph` chạy vài "bước" tất định, giữ đúng hình dạng stream-rồi-emit.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

# Bộ đếm tất định thay cho uuid4().hex (để demo in ra ổn định, dễ đọc).
_counter = itertools.count(1)


def _next_id(prefix: str) -> str:
    return f"{prefix}-{next(_counter):04d}"


# ──────────────────────────────────────────────────────────────────────────
# DTO — trùng core/schemas.py (rút gọn các trường không cần cho bài học)
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DelegationSpec:
    objective: str
    input_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DelegationPolicy:
    max_steps: int = 20


@dataclass(frozen=True)
class DelegationRequest:
    delegation_id: str
    parent_task_id: str
    target: str
    spec: DelegationSpec
    policy: DelegationPolicy


@dataclass(frozen=True)
class ArtifactEnvelope:
    artifact_id: str
    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DelegationProgress:
    delegation_id: str
    sequence: int
    event_id: str
    artifact: ArtifactEnvelope
    status: str = "running"


@dataclass(frozen=True)
class DelegationResult:
    delegation_id: str
    parent_task_id: str
    outcome: str  # "success" | "failed"
    artifacts: tuple[ArtifactEnvelope, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# child_session rút gọn: chỉ cần một id để trùng hình dạng KernelSession.identity.
@dataclass(frozen=True)
class _Identity:
    session_id: str


@dataclass(frozen=True)
class KernelSession:
    identity: _Identity


ProgressSink = Callable[[DelegationProgress], None]


# ──────────────────────────────────────────────────────────────────────────
# TARGET interface — DelegationPort (trùng core/ports.py:32-45)
# ──────────────────────────────────────────────────────────────────────────
@runtime_checkable
class DelegationPort(Protocol):
    name: str

    def can_handle(self, target: str) -> bool: ...

    def run(
        self,
        request: DelegationRequest,
        child_session: KernelSession,
        progress_sink: ProgressSink,
    ) -> DelegationResult: ...


# ──────────────────────────────────────────────────────────────────────────
# ADAPTER #1 — ScriptedDelegationAgent (adaptee = list artifact ghi sẵn)
# Trùng vai trò adapters/agents/scripted.py:17-59
# ──────────────────────────────────────────────────────────────────────────
class ScriptedDelegationAgent:
    """Adapter tất định cho test: adaptee là một list payload ghi sẵn."""

    def __init__(self, target: str, artifacts: list[dict[str, Any]] | None = None) -> None:
        self.name = target
        self.target = target
        self.artifacts = list(artifacts or [])  # ← adaptee

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(
        self,
        request: DelegationRequest,
        child_session: KernelSession,
        progress_sink: ProgressSink,
    ) -> DelegationResult:
        emitted: list[ArtifactEnvelope] = []
        for sequence, payload in enumerate(self.artifacts, start=1):
            artifact = ArtifactEnvelope(
                artifact_id=_next_id("art"),
                kind=str(payload.get("kind") or "scripted"),
                payload=dict(payload),
            )
            emitted.append(artifact)
            progress_sink(
                DelegationProgress(
                    delegation_id=request.delegation_id,
                    sequence=sequence,
                    event_id=_next_id("evt"),
                    artifact=artifact,
                )
            )
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            artifacts=tuple(emitted),
            summary={
                "target": request.target,
                "objective": request.spec.objective,
                "artifact_count": len(emitted),
                "child_session_id": child_session.identity.session_id,
            },
        )


# ──────────────────────────────────────────────────────────────────────────
# Fake ADAPTEE — "đồ thị LangGraph" (thay langgraph.graph.stream thật)
# ──────────────────────────────────────────────────────────────────────────
class _FakeGraph:
    """Giả lập một graph streaming: mỗi lần stream() yield một 'state' theo
    từng bước, tăng dần budget.steps — đúng hình dạng graph.stream(...,
    stream_mode='values') trong langgraph_agent.py:57-80."""

    def __init__(self, n_steps: int) -> None:
        self._n_steps = n_steps

    def stream(self, objective: str, max_steps: int):
        steps = min(self._n_steps, max_steps)
        for step in range(1, steps + 1):
            completed = step == steps
            yield {
                "steps": step,
                "last_action": {"tool": "search" if not completed else "final", "step": step},
                "status": "completed" if completed else "running",
                "final": f"done: {objective}" if completed else None,
            }


# ──────────────────────────────────────────────────────────────────────────
# ADAPTER #2 — GraphDelegationAgent (adaptee = _FakeGraph stream)
# Trùng vai trò adapters/agents/langgraph_agent.py:21-95
# ──────────────────────────────────────────────────────────────────────────
class GraphDelegationAgent:
    """Adapter 'production-like': adaptee là một đồ thị streaming. Mỗi bước mới
    của graph được dịch thành một ArtifactEnvelope kind='agent_step' và phát
    qua progress_sink — cùng Port với ScriptedDelegationAgent."""

    def __init__(self, target: str, graph: _FakeGraph) -> None:
        self.name = target
        self.target = target
        self._graph = graph  # ← adaptee (composition)

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(
        self,
        request: DelegationRequest,
        child_session: KernelSession,
        progress_sink: ProgressSink,
    ) -> DelegationResult:
        emitted_step = 0
        artifacts: list[ArtifactEnvelope] = []
        final_state: dict[str, Any] = {"steps": 0, "status": "failed", "final": None}
        for values in self._graph.stream(request.spec.objective, request.policy.max_steps):
            final_state = values
            step = int(values.get("steps", 0))
            if step <= emitted_step:
                continue
            emitted_step = step
            artifact = ArtifactEnvelope(
                artifact_id=_next_id("art"),
                kind="agent_step",
                payload={
                    "step": step,
                    "action": dict(values.get("last_action") or {}),
                    "status": values.get("status", "running"),
                },
            )
            artifacts.append(artifact)
            progress_sink(
                DelegationProgress(
                    delegation_id=request.delegation_id,
                    sequence=len(artifacts),
                    event_id=_next_id("evt"),
                    artifact=artifact,
                )
            )

        status = str(final_state.get("status") or "failed")
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success" if status == "completed" else "failed",
            artifacts=tuple(artifacts),
            summary={
                "target": request.target,
                "child_session_id": child_session.identity.session_id,
                "steps": int(final_state.get("steps", 0)),
                "final": final_state.get("final"),
            },
            error=final_state.get("error") if status != "completed" else None,
        )


# ──────────────────────────────────────────────────────────────────────────
# CLIENT — orchestrator chỉ biết DelegationPort, không biết agent là gì
# (tinh thần delegation service trong hex_agent)
# ──────────────────────────────────────────────────────────────────────────
class DelegationOrchestrator:
    def __init__(self, agents: list[DelegationPort]) -> None:
        self._agents = list(agents)

    def available_targets(self) -> tuple[str, ...]:
        return tuple(a.name for a in self._agents)

    def delegate(self, request: DelegationRequest, child_session: KernelSession) -> DelegationResult:
        agent = next((a for a in self._agents if a.can_handle(request.target)), None)
        if agent is None:
            raise ValueError(f"không có agent xử lý target {request.target!r}")
        progress_log: list[DelegationProgress] = []
        # progress_sink: client chỉ thu DelegationProgress, không cần biết nó tới
        # từ list ghi sẵn hay từ graph streaming.
        result = agent.run(request, child_session, progress_log.append)
        # đính số progress vào summary để demo dễ kiểm chứng
        return DelegationResult(
            delegation_id=result.delegation_id,
            parent_task_id=result.parent_task_id,
            outcome=result.outcome,
            artifacts=result.artifacts,
            summary={**result.summary, "progress_events": len(progress_log)},
            error=result.error,
        )


# ──────────────────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────────────────
def _request(target: str) -> DelegationRequest:
    return DelegationRequest(
        delegation_id=_next_id("dlg"),
        parent_task_id="task-root",
        target=target,
        spec=DelegationSpec(objective="tóm tắt repo"),
        policy=DelegationPolicy(max_steps=10),
    )


def demo() -> None:
    print("=" * 70)
    print("CASE 03 — Adapter: hai Delegation Agent sau cùng một DelegationPort")
    print("=" * 70)

    child = KernelSession(identity=_Identity(session_id="child-001"))

    # Adapter 1: scripted (3 artifact ghi sẵn)
    scripted = ScriptedDelegationAgent(
        target="agent:scripted",
        artifacts=[{"kind": "plan", "text": "B1"}, {"kind": "step", "text": "B2"}, {"kind": "answer", "text": "B3"}],
    )
    # Adapter 2: graph (chạy 3 bước rồi completed)
    graph = GraphDelegationAgent(target="agent:graph", graph=_FakeGraph(n_steps=3))

    # CẢ HAI cùng implement DelegationPort -> runtime_checkable kiểm chứng được.
    assert isinstance(scripted, DelegationPort)
    assert isinstance(graph, DelegationPort)
    print("\n[assert] Cả ScriptedDelegationAgent và GraphDelegationAgent đều là DelegationPort. OK")

    orchestrator = DelegationOrchestrator([scripted, graph])
    print("Targets sẵn có:", orchestrator.available_targets())

    print("\n[1] delegate -> agent:scripted (adaptee = list ghi sẵn)")
    res_scripted = orchestrator.delegate(_request("agent:scripted"), child)
    print("    outcome:", res_scripted.outcome)
    print("    artifacts:", [a.kind for a in res_scripted.artifacts])
    print("    summary:", res_scripted.summary)

    print("\n[2] delegate -> agent:graph (adaptee = graph streaming)  — CÙNG code client")
    res_graph = orchestrator.delegate(_request("agent:graph"), child)
    print("    outcome:", res_graph.outcome)
    print("    artifacts:", [a.kind for a in res_graph.artifacts])
    print("    summary:", res_graph.summary)

    # BẤT BIẾN substitutability: cùng hình dạng kết quả + cùng số progress event
    assert res_scripted.outcome == "success" == res_graph.outcome
    assert len(res_scripted.artifacts) == len(res_graph.artifacts) == 3
    assert res_scripted.summary["progress_events"] == res_graph.summary["progress_events"] == 3
    assert isinstance(res_scripted, DelegationResult) and isinstance(res_graph, DelegationResult)
    print("\n[assert] Hai adapter cho cùng hình dạng DelegationResult + cùng 3 progress event.")
    print("         Client xử lý GIỐNG HỆT dù agent tất định hay graph thật. OK")

    # Đối chứng: nếu client phải tự if/else theo loại agent
    print("\n[3] Đối chứng: KHÔNG có Port -> client phải biết nội tạng từng agent")
    print("    - với scripted: phải lặp .artifacts (một list dict)")
    print("    - với graph: phải tự gọi .stream() và tự dịch state -> artifact")
    print("    -> thêm 1 loại agent = sửa client; test không thể đổi production agent")
    print("       lấy fake tất định. Port + adapter loại bỏ chính sự coupling này.")

    print("\nKẾT LUẬN: DelegationPort là biên do core sở hữu; mỗi agent là một")
    print("Object Adapter bọc nội tạng riêng (list hoặc graph). Nhờ vậy test dùng")
    print("ScriptedDelegationAgent chạy nhanh, tất định, không cần LLM — mà core")
    print("không hề biết mình đang nói chuyện với bản thật hay bản giả.")


if __name__ == "__main__":
    demo()
