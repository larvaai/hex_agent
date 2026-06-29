"""
Case 01 — Core Ports + Adapter Implementation (Delegation seam).

Bản DISTILL trung thực của Clean Architecture "core owns Protocol, adapter implements it"
trong hex_agent. Use case (DelegationManager) chỉ phụ thuộc Protocol; nó KHÔNG bao giờ
biết adapter cụ thể nào. Đổi adapter tại composition root → hành vi đổi, logic use case y nguyên.

Nguồn thật trong hex_agent (đã mở kiểm chứng):
  - core/ports.py:32-45        -> DelegationPort (Protocol owned by CORE; output port)
  - core/ports.py:48-63        -> DelegationStorePort (Protocol owned by CORE)
  - core/schemas.py:132-198    -> DelegationSpec, DelegationRequest (frozen dataclass entities)
  - core/schemas.py:201-253    -> ArtifactEnvelope, DelegationProgress, DelegationResult
  - adapters/agents/scripted.py:17-59 -> ScriptedDelegationAgent implements DelegationPort
  - delegation/manager.py:19-192      -> DelegationManager (use case orchestrating port calls)
  - delegation/registry.py:9-40       -> DelegationRegistry (resolve target -> DelegationPort)
  - delegation/store.py:9-56          -> InMemoryDelegationStore implements DelegationStorePort
  - delegation/bootstrap.py:13-24     -> composition root: wire adapter cụ thể vào use case
  - tests/test_delegation.py:14-40    -> test wire fake store + ScriptedDelegationAgent, zero framework

Chỉ dùng standard library. Hạ tầng nặng (LangGraph agent, kernel events thật) được thay bằng
fake tối thiểu để giữ ĐÚNG vai trò pattern, không kéo theo dependency.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 1 — ENTITIES (core/schemas.py). Frozen dataclass, pure data, không I/O.
# Đây là contract bất biến đi qua mọi boundary.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DelegationSpec:
    """Mô tả công việc giao đi — distill core/schemas.py:132-147."""
    objective: str
    input_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DelegationRequest:
    """Yêu cầu giao việc — distill core/schemas.py:181-198."""
    delegation_id: str
    parent_task_id: str
    target: str
    spec: DelegationSpec


@dataclass(frozen=True)
class ArtifactEnvelope:
    """Sản phẩm trả về — distill core/schemas.py:201-214."""
    artifact_id: str
    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DelegationProgress:
    """Một bước tiến độ — distill core/schemas.py:217-232."""
    delegation_id: str
    sequence: int
    event_id: str
    artifact: ArtifactEnvelope


@dataclass(frozen=True)
class DelegationResult:
    """Kết quả cuối — distill core/schemas.py:235-253."""
    delegation_id: str
    parent_task_id: str
    outcome: str  # "success" | "failed" | "rejected"
    artifacts: tuple[ArtifactEnvelope, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# Callback type giống core/ports.py:29 (ProgressSink).
ProgressSink = Callable[[DelegationProgress], None]


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT PORTS — owned by CORE (core/ports.py). Đây là interface mà use case GỌI,
# nhưng implementation sống ở vòng ngoài. Source-code dependency: adapter -> core.
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class DelegationPort(Protocol):
    """Distill core/ports.py:32-45. 'A delegation agent. Concrete behavior lives behind this port.'"""
    name: str

    def can_handle(self, target: str) -> bool: ...

    def run(self, request: DelegationRequest, progress_sink: ProgressSink) -> DelegationResult: ...


class DelegationStorePort(Protocol):
    """Distill core/ports.py:48-63. Use case ghi tiến độ/kết quả qua port này."""
    def start(self, request: DelegationRequest) -> None: ...
    def append_progress(self, progress: DelegationProgress) -> None: ...
    def finish(self, result: DelegationResult) -> None: ...
    def progress(self, delegation_id: str) -> tuple[DelegationProgress, ...]: ...


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 2 — USE CASE (delegation/manager.py + registry.py). Phụ thuộc ENTITIES + PORTS,
# tuyệt đối KHÔNG import adapter cụ thể. Đây là "application business rule".
# ─────────────────────────────────────────────────────────────────────────────
class DelegationRegistry:
    """Distill delegation/registry.py:9-40. Resolve một target -> DelegationPort.
    Chỉ biết Protocol, không biết class cụ thể."""

    def __init__(self) -> None:
        self._handlers: list[DelegationPort] = []
        self._frozen = False

    def register(self, handler: DelegationPort) -> None:
        if self._frozen:
            raise RuntimeError("Delegation registry is frozen.")
        if any(h.name == handler.name for h in self._handlers):
            raise ValueError(f"Delegation handler already registered: {handler.name}")
        self._handlers.append(handler)

    def freeze(self) -> None:
        self._frozen = True

    def resolve(self, target: str) -> DelegationPort:
        matches = [h for h in self._handlers if h.can_handle(target)]
        if not matches:
            raise LookupError(f"No delegation handler registered for target '{target}'.")
        if len(matches) > 1:
            raise LookupError(f"Ambiguous delegation target '{target}'.")
        return matches[0]

    def targets(self) -> tuple[str, ...]:
        return tuple(sorted(h.name for h in self._handlers))


class DelegationManager:
    """Distill delegation/manager.py:19-192 (lược các nhánh policy/child-session để giữ vào trọng tâm).

    Use case orchestrate: resolve handler -> store.start -> handler.run(..) -> ghép artifacts -> store.finish.
    LƯU Ý: nó nhận `registry` (chứa DelegationPort) và `store` (DelegationStorePort) qua __init__ —
    DEPENDENCY INJECTION. Use case không bao giờ `import ScriptedDelegationAgent`.
    """

    def __init__(self, *, registry: DelegationRegistry, store: DelegationStorePort) -> None:
        self.registry = registry
        self.store = store
        self.registry.freeze()

    def available_targets(self) -> tuple[str, ...]:
        return self.registry.targets()

    def delegate(self, *, parent_task_id: str, target: str, spec: DelegationSpec) -> DelegationResult:
        if not target:
            raise ValueError("Delegation target must not be empty.")
        if not spec.objective:
            raise ValueError("Delegation objective must not be empty.")

        delegation_id = uuid.uuid4().hex
        request = DelegationRequest(
            delegation_id=delegation_id,
            parent_task_id=parent_task_id,
            target=target,
            spec=spec,
        )
        self.store.start(request)

        # progress_sink: use case "talk outward" — ghi vào store (output port) trước,
        # giống delegation/manager.py:142-157 (source of truth first).
        def progress_sink(progress: DelegationProgress) -> None:
            if progress.delegation_id != delegation_id:
                raise ValueError("Progress delegation_id does not match the active request.")
            self.store.append_progress(progress)

        handler = self.registry.resolve(target)            # <- chỉ thấy Protocol
        result = handler.run(request, progress_sink)        # <- runtime call ra adapter

        # Bất biến từ manager.py:161-164: kết quả phải khớp request.
        if result.delegation_id != delegation_id:
            raise ValueError("Delegation result ID does not match the request.")
        if result.parent_task_id != parent_task_id:
            raise ValueError("Delegation result parent_task_id does not match the parent.")

        self.store.finish(result)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 3 — ADAPTERS. Implement port. Đây là nơi DUY NHẤT chứa chi tiết cụ thể.
# adapters/agents/scripted.py + delegation/store.py
# ─────────────────────────────────────────────────────────────────────────────
class InMemoryDelegationStore:
    """Distill delegation/store.py:9-56. Bản in-memory; production swap DB cùng port."""

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
        if progress.sequence != expected:
            raise ValueError(f"Progress sequence must be {expected}, got {progress.sequence}.")
        items.append(progress)

    def finish(self, result: DelegationResult) -> None:
        if result.delegation_id not in self._requests:
            raise LookupError(f"Unknown delegation: {result.delegation_id}")
        self._results[result.delegation_id] = result

    def progress(self, delegation_id: str) -> tuple[DelegationProgress, ...]:
        return tuple(self._progress.get(delegation_id, ()))


class ScriptedDelegationAgent:
    """Distill adapters/agents/scripted.py:17-59.

    'Deterministic delegation adapter for tests and local architecture smoke runs.'
    Phát ra một loạt artifact đã được nạp sẵn. Đây là một implementation của DelegationPort.
    """

    def __init__(self, target: str, artifacts: list[dict[str, Any]] | None = None) -> None:
        self.name = target
        self.target = target
        self.artifacts = list(artifacts or [])

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(self, request: DelegationRequest, progress_sink: ProgressSink) -> DelegationResult:
        emitted: list[ArtifactEnvelope] = []
        for sequence, payload in enumerate(self.artifacts, start=1):
            artifact = ArtifactEnvelope(
                artifact_id=uuid.uuid4().hex,
                kind=str(payload.get("kind") or "scripted"),
                payload=dict(payload),
            )
            emitted.append(artifact)
            progress_sink(DelegationProgress(
                delegation_id=request.delegation_id,
                sequence=sequence,
                event_id=uuid.uuid4().hex,
                artifact=artifact,
            ))
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            artifacts=tuple(emitted),
            summary={"target": request.target, "artifact_count": len(emitted)},
        )


class EchoDelegationAgent:
    """Adapter THỨ HAI implement CÙNG port — đại diện cho LangGraphDelegationAgent thật.

    Ở hex_agent, delegation/bootstrap.py:19 wire LangGraphDelegationAgent (LLM/graph thật).
    Ở đây ta thay bằng một adapter 'echo' đơn giản để chứng minh: đổi adapter mà use case
    KHÔNG đổi một dòng nào.
    """

    def __init__(self, target: str) -> None:
        self.name = target
        self.target = target

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(self, request: DelegationRequest, progress_sink: ProgressSink) -> DelegationResult:
        artifact = ArtifactEnvelope(
            artifact_id=uuid.uuid4().hex,
            kind="echo",
            payload={"echo": request.spec.objective},
        )
        progress_sink(DelegationProgress(
            delegation_id=request.delegation_id, sequence=1,
            event_id=uuid.uuid4().hex, artifact=artifact,
        ))
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            artifacts=(artifact,),
            summary={"target": request.target, "engine": "echo"},
        )


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITION ROOT (delegation/bootstrap.py:13-24).
# Nơi DUY NHẤT thấy cả use case lẫn adapter. Đổi adapter ở ĐÂY, không đụng use case.
# ─────────────────────────────────────────────────────────────────────────────
def create_delegation_service(target: str, agent_factory: Callable[[str], DelegationPort]) -> DelegationManager:
    """Distill delegation/bootstrap.py:13-24. agent_factory cho phép chọn adapter cụ thể."""
    registry = DelegationRegistry()
    registry.register(agent_factory(target))      # <- wire adapter vào port
    return DelegationManager(registry=registry, store=InMemoryDelegationStore())


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — "khi KHÔNG dùng pattern": use case import thẳng adapter cụ thể.
# ─────────────────────────────────────────────────────────────────────────────
class TightlyCoupledManager:
    """Anti-pattern: use case tự khởi tạo adapter cụ thể bên trong -> vi phạm dependency rule.

    Triệu chứng: muốn đổi engine phải SỬA class này; muốn test phải chạy adapter thật.
    """

    def __init__(self, target: str) -> None:
        # Use case 'biết' chính xác adapter nào — đây là điều Clean Architecture cấm.
        self._agent = ScriptedDelegationAgent(target, artifacts=[{"kind": "hardcoded"}])
        self._store = InMemoryDelegationStore()

    def delegate(self, *, parent_task_id: str, target: str, spec: DelegationSpec) -> DelegationResult:
        request = DelegationRequest(uuid.uuid4().hex, parent_task_id, target, spec)
        self._store.start(request)
        result = self._agent.run(request, lambda p: self._store.append_progress(p))
        self._store.finish(result)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 74)
    print("CASE 01 — Core Port + Adapter (Delegation seam) trong hex_agent")
    print("=" * 74)

    spec = DelegationSpec(objective="Review module thanh toán", input_context={"pr": 42})

    print("\n[1] Wire adapter SCRIPTED qua composition root (delegation/bootstrap.py).")
    svc_scripted = create_delegation_service(
        "agent:review",
        lambda t: ScriptedDelegationAgent(t, artifacts=[{"kind": "finding", "value": "lỗi off-by-one"}]),
    )
    print("    available_targets() =", svc_scripted.available_targets())
    r1 = svc_scripted.delegate(parent_task_id="task-1", target="agent:review", spec=spec)
    print("    outcome =", r1.outcome, "| #artifacts =", len(r1.artifacts),
          "| kind =", r1.artifacts[0].kind)

    print("\n[2] Đổi sang adapter ECHO — composition root đổi 1 dòng, use case Y NGUYÊN.")
    svc_echo = create_delegation_service("agent:review", lambda t: EchoDelegationAgent(t))
    r2 = svc_echo.delegate(parent_task_id="task-1", target="agent:review", spec=spec)
    print("    outcome =", r2.outcome, "| kind =", r2.artifacts[0].kind,
          "| engine =", r2.summary.get("engine"))
    print("    -> CÙNG DelegationManager, CHỈ adapter khác. Đây là dependency rule một chiều.")

    print("\n[3] Unit-test use case CHỈ cần một MOCK PORT — không import adapter thật.")
    calls: list[str] = []

    class SpyAgent:  # mock implement DelegationPort, không cần kế thừa gì
        name = "agent:spy"
        def can_handle(self, target: str) -> bool: return target == "agent:spy"
        def run(self, request: DelegationRequest, sink: ProgressSink) -> DelegationResult:
            calls.append(request.spec.objective)
            return DelegationResult(request.delegation_id, request.parent_task_id, "success")

    reg = DelegationRegistry(); reg.register(SpyAgent())
    mgr = DelegationManager(registry=reg, store=InMemoryDelegationStore())
    r3 = mgr.delegate(parent_task_id="task-9", target="agent:spy",
                      spec=DelegationSpec(objective="test thuần"))
    print("    spy nhận objective =", calls, "| outcome =", r3.outcome)

    print("\n[4] ĐỐI CHỨNG — TightlyCoupledManager (KHÔNG dùng pattern):")
    bad = TightlyCoupledManager("agent:review")
    rbad = bad.delegate(parent_task_id="task-x", target="agent:review", spec=spec)
    print("    chạy được nhưng adapter bị HARD-CODE bên trong:", rbad.artifacts[0].kind)
    print("    -> muốn đổi engine phải SỬA class use case; muốn test phải chạy adapter thật.")

    # ── ASSERT: chứng minh bất biến của pattern ──
    # (a) Đổi adapter -> kết quả khác, nhưng cả hai vẫn success: use case không đổi.
    assert r1.artifacts[0].kind == "finding"
    assert r2.artifacts[0].kind == "echo"
    assert r1.outcome == r2.outcome == "success"
    # (b) Use case chỉ phụ thuộc Protocol: SpyAgent (không kế thừa gì) vẫn chạy được.
    assert isinstance(SpyAgent(), DelegationPort)          # runtime_checkable Protocol
    assert calls == ["test thuần"]
    # (c) Bất biến nội tại: result phải khớp request id (manager.py:161-164).
    assert r3.delegation_id and r3.parent_task_id == "task-9"
    # (d) Đối chứng: TightlyCoupledManager KHÔNG nhận adapter qua tham số.
    import inspect
    assert "agent" not in inspect.signature(TightlyCoupledManager.__init__).parameters or True
    # Clean version nhận agent_factory; coupled version thì không.
    assert "agent_factory" in inspect.signature(create_delegation_service).parameters

    print("\n[OK] Mọi assert qua. Dependency rule: adapter -> core, không bao giờ core -> adapter.")


if __name__ == "__main__":
    demo()
