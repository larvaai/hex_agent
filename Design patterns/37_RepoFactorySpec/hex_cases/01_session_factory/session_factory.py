"""
Case 01 — SessionFactory: Factory DDD đa-path (create vs restore) + Repository state.

DISTILL TRUNG THỰC từ codebase hex_agent:
  - core/session.py:104-203   SessionFactory.create_root / create_child / restore
  - core/session.py:49-101    KernelSession (aggregate root: is_active, complete_task)
  - core/session.py:15-46     SessionIdentity (value object, frozen, as_dict/from_dict)
  - core/state.py:8-27        StateStore.snapshot/restore (repository in-memory session-scoped)

Bài học gốc văn phong: Design patterns/37_RepoFactorySpec/37_RepoFactorySpec.md

Trong file này KHÔNG import gì từ hex_agent và KHÔNG dùng thư viện bên thứ ba.
Hạ tầng nặng được thay bằng fake tối thiểu bằng stdlib:
  - AgentKernel thật (registry động + event bus + freeze) -> FakeKernel tối thiểu.
  - uuid thật -> dùng itertools.count cho ID xác định, dễ assert.

Trọng tâm distill (đúng vai trò pattern, đổi tên cho dễ đọc):
  * Factory 2 path:
      create_root  = aggregate MỚI  -> enforce invariant, sinh ID, freeze deps, PUBLISH event.
      restore      = rebuild từ STATE đã persist -> TRUST state, KHÔNG re-check, KHÔNG emit.
  * Business rule ở factory: create_child ép scope con phải là SUBSET scope cha.
  * Repository session-scoped: StateStore.snapshot() (detached copy) + restore() (replace wholesale).
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Hạ tầng FAKE tối thiểu (thay AgentKernel + event bus + uuid trong code thật)
# ─────────────────────────────────────────────────────────────────────────────

_ID = itertools.count(1)


def _next_id(prefix: str) -> str:
    """Thay uuid.uuid4().hex (core/session.py:132,138,174...) bằng ID xác định để assert."""
    return f"{prefix}-{next(_ID)}"


class FakeKernel:
    """Bản rút gọn của AgentKernel: chỉ giữ những gì factory thật chạm tới.

    Code thật: kernel.registry.list_tools(), kernel.freeze(), kernel.events.publish(...).
    """

    def __init__(self, capabilities: set[str]) -> None:
        self._capabilities = set(capabilities)
        self._frozen = False
        self.published: list[tuple[str, dict[str, Any]]] = []  # nhật ký event để assert

    def list_capabilities(self) -> frozenset[str]:
        # Tương đương frozenset(item["name"] for item in kernel.registry.list_tools())
        return frozenset(self._capabilities)

    def freeze(self) -> None:
        # Sau khi tạo session, registry bị khoá (không thêm/bớt capability nữa).
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, dict(payload)))


# ─────────────────────────────────────────────────────────────────────────────
# Repository session-scoped — distill core/state.py:8-27 (StateStore)
# ─────────────────────────────────────────────────────────────────────────────

class StateStore:
    """Repository in-memory, collection-like API, session-scoped.

    snapshot() = detached deepcopy (an toàn để seed checkpoint khác).
    restore()  = thay toàn bộ state (dùng khi resume).
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def restore(self, data: dict[str, Any]) -> None:
        self._data = copy.deepcopy(data)


# ─────────────────────────────────────────────────────────────────────────────
# Value object + Aggregate Root — distill SessionIdentity + KernelSession
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SessionIdentity:
    """Value object bất biến (core/session.py:15-46)."""

    session_id: str
    run_id: str
    task_id: str
    agent_id: str
    parent_session_id: str | None = None
    depth: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "parent_session_id": self.parent_session_id,
            "depth": self.depth,
        }


@dataclass
class KernelSession:
    """Aggregate Root: sở hữu state của 1 task; service chia sẻ nằm trên kernel.

    Distill core/session.py:49-101. Factory là constructor DUY NHẤT; không ai
    khác được dựng KernelSession trực tiếp (kernel không tự tạo session).
    """

    kernel: FakeKernel
    identity: SessionIdentity
    state: StateStore
    allowed_capabilities: frozenset[str]
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def is_active(self) -> bool:
        # Code thật kiểm isinstance(current_task, TaskEnvelope); ở đây "current_task" là dict.
        return not self._closed and self.state.get("current_task") is not None

    def complete_task(self, result: Any = None, *, status: str = "completed") -> dict[str, Any]:
        if not self.is_active:
            raise RuntimeError("Session task lifecycle is already closed.")
        outcome = {"task_id": self.identity.task_id, "status": status, "result": result}
        self.state.set("last_result", outcome)
        self.state.set("current_task", None)
        self._closed = True
        self.kernel.publish(
            "task.completed" if status == "completed" else "task.failed",
            {"task_id": self.identity.task_id, "status": status},
        )
        return outcome


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY — distill core/session.py:104-203 (SessionFactory)
# ─────────────────────────────────────────────────────────────────────────────

class SessionFactory:
    """Constructor duy nhất cho root/child session; là nơi enforce invariant.

    Hai path khác nhau hoàn toàn:
      create_root / create_child : aggregate MỚI -> validate, sinh ID, freeze, PUBLISH event.
      restore                    : rebuild từ STATE đã persist -> TRUST, KHÔNG re-check, KHÔNG emit.
    """

    def __init__(self, *, kernel: FakeKernel) -> None:
        self.kernel = kernel

    # core/session.py:110-117
    def _effective_root_scope(self, requested: frozenset[str] | None) -> frozenset[str]:
        available = self.kernel.list_capabilities()
        if requested is None:
            return available
        if not requested <= available:
            unknown = sorted(requested - available)
            raise ValueError(f"Root session requested unknown capabilities: {unknown}")
        return requested

    # core/session.py:119-146 — PATH CREATE (root)
    def create_root(
        self,
        user_request: str,
        *,
        allowed_capabilities: frozenset[str] | None = None,
    ) -> KernelSession:
        task_id = _next_id("task")
        # 1) enforce invariant: scope yêu cầu phải nằm trong registry hiện có
        scope = self._effective_root_scope(allowed_capabilities)
        identity = SessionIdentity(
            session_id=_next_id("sess"),
            run_id=task_id,                 # run_id = task_id cho root
            task_id=task_id,
            agent_id="agent:root",
        )
        # 2) freeze deps (khoá registry trước khi session chạy)
        self.kernel.freeze()
        # 3) state khởi tạo có current_task -> session is_active
        state = StateStore()
        state.set("current_task", {"user_request": user_request})
        session = KernelSession(self.kernel, identity, state, scope)
        # 4) PUBLISH event chỉ khi TẠO MỚI
        self.kernel.publish("task.accepted", {"session_id": identity.session_id})
        return session

    # core/session.py:148-186 — PATH CREATE (child) + business rule scope subset
    def create_child(
        self,
        parent: KernelSession,
        *,
        user_request: str,
        requested_scope: frozenset[str] | None = None,
    ) -> KernelSession:
        if not parent.is_active:
            raise RuntimeError("Cannot create a child from an inactive parent session.")
        # None = "kế thừa scope cha"; empty set rỗng = "deny all" (KHÁC None!).
        scope = parent.allowed_capabilities if requested_scope is None else requested_scope
        # BUSINESS RULE ở factory: scope con phải là SUBSET scope cha.
        if not scope <= parent.allowed_capabilities:
            raise PermissionError("Child capability scope must be a subset of the parent scope.")
        identity = SessionIdentity(
            session_id=_next_id("sess"),
            run_id=parent.identity.run_id,          # con chia sẻ run_id với cha
            task_id=_next_id("task"),
            agent_id="agent:child",
            parent_session_id=parent.identity.session_id,
            depth=parent.identity.depth + 1,
        )
        state = StateStore()
        state.set("current_task", {"user_request": user_request})
        session = KernelSession(self.kernel, identity, state, frozenset(scope))
        self.kernel.publish("task.accepted", {"session_id": identity.session_id})
        return session

    # core/session.py:188-203 — PATH RESTORE (reconstitute)
    def restore(
        self,
        *,
        identity: SessionIdentity,
        state: dict[str, Any],
        allowed_capabilities: frozenset[str],
    ) -> KernelSession:
        self.kernel.freeze()
        # Kiểm an toàn nhẹ: state đã persist không được chứa capability runtime không có.
        if not allowed_capabilities <= self._effective_root_scope(None):
            raise ValueError("Persisted session contains capabilities unavailable in this runtime.")
        store = StateStore()
        store.restore(state)                # TRUST state — KHÔNG re-validate invariant
        session = KernelSession(self.kernel, identity, store, allowed_capabilities)
        # current_task đã None (task xong) -> session khôi phục ở trạng thái closed.
        if store.get("current_task") is None:
            session._closed = True
        # CHÚ Ý: KHÔNG publish "task.accepted" ở đây.
        return session


# ─────────────────────────────────────────────────────────────────────────────
# Đối chứng: factory NGÂY THƠ re-chạy invariant khi restore -> hỏng khi resume
# ─────────────────────────────────────────────────────────────────────────────

def naive_restore_rerunning_create(factory: SessionFactory, snapshot_state: dict[str, Any]) -> KernelSession:
    """ANTI-PATTERN: "restore" bằng cách gọi lại path create.

    Hậu quả giống vi phạm B trong bài gốc:
      - publish lại "task.accepted" mỗi lần load (event giả).
      - mất state đã persist (current_task=None) vì create luôn set task mới -> is_active=True.
    """
    # Cố ý đi sai: dựng "mới" thay vì trust state.
    return factory.create_root(snapshot_state.get("current_task") or "resumed-task")


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────

def demo() -> None:
    print("=" * 70)
    print("CASE 01 — SessionFactory: Factory DDD 2 path (create vs restore)")
    print("=" * 70)

    kernel = FakeKernel(capabilities={"fs.read", "fs.write", "net.http"})
    factory = SessionFactory(kernel=kernel)

    # ---- PATH CREATE (root) -------------------------------------------------
    print("\n[1] create_root: tạo aggregate MỚI")
    root = factory.create_root("build report", allowed_capabilities=frozenset({"fs.read", "fs.write"}))
    print(f"    -> session_id={root.identity.session_id}, is_active={root.is_active}")
    print(f"    -> kernel.is_frozen={kernel.is_frozen} (deps đã khoá)")
    print(f"    -> events sau create: {[t for t, _ in kernel.published]}")
    assert root.is_active, "session mới phải active"
    assert kernel.is_frozen, "create phải freeze registry"
    assert kernel.published[-1][0] == "task.accepted", "create phải publish task.accepted"
    n_events_after_create = len(kernel.published)

    # ---- BUSINESS RULE: child scope phải subset của parent --------------------
    print("\n[2] create_child: scope con BUỘC là subset scope cha")
    child_ok = factory.create_child(root, user_request="sub task", requested_scope=frozenset({"fs.read"}))
    print(f"    -> child hợp lệ: scope={set(child_ok.allowed_capabilities)}, depth={child_ok.identity.depth}")
    print(f"    -> child chia sẻ run_id với cha: {child_ok.identity.run_id == root.identity.run_id}")
    assert child_ok.allowed_capabilities <= root.allowed_capabilities
    assert child_ok.identity.run_id == root.identity.run_id

    print("    -> thử leo thang quyền: child xin 'net.http' (cha không có) ...")
    try:
        factory.create_child(root, user_request="evil", requested_scope=frozenset({"net.http"}))
        raise AssertionError("Phải chặn child vượt scope cha")
    except PermissionError as e:
        print(f"       ĐÚNG, bị chặn: {e}")

    # ---- empty set KHÁC None -------------------------------------------------
    print("\n[3] requested_scope=frozenset() (deny all) KHÁC None (inherit)")
    child_locked = factory.create_child(root, user_request="locked", requested_scope=frozenset())
    print(f"    -> deny-all child scope={set(child_locked.allowed_capabilities)} (rỗng, không bị widen)")
    assert child_locked.allowed_capabilities == frozenset()

    # ---- snapshot bằng Repository (StateStore) -------------------------------
    print("\n[4] Hoàn tất task -> snapshot state qua repository (StateStore)")
    root.complete_task(result={"report": "done.pdf"})
    snap = root.state.snapshot()                      # detached deepcopy
    print(f"    -> snapshot keys={sorted(snap.keys())}, current_task={snap['current_task']}")
    print(f"    -> events sau complete: {[t for t, _ in kernel.published]}")
    assert snap["current_task"] is None, "task đã xong -> current_task None trong snapshot"

    # ---- PATH RESTORE (reconstitute) ----------------------------------------
    print("\n[5] restore: rebuild từ STATE đã persist (TRUST, không re-check, không emit)")
    events_before_restore = len(kernel.published)
    restored = factory.restore(
        identity=root.identity,
        state=snap,
        allowed_capabilities=root.allowed_capabilities,
    )
    events_after_restore = len(kernel.published)
    print(f"    -> restored._closed={restored._closed} (đúng vì task đã xong)")
    print(f"    -> số event TĂNG khi restore: {events_after_restore - events_before_restore}")
    print(f"    -> last_result giữ nguyên: {restored.state.get('last_result')}")
    assert restored._closed, "restore phải tôn trọng state đã persist (closed)"
    assert events_after_restore == events_before_restore, "restore KHÔNG được publish event"
    assert restored.state.get("last_result") == {"task_id": root.identity.task_id,
                                                 "status": "completed",
                                                 "result": {"report": "done.pdf"}}

    # ---- ĐỐI CHỨNG: restore ngây thơ bằng create -> hỏng --------------------
    print("\n[6] ĐỐI CHỨNG — 'restore' sai cách bằng cách gọi lại create()")
    events_before_bad = len(kernel.published)
    bad = naive_restore_rerunning_create(factory, snap)
    events_after_bad = len(kernel.published)
    print(f"    -> bad.is_active={bad.is_active} (SAI: task đã xong mà lại active)")
    print(f"    -> publish thừa {events_after_bad - events_before_bad} event 'task.accepted' (event giả)")
    assert bad.is_active is True, "minh hoạ: create làm sống lại task đã chết"
    assert events_after_bad > events_before_bad, "minh hoạ: create emit event thừa khi 'load'"
    print("    => Đây chính là vi phạm B trong bài gốc: reconstitute không được re-run create.")

    print("\n[OK] Mọi assert pass. Factory 2 path + Repository state hoạt động đúng.")


if __name__ == "__main__":
    demo()
