"""
Hexagonal (Ports & Adapters) — Case 02: Delegation, DRIVING port + nhiều adapter chiến lược.

Bản DISTILL TRUNG THỰC từ codebase hex_agent. Nguồn thật:
  - core/ports.py:32-45             -> DelegationPort (DRIVING PORT: lõi định nghĩa cái nó LÀM được)
  - core/ports.py:48-62             -> DelegationStorePort (DRIVEN PORT cho lưu progress/result)
  - adapters/agents/scripted.py:17-59       -> ScriptedDelegationAgent (DRIVING ADAPTER deterministic)
  - adapters/agents/langgraph_agent.py:21-95 -> LangGraphDelegationAgent (DRIVING ADAPTER production)
  - delegation/store.py:9-56        -> InMemoryDelegationStore (DRIVEN ADAPTER, comment: "durable adapter later")
  - delegation/manager.py:19-32     -> DelegationManager.__init__ (CORE ORCHESTRATOR, inject registry+store)
  - delegation/manager.py:119-192   -> DelegationManager.delegate() resolve handler + run + persist
  - delegation/bootstrap.py:13-24   -> create_delegation_service() (COMPOSITION ROOT: nơi DUY NHẤT import adapter)
  - delegation/registry.py          -> DelegationRegistry (đăng ký adapter theo target)

Điều case này LƯỢC BỎ so với bản thật:
  - Bỏ LangGraph + LLM thật: LangGraph-adapter ở đây gọi 1 "fake graph" sinh step bằng stdlib,
    giữ NGUYÊN vai trò: production adapter chạy nhiều bước, emit progress per step.
  - Bỏ KernelSession/SessionFactory thật: thay bằng FakeSession tối thiểu (chỉ có id).
  - Bỏ policy engine, redaction, event publish: giữ phần lõi resolve->run->persist->finish.
  - Giữ NGUYÊN: driving port do lõi sở hữu, registry để add adapter không sửa core,
    composition root là nơi duy nhất biết adapter cụ thể.

Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent, KHÔNG thư viện bên thứ ba.
Chạy: python3 delegation_agents_pattern.py   (thoát code 0, không traceback)
"""
from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

# ─────────────────────────────────────────────────────────────────────────────
# 0) VALUE TYPES (distill core/schemas: DelegationRequest/Result/Progress/Artifact)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DelegationRequest:
    delegation_id: str
    target: str
    objective: str
    max_steps: int = 8


@dataclass(frozen=True)
class DelegationProgress:
    delegation_id: str
    sequence: int
    artifact: Artifact


@dataclass(frozen=True)
class DelegationResult:
    delegation_id: str
    outcome: str                       # "success" | "failed" | "rejected"
    artifacts: tuple[Artifact, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# Sink mà adapter gọi để báo tiến độ từng bước về cho lõi.
ProgressSink = Callable[[DelegationProgress], None]


# ─────────────────────────────────────────────────────────────────────────────
# 1) PORTS  (distill core/ports.py:32-62)
#    DRIVING port: lõi định nghĩa "việc lõi làm được" (run). Adapter PHẢI implement.
#    Khác driven port (case 01): ở đó lõi GỌI RA; ở đây thế giới ngoài (adapter) ĐƯỢC GỌI VÀO run.
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class DelegationPort(Protocol):
    """DRIVING PORT. Mỗi adapter chiến lược phải có name + can_handle() + run()."""
    name: str

    def can_handle(self, target: str) -> bool: ...

    def run(self, request: DelegationRequest, child_session: "FakeSession",
            progress_sink: ProgressSink) -> DelegationResult: ...


class DelegationStorePort(Protocol):
    """DRIVEN PORT cho lưu trữ: lõi gọi ra để persist. Adapter làm thật."""
    def start(self, request: DelegationRequest) -> None: ...
    def append_progress(self, progress: DelegationProgress) -> None: ...
    def finish(self, result: DelegationResult) -> None: ...
    def progress(self, delegation_id: str) -> tuple[DelegationProgress, ...]: ...
    def result(self, delegation_id: str) -> DelegationResult | None: ...


# ─────────────────────────────────────────────────────────────────────────────
# 2) FakeSession  (thay KernelSession thật, chỉ giữ id)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FakeSession:
    session_id: str

    @property
    def is_active(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
# 3) DRIVING ADAPTERS  — hai chiến lược hoàn toàn khác nhau, cùng DelegationPort.
# ─────────────────────────────────────────────────────────────────────────────
class ScriptedDelegationAgent:
    """DRIVING ADAPTER deterministic (distill adapters/agents/scripted.py:17-59).
    Dùng trong test: trả artifact đã 'đóng hộp', emit progress từng cái."""
    def __init__(self, target: str, artifacts: list[dict[str, Any]] | None = None) -> None:
        self.name = target
        self.target = target
        self.artifacts = list(artifacts or [])

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(self, request: DelegationRequest, child_session: FakeSession,
            progress_sink: ProgressSink) -> DelegationResult:
        emitted: list[Artifact] = []
        for sequence, payload in enumerate(self.artifacts, start=1):
            art = Artifact(uuid.uuid4().hex, str(payload.get("kind") or "scripted"), dict(payload))
            emitted.append(art)
            progress_sink(DelegationProgress(request.delegation_id, sequence, art))
        return DelegationResult(
            delegation_id=request.delegation_id,
            outcome="success",
            artifacts=tuple(emitted),
            summary={"target": request.target, "objective": request.objective,
                     "artifact_count": len(emitted), "child_session_id": child_session.session_id},
        )


class _FakeGraph:
    """Thay LangGraph thật: stream ra vài 'step' deterministic thay vì gọi LLM."""
    def __init__(self, n_steps: int) -> None:
        self._n_steps = n_steps

    def stream(self, objective: str):
        for step in range(1, self._n_steps + 1):
            yield {"step": step, "action": {"do": f"work on '{objective}' part {step}"},
                   "status": "running" if step < self._n_steps else "completed"}


class LangGraphDelegationAgent:
    """DRIVING ADAPTER production (distill adapters/agents/langgraph_agent.py:21-95).
    Gọi vào 1 graph, emit 1 artifact mỗi step. Ở đây graph là _FakeGraph (stdlib)."""
    def __init__(self, target: str = "agent:general", *, n_steps: int = 3) -> None:
        self.name = target
        self.target = target
        self._n_steps = n_steps

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(self, request: DelegationRequest, child_session: FakeSession,
            progress_sink: ProgressSink) -> DelegationResult:
        graph = _FakeGraph(self._n_steps)
        artifacts: list[Artifact] = []
        final_status = "failed"
        for values in graph.stream(request.objective):
            final_status = values["status"]
            art = Artifact(uuid.uuid4().hex, "agent_step",
                           {"step": values["step"], "action": values["action"],
                            "status": values["status"]})
            artifacts.append(art)
            progress_sink(DelegationProgress(request.delegation_id, len(artifacts), art))
        return DelegationResult(
            delegation_id=request.delegation_id,
            outcome="success" if final_status == "completed" else "failed",
            artifacts=tuple(artifacts),
            summary={"target": request.target, "steps": len(artifacts),
                     "child_session_id": child_session.session_id},
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4) DRIVEN ADAPTER cho store (distill delegation/store.py:9-56)
# ─────────────────────────────────────────────────────────────────────────────
class InMemoryDelegationStore:
    """Deterministic v1 store; 'a durable adapter can implement the same port later'."""
    def __init__(self) -> None:
        self._requests: dict[str, DelegationRequest] = {}
        self._progress: dict[str, list[DelegationProgress]] = {}
        self._results: dict[str, DelegationResult] = {}

    def start(self, request: DelegationRequest) -> None:
        if request.delegation_id in self._requests:
            raise ValueError(f"Delegation already exists: {request.delegation_id}")
        self._requests[request.delegation_id] = request
        self._progress[request.delegation_id] = []

    def append_progress(self, progress: DelegationProgress) -> None:
        items = self._progress.get(progress.delegation_id)
        if items is None:
            raise LookupError(f"Unknown delegation: {progress.delegation_id}")
        expected = len(items) + 1
        if progress.sequence != expected:        # ép thứ tự ghi đúng (như bản thật)
            raise ValueError(f"Progress sequence must be {expected}, got {progress.sequence}.")
        items.append(progress)

    def finish(self, result: DelegationResult) -> None:
        if result.delegation_id not in self._requests:
            raise LookupError(f"Unknown delegation: {result.delegation_id}")
        self._results[result.delegation_id] = result

    def progress(self, delegation_id: str) -> tuple[DelegationProgress, ...]:
        return tuple(self._progress.get(delegation_id, ()))

    def result(self, delegation_id: str) -> DelegationResult | None:
        return self._results.get(delegation_id)


# ─────────────────────────────────────────────────────────────────────────────
# 5) REGISTRY  (distill delegation/registry.py)
#    Cho phép ADD adapter mà KHÔNG sửa lõi orchestrator. Đăng ký theo can_handle().
# ─────────────────────────────────────────────────────────────────────────────
class DelegationRegistry:
    def __init__(self) -> None:
        self._agents: list[DelegationPort] = []
        self._frozen = False

    def register(self, agent: DelegationPort) -> None:
        if self._frozen:
            raise RuntimeError("registry frozen")
        self._agents.append(agent)

    def freeze(self) -> None:
        self._frozen = True

    def targets(self) -> tuple[str, ...]:
        return tuple(a.name for a in self._agents)

    def resolve(self, target: str) -> DelegationPort:
        for agent in self._agents:
            if agent.can_handle(target):
                return agent
        raise LookupError(f"No delegation adapter can handle target: {target!r}")


# ─────────────────────────────────────────────────────────────────────────────
# 6) CORE ORCHESTRATOR  (distill delegation/manager.py:19-32, 119-192)
#    DelegationManager nhận registry + store qua __init__ (DI). Nó KHÔNG biết
#    ScriptedDelegationAgent hay LangGraphDelegationAgent — chỉ biết DelegationPort.
# ─────────────────────────────────────────────────────────────────────────────
class DelegationManager:
    def __init__(self, *, registry: DelegationRegistry, store: DelegationStorePort) -> None:
        self.registry = registry
        self.store = store
        self._session_ids = itertools.count(1)
        self.registry.freeze()

    def available_targets(self) -> tuple[str, ...]:
        return self.registry.targets()

    def delegate(self, target: str, objective: str, *, max_steps: int = 8) -> DelegationResult:
        if not target:
            raise ValueError("Delegation target must not be empty.")
        if not objective:
            raise ValueError("Delegation objective must not be empty.")

        delegation_id = uuid.uuid4().hex
        request = DelegationRequest(delegation_id, target, objective, max_steps)
        self.store.start(request)

        child = FakeSession(session_id=f"child-{next(self._session_ids)}")

        def progress_sink(progress: DelegationProgress) -> None:
            if progress.delegation_id != delegation_id:
                raise ValueError("Progress delegation_id does not match the active request.")
            if progress.sequence > max_steps:
                raise ValueError("Delegation progress exceeded max_steps.")
            self.store.append_progress(progress)   # source of truth first

        try:
            handler = self.registry.resolve(target)        # lõi chọn adapter qua port
            result = handler.run(request, child, progress_sink)
            if result.delegation_id != delegation_id:
                raise ValueError("Delegation result ID does not match the request.")
        except Exception as exc:
            progressed = self.store.progress(delegation_id)
            result = DelegationResult(delegation_id, outcome="failed",
                                      artifacts=tuple(p.artifact for p in progressed),
                                      error=str(exc))
        self.store.finish(result)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# 7) COMPOSITION ROOT  (distill delegation/bootstrap.py:13-24)
#    Nơi DUY NHẤT import + chọn adapter cụ thể. Đổi mode = đổi 1 chỗ này.
# ─────────────────────────────────────────────────────────────────────────────
def create_delegation_service(*, mode: str, target: str = "agent:general") -> DelegationManager:
    registry = DelegationRegistry()
    if mode == "scripted":
        registry.register(ScriptedDelegationAgent(
            target, artifacts=[{"kind": "finding", "value": 1}, {"kind": "finding", "value": 2}]))
    elif mode == "langgraph":
        registry.register(LangGraphDelegationAgent(target, n_steps=3))
    else:
        raise ValueError(f"Unknown delegation mode: {mode!r}")
    return DelegationManager(registry=registry, store=InMemoryDelegationStore())


# ─────────────────────────────────────────────────────────────────────────────
# 8) PHẢN VÍ DỤ: supervisor gọi thẳng class adapter cụ thể (không qua port/registry)
# ─────────────────────────────────────────────────────────────────────────────
class HardWiredSupervisor:
    """ANTI-PATTERN: lõi new thẳng LangGraphDelegationAgent.
    Muốn dùng Scripted trong test phải SỬA lõi -> mất khả năng test offline."""
    def __init__(self) -> None:
        self._agent = LangGraphDelegationAgent("agent:general")   # ← lõi biết adapter cụ thể: SAI

    def delegate(self, objective: str) -> DelegationResult:
        req = DelegationRequest(uuid.uuid4().hex, "agent:general", objective)
        return self._agent.run(req, FakeSession("x"), lambda p: None)


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 02 — Delegation: DRIVING port + nhiều adapter chiến lược")
    print("=" * 72)

    # --- (1) Mode scripted (test) ---
    print("\n[1] create_delegation_service(mode='scripted') — adapter deterministic")
    svc_scripted = create_delegation_service(mode="scripted", target="agent:general")
    print(f"    targets = {svc_scripted.available_targets()}")
    r1 = svc_scripted.delegate("agent:general", "review the PR")
    print(f"    outcome={r1.outcome} artifacts={len(r1.artifacts)} "
          f"kinds={[a.kind for a in r1.artifacts]}")
    assert r1.outcome == "success" and len(r1.artifacts) == 2

    # --- (2) Mode langgraph (prod) — CÙNG DelegationManager, khác adapter ---
    print("\n[2] create_delegation_service(mode='langgraph') — adapter production (fake graph)")
    svc_lg = create_delegation_service(mode="langgraph", target="agent:general")
    r2 = svc_lg.delegate("agent:general", "build the feature")
    print(f"    outcome={r2.outcome} artifacts={len(r2.artifacts)} "
          f"kinds={[a.kind for a in r2.artifacts]}")
    assert r2.outcome == "success" and all(a.kind == "agent_step" for a in r2.artifacts)

    # BẤT BIẾN: hai service dùng CÙNG class DelegationManager — chỉ adapter khác.
    assert type(svc_scripted) is type(svc_lg) is DelegationManager
    print("    [assert] cả hai dùng CÙNG DelegationManager; lõi không đổi 1 dòng. OK")

    # --- (3) progress được persist TRƯỚC khi finish (source of truth) ---
    print("\n[3] Store giữ progress theo thứ tự; lõi đọc lại từ store")
    did = r2.delegation_id
    seqs = [p.sequence for p in svc_lg.store.progress(did)]
    assert seqs == sorted(seqs) and seqs == list(range(1, len(seqs) + 1))
    print(f"    progress sequences = {seqs} (đúng thứ tự, idempotent-friendly). OK")

    # --- (4) Add adapter mới mà KHÔNG sửa lõi ---
    print("\n[4] Mở rộng: đăng ký thêm 1 adapter target mới vào registry")
    reg = DelegationRegistry()
    reg.register(ScriptedDelegationAgent("agent:review", artifacts=[{"kind": "note"}]))
    reg.register(LangGraphDelegationAgent("agent:build", n_steps=2))
    mgr = DelegationManager(registry=reg, store=InMemoryDelegationStore())
    print(f"    targets sau khi add 2 adapter = {mgr.available_targets()}")
    assert mgr.delegate("agent:review", "x").outcome == "success"
    assert mgr.delegate("agent:build", "y").outcome == "success"
    print("    [assert] DelegationManager phục vụ cả 2 target mới, KHÔNG sửa code lõi. OK")

    # --- (5) Target không adapter nào nhận -> failed sạch (không crash chương trình) ---
    print("\n[5] delegate tới target không ai handle -> outcome=failed, error rõ ràng")
    r5 = mgr.delegate("agent:unknown", "z")
    assert r5.outcome == "failed" and r5.error is not None
    print(f"    outcome={r5.outcome} error='{r5.error}'")

    # --- (6) PHẢN VÍ DỤ ---
    print("\n[6] PHẢN VÍ DỤ — HardWiredSupervisor new thẳng LangGraph trong lõi")
    print("    Không qua port/registry => muốn test offline bằng Scripted phải SỬA lõi.")
    print("    => kẹt cứng với 1 adapter. Đây là cái driving-port giải phóng ta khỏi.")

    print("\n" + "=" * 72)
    print("KẾT LUẬN: driving port = 'việc lõi làm được'; adapter là cách làm.")
    print("Registry + composition root cho phép thêm/đổi adapter mà lõi đứng yên.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
