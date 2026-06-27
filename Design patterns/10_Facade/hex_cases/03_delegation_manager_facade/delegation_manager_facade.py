"""
Case 03 — DelegationManager Facade: policy + registry + sessions + store + events
sau một method duy nhất delegate().

NGUỒN THẬT (đã mở & kiểm chứng trong hex_agent):
  - delegation/manager.py:1       -> docstring: "Sequential delegation chokepoint: policy,
                                     child session, progress, events, result."
  - delegation/manager.py:19-32   -> __init__(registry, sessions, store, policy); freeze registry.
  - delegation/manager.py:34-35   -> available_targets().
  - delegation/manager.py:45-61   -> _finish(): store.finish + publish "delegation.finished".
  - delegation/manager.py:63-192  -> delegate(): điều phối tuần tự 6 subsystem với 3 nhánh lỗi:
        * validate input (70-75)
        * policy.validate (79-104)            -> nhánh lỗi: rejected
        * store.start + publish "started" (90-94, 105-117)
        * registry.resolve + sessions.create_child (119-140) -> nhánh lỗi: rejected/failed
        * progress_sink callback (142-157)    -> store.append_progress + publish "progress"
        * handler.run (159-185)               -> nhánh lỗi: failed
        * child.complete_task/fail_task + _finish (187-192)
  - delegation/policy.py          -> DelegationPolicyEngine.validate().
  - delegation/registry.py        -> DelegationRegistry.resolve()/targets()/freeze().
  - core/session.py               -> SessionFactory.create_child() (cô lập + scoping).
  - core/ports.py                 -> DelegationStorePort, DelegationPort.
  - core/schemas.py               -> DelegationSpec/Policy/Request/Result/Progress.

VAI TRÒ FACADE Ở ĐÂY:
  Facade        = DelegationManager.delegate() — 1 entrypoint cho cả workflow uỷ thác.
  Subsystem 1   = PolicyEngine.validate(): kiểm policy với parent session.
  Subsystem 2   = Registry.resolve(): map target string -> handler.
  Subsystem 3   = SessionFactory.create_child(): tạo child session scoping năng lực.
  Subsystem 4   = Handler.run(): chạy handler với progress_sink callback.
  Subsystem 5   = Store.start/append_progress/finish: nguồn-sự-thật tiến trình.
  Subsystem 6   = EventBus.publish: phát delegation.started/progress/finished.
  Client        = chỉ gọi manager.delegate(parent, target, spec); KHÔNG import
                  Policy/Registry/Store/EventBus.

Bản distill giữ NGUYÊN choreography 6 subsystem + 3 nhánh lỗi (policy reject,
tạo child fail, handler fail), giữ progress_sink là contract callback, và giữ
"store trước, event sau". Hạ tầng nặng được thay bằng fake stdlib.

Chỉ dùng thư viện chuẩn Python. KHÔNG import hex_agent, KHÔNG bên thứ ba.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable


# ──────────────────────────────────────────────────────────────────────────────
# SCHEMAS (core/schemas.py thật, rút gọn)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DelegationSpec:
    objective: str
    input_context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DelegationPolicy:
    allowed_capabilities: frozenset[str] = frozenset()
    max_steps: int = 4


@dataclass(frozen=True)
class DelegationRequest:
    delegation_id: str
    parent_task_id: str
    target: str
    spec: DelegationSpec
    policy: DelegationPolicy


@dataclass(frozen=True)
class DelegationProgress:
    delegation_id: str
    sequence: int
    status: str
    note: str = ""


@dataclass(frozen=True)
class DelegationResult:
    delegation_id: str
    parent_task_id: str
    outcome: str  # "success" | "rejected" | "failed"
    summary: str = ""
    error: str | None = None
    artifacts: tuple[str, ...] = ()


# ──────────────────────────────────────────────────────────────────────────────
# Kernel / Session (core/kernel.py, core/session.py thật, rút gọn)
# ──────────────────────────────────────────────────────────────────────────────


class EventBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, fields: dict) -> None:
        self.published.append((topic, fields))

    def topics(self) -> list[str]:
        return [t for t, _ in self.published]


class Kernel:
    def __init__(self) -> None:
        self.events = EventBus()


@dataclass
class SessionIdentity:
    session_id: str
    task_id: str
    agent_id: str


class KernelSession:
    def __init__(self, kernel: Kernel, identity: SessionIdentity, scope: frozenset[str]) -> None:
        self.kernel = kernel
        self.identity = identity
        self.scope = scope
        self.is_active = True
        self.state: dict = {}
        self.finished_with: str | None = None

    def complete_task(self, payload: dict) -> None:
        self.is_active = False
        self.finished_with = "success"

    def fail_task(self, reason: str) -> None:
        self.is_active = False
        self.finished_with = f"failed:{reason}"


class SessionFactory:
    """core.session.SessionFactory.create_child — child session scoping năng lực.

    LƯU Ý (giản lược đã công bố ở README §4): chữ ký thật
    (core/session.py:148-157) còn nhận `user_request: str` (bắt buộc) và
    `context: dict | None` (tuỳ chọn) để dựng TaskEnvelope cho child. Bản distill
    bỏ hai tham số này, chỉ giữ parent/delegation_id/target/requested_scope.
    Bất biến scoping (PermissionError khi child vượt scope cha) vẫn được giữ đúng.
    """

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    def create_child(
        self, parent: KernelSession, *, delegation_id: str, target: str, requested_scope: frozenset[str]
    ) -> KernelSession:
        # SCOPING: child KHÔNG được vượt năng lực của parent.
        if not requested_scope <= parent.scope:
            raise PermissionError(
                f"Child scope {set(requested_scope)} vượt scope parent {set(parent.scope)}."
            )
        ident = SessionIdentity(
            session_id=f"{parent.identity.session_id}.{delegation_id[:6]}",
            task_id=delegation_id,
            agent_id=target,
        )
        return KernelSession(self.kernel, ident, requested_scope)


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 1 — PolicyEngine (delegation/policy.py thật)
# ──────────────────────────────────────────────────────────────────────────────


class DelegationPolicyEngine:
    def validate(self, parent: KernelSession, requested: DelegationPolicy) -> DelegationPolicy:
        if not parent.is_active:
            raise RuntimeError("Parent session không active.")
        # Policy không được mở rộng năng lực ngoài scope parent.
        if not requested.allowed_capabilities <= parent.scope:
            raise PermissionError("Policy yêu cầu năng lực ngoài scope parent.")
        if requested.max_steps < 1:
            raise ValueError("max_steps phải >= 1.")
        return requested


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 2 — Registry + Handler (delegation/registry.py, core/ports.py thật)
# ──────────────────────────────────────────────────────────────────────────────


ProgressSink = Callable[[DelegationProgress], None]


class DelegationHandler:
    """DelegationPort.run — handler thực thi công việc uỷ thác."""

    def __init__(self, target: str, steps: int = 2, blow_up: bool = False) -> None:
        self.target = target
        self.steps = steps
        self.blow_up = blow_up

    def run(self, request: DelegationRequest, child: KernelSession, sink: ProgressSink) -> DelegationResult:
        for i in range(1, self.steps + 1):
            sink(DelegationProgress(request.delegation_id, sequence=i, status="working", note=f"step {i}"))
            if self.blow_up and i == self.steps:
                raise RuntimeError("Handler nổ giữa chừng.")
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            summary=f"{self.target} hoàn thành: {request.spec.objective}",
            artifacts=("artifact-A",),
        )


class DelegationRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, DelegationHandler] = {}
        self._frozen = False

    def register(self, handler: DelegationHandler) -> None:
        if self._frozen:
            raise RuntimeError("Registry đã đóng băng.")
        self._handlers[handler.target] = handler

    def freeze(self) -> None:
        self._frozen = True

    def targets(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def resolve(self, target: str) -> DelegationHandler:
        if target not in self._handlers:
            raise KeyError(f"Không có handler cho target {target!r}.")
        return self._handlers[target]


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 5 — Store (core/ports.DelegationStorePort thật)
# ──────────────────────────────────────────────────────────────────────────────


class InMemoryDelegationStore:
    def __init__(self) -> None:
        self.started: list[DelegationRequest] = []
        self.progress_log: list[DelegationProgress] = []
        self.finished: list[DelegationResult] = []

    def start(self, request: DelegationRequest) -> None:
        self.started.append(request)

    def append_progress(self, progress: DelegationProgress) -> None:
        self.progress_log.append(progress)

    def progress(self, delegation_id: str) -> list[DelegationProgress]:
        return [p for p in self.progress_log if p.delegation_id == delegation_id]

    def finish(self, result: DelegationResult) -> None:
        self.finished.append(result)


# ──────────────────────────────────────────────────────────────────────────────
# FACADE — DelegationManager.delegate() (delegation/manager.py:63 thật)
# ──────────────────────────────────────────────────────────────────────────────


class DelegationManager:
    """
    FACADE: delegate() là chokepoint tuần tự che 6 subsystem. (delegation/manager.py:19)
    """

    def __init__(
        self,
        *,
        registry: DelegationRegistry,
        sessions: SessionFactory,
        store: InMemoryDelegationStore,
        policy: DelegationPolicyEngine | None = None,
    ) -> None:
        self.registry = registry
        self.sessions = sessions
        self.store = store
        self.policy = policy or DelegationPolicyEngine()
        self.registry.freeze()

    def available_targets(self) -> tuple[str, ...]:
        return self.registry.targets()

    def _finish(self, parent: KernelSession, target: str, result: DelegationResult) -> DelegationResult:
        """delegation/manager.py:45 — store.finish trước, publish event sau."""
        self.store.finish(result)
        parent.kernel.events.publish(
            "delegation.finished",
            {"delegation_id": result.delegation_id, "target": target, "outcome": result.outcome},
        )
        return result

    def delegate(
        self,
        parent_session: KernelSession,
        target: str,
        spec: DelegationSpec,
        policy: DelegationPolicy | None = None,
    ) -> DelegationResult:
        """delegation/manager.py:63 — 1 entrypoint điều phối toàn bộ workflow."""
        if not parent_session.is_active:
            raise RuntimeError("Cannot delegate from an inactive parent session.")
        if not target:
            raise ValueError("Delegation target must not be empty.")
        if not spec.objective:
            raise ValueError("Delegation objective must not be empty.")

        delegation_id = uuid.uuid4().hex
        requested_policy = policy or DelegationPolicy()

        # ── Subsystem 1: policy (nhánh lỗi 1 = rejected) ──
        try:
            active_policy = self.policy.validate(parent_session, requested_policy)
        except Exception as exc:
            request = DelegationRequest(
                delegation_id, parent_session.identity.task_id, target, spec, requested_policy
            )
            self.store.start(request)
            parent_session.kernel.events.publish(
                "delegation.started", {"delegation_id": delegation_id, "target": target}
            )
            return self._finish(
                parent_session,
                target,
                DelegationResult(delegation_id, parent_session.identity.task_id, "rejected", error=str(exc)),
            )

        request = DelegationRequest(
            delegation_id, parent_session.identity.task_id, target, spec, active_policy
        )
        self.store.start(request)  # Subsystem 5
        parent_session.kernel.events.publish(  # Subsystem 6
            "delegation.started", {"delegation_id": delegation_id, "target": target}
        )

        # ── Subsystem 2 + 3: resolve handler & tạo child (nhánh lỗi 2) ──
        try:
            handler = self.registry.resolve(target)
            child = self.sessions.create_child(
                parent_session,
                delegation_id=delegation_id,
                target=target,
                requested_scope=active_policy.allowed_capabilities,
            )
        except Exception as exc:
            return self._finish(
                parent_session,
                target,
                DelegationResult(
                    delegation_id,
                    parent_session.identity.task_id,
                    "rejected" if isinstance(exc, PermissionError) else "failed",
                    error=str(exc),
                ),
            )

        # ── progress_sink: contract callback giữa facade và handler ──
        def progress_sink(progress: DelegationProgress) -> None:
            if progress.delegation_id != delegation_id:
                raise ValueError("Progress delegation_id không khớp request.")
            if progress.sequence > active_policy.max_steps:
                raise ValueError("Delegation progress vượt max_steps.")
            self.store.append_progress(progress)  # store là nguồn-sự-thật, ghi trước
            child.kernel.events.publish(  # event sau
                "delegation.progress",
                {"delegation_id": delegation_id, "sequence": progress.sequence, "status": progress.status},
            )

        # ── Subsystem 4: chạy handler (nhánh lỗi 3 = failed) ──
        try:
            result = handler.run(request, child, progress_sink)
            if result.delegation_id != delegation_id:
                raise ValueError("Result ID không khớp request.")
        except Exception as exc:
            result = DelegationResult(
                delegation_id,
                parent_session.identity.task_id,
                "failed",
                error=str(exc),
            )

        # ── đóng child & finish (store + event) ──
        if child.is_active:
            if result.outcome == "success":
                child.complete_task({"summary": result.summary})
            else:
                child.fail_task(result.error or result.outcome)
        return self._finish(parent_session, target, result)


# ──────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — client KHÔNG có facade phải tự dựng cả vũ điệu
# ──────────────────────────────────────────────────────────────────────────────


def delegate_without_facade(
    parent: KernelSession,
    registry: DelegationRegistry,
    sessions: SessionFactory,
    store: InMemoryDelegationStore,
    policy_engine: DelegationPolicyEngine,
    target: str,
    spec: DelegationSpec,
    requested_policy: DelegationPolicy,
) -> DelegationResult:
    """
    'Ngây thơ': client tự validate policy -> store.start -> publish -> resolve ->
    create_child -> tự viết progress_sink -> handler.run -> đóng child -> store.finish
    -> publish. 10+ bước, nhiều nhánh lỗi. Dễ quên 'store trước event sau', dễ quên
    đóng child, dễ lệch shape result giữa các client.
    """
    delegation_id = uuid.uuid4().hex
    active_policy = policy_engine.validate(parent, requested_policy)  # có thể ném
    request = DelegationRequest(delegation_id, parent.identity.task_id, target, spec, active_policy)
    store.start(request)
    parent.kernel.events.publish("delegation.started", {"delegation_id": delegation_id, "target": target})
    handler = registry.resolve(target)  # có thể ném
    child = sessions.create_child(
        parent, delegation_id=delegation_id, target=target, requested_scope=active_policy.allowed_capabilities
    )  # có thể ném

    def sink(p: DelegationProgress) -> None:
        store.append_progress(p)
        child.kernel.events.publish("delegation.progress", {"sequence": p.sequence})

    result = handler.run(request, child, sink)  # có thể ném
    child.complete_task({"summary": result.summary})
    store.finish(result)
    parent.kernel.events.publish("delegation.finished", {"delegation_id": delegation_id})
    return result


# ──────────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────────


def _make_world(blow_up: bool = False):
    kernel = Kernel()
    parent = KernelSession(
        kernel,
        SessionIdentity("sess-root", "task-root", "agent:root"),
        scope=frozenset({"read", "write", "search"}),
    )
    registry = DelegationRegistry()
    registry.register(DelegationHandler("agent:research", steps=2, blow_up=blow_up))
    sessions = SessionFactory(kernel)
    store = InMemoryDelegationStore()
    mgr = DelegationManager(registry=registry, sessions=sessions, store=store)
    return kernel, parent, mgr, store


def demo() -> None:
    print("=" * 72)
    print("CASE 03 — DelegationManager Facade (delegate())")
    print("=" * 72)

    print("\n[1] DÙNG FACADE: 1 lời gọi delegate() điều phối 6 subsystem.")
    kernel, parent, mgr, store = _make_world()
    spec = DelegationSpec(objective="Khảo sát thị trường")
    policy = DelegationPolicy(allowed_capabilities=frozenset({"read", "search"}), max_steps=4)
    result = mgr.delegate(parent, "agent:research", spec, policy)
    print("    outcome =", result.outcome, "| summary =", result.summary)
    print("    events  =", kernel.events.topics())
    assert result.outcome == "success"
    # Bất biến thứ tự event: started -> progress(x2) -> finished
    assert kernel.events.topics() == [
        "delegation.started",
        "delegation.progress",
        "delegation.progress",
        "delegation.finished",
    ]
    # Bất biến "store là nguồn-sự-thật": progress được ghi store đủ 2 bước
    assert len(store.progress(result.delegation_id)) == 2
    assert len(store.finished) == 1 and len(store.started) == 1
    print("    -> Client chỉ gọi delegate(); không import Policy/Registry/Store/EventBus.")

    print("\n[2] NHÁNH LỖI 1 — policy reject (vượt scope parent) -> outcome 'rejected'.")
    kernel2, parent2, mgr2, store2 = _make_world()
    bad_policy = DelegationPolicy(allowed_capabilities=frozenset({"admin"}), max_steps=4)
    r2 = mgr2.delegate(parent2, "agent:research", DelegationSpec("X"), bad_policy)
    print("    outcome =", r2.outcome, "| error =", r2.error)
    assert r2.outcome == "rejected"
    # Dù bị reject, facade VẪN ghi started + finished (audit trail nhất quán)
    assert kernel2.events.topics() == ["delegation.started", "delegation.finished"]
    assert len(store2.finished) == 1
    print("    -> Facade vẫn giữ audit trail (started+finished) khi reject.")

    print("\n[3] NHÁNH LỖI 2 — target không tồn tại -> outcome 'failed'.")
    kernel3, parent3, mgr3, store3 = _make_world()
    r3 = mgr3.delegate(parent3, "agent:unknown", DelegationSpec("Y"),
                       DelegationPolicy(frozenset({"read"})))
    print("    outcome =", r3.outcome, "| error =", r3.error)
    assert r3.outcome == "failed"
    assert len(store3.finished) == 1
    print("    -> Mọi nhánh lỗi đều quy về _finish(): client thấy 1 envelope nhất quán.")

    print("\n[4] NHÁNH LỖI 3 — handler nổ giữa chừng -> outcome 'failed', child fail_task.")
    kernel4, parent4, mgr4, store4 = _make_world(blow_up=True)
    r4 = mgr4.delegate(parent4, "agent:research", DelegationSpec("Z"),
                       DelegationPolicy(frozenset({"read"}), max_steps=4))
    print("    outcome =", r4.outcome, "| error =", r4.error)
    assert r4.outcome == "failed"
    assert "delegation.finished" in kernel4.events.topics()
    print("    -> Handler ném exception vẫn được facade bắt, đóng sổ sạch sẽ.")

    print("\n[5] ĐỐI CHỨNG: client tự dựng vũ điệu -> lỗi giữa chừng KHÔNG đóng sổ.")
    kernel5, parent5, mgr5, store5 = _make_world()
    reg5 = DelegationRegistry()
    reg5.register(DelegationHandler("agent:research", steps=2, blow_up=True))
    reg5.freeze()
    sf5 = SessionFactory(kernel5)
    try:
        delegate_without_facade(
            parent5, reg5, sf5, store5, DelegationPolicyEngine(),
            "agent:research", DelegationSpec("Z"), DelegationPolicy(frozenset({"read"}), max_steps=4),
        )
        raise AssertionError("đáng lẽ handler phải nổ")
    except RuntimeError as exc:
        print("    client tự xử bị ném:", exc)
    # Vì không có facade bọc try/except + _finish, store.finish KHÔNG được gọi:
    assert len(store5.finished) == 0, "thiếu facade => sổ kết quả bị bỏ dở"
    assert "delegation.finished" not in kernel5.events.topics()
    print("    -> Thiếu facade: started có, finished KHÔNG -> audit trail rò rỉ, child treo.")

    print("\nTẤT CẢ ASSERT QUA. delegate() là facade gói trọn 6 subsystem + 3 nhánh lỗi.")


if __name__ == "__main__":
    demo()
