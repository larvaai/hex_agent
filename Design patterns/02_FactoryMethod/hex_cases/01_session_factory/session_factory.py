"""
Case 01 — SessionFactory.create_root / create_child (Factory Method).

DISTILL TRUNG THỰC TỪ MÃ THẬT:
  - core/session.py:104-186  (class SessionFactory; create_root 119-146; create_child 148-186)
  - core/session.py:188-203  (SessionFactory.restore — factory method thứ 3)
  - core/session.py:49-101   (KernelSession — sản phẩm được tạo)
  - tests/test_lifecycle.py:12  (SessionFactory(kernel=k).create_root("x"))
  - tests/test_delegation.py:46 (parent = ...create_root(...); rồi create_child)

Ở hex_agent, AgentKernel KHÔNG bao giờ tự tạo session. Mọi session đều phải đi
qua SessionFactory — đây là "the only constructor for root/child sessions"
(docstring thật ở core/session.py:105). Factory có nhiều phương thức tạo:
  * create_root   — phiên gốc cho 1 user request (validate phạm vi capability).
  * create_child  — phiên con khi uỷ thác (delegation), phạm vi PHẢI là tập con
                    của cha (scope subsetting).
  * restore       — dựng lại phiên từ trạng thái đã lưu.

Bản distill này chỉ dùng thư viện chuẩn. Hạ tầng nặng được thay bằng fake:
  - AgentKernel thật  -> FakeKernel (chỉ giữ danh sách capability + log event).
  - StateStore thật   -> dict thường.
  - uuid thật         -> uuid.uuid4().hex (stdlib, giữ nguyên).

Trọng tâm dạy học: vì sao Factory Method tốt hơn việc rải if-else "tạo loại
session nào" trong code gọi (client). Khách hàng chỉ gọi factory.create_*,
không cần biết cách dựng SessionIdentity / validate scope / phát event.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Hạ tầng fake tối thiểu (thay cho AgentKernel + StateStore thật)
# ─────────────────────────────────────────────────────────────────────────────
class FakeKernel:
    """Đứng thay AgentKernel: chỉ giữ tập capability khả dụng và log event.

    Trong mã thật (core/kernel.py) kernel có registry, event bus, middleware...
    Ở đây ta rút gọn còn đúng phần factory cần: liệt kê capability + publish event.
    """

    def __init__(self, capabilities: frozenset[str]) -> None:
        self._capabilities = frozenset(capabilities)
        self.events: list[tuple[str, dict]] = []
        self.frozen = False

    def list_capabilities(self) -> frozenset[str]:
        return self._capabilities

    def freeze(self) -> None:
        # Mã thật gọi kernel.freeze() để khoá cấu hình trước khi chạy.
        self.frozen = True

    def publish(self, topic: str, payload: dict) -> None:
        self.events.append((topic, payload))


# ─────────────────────────────────────────────────────────────────────────────
# Product (sản phẩm) — tương ứng KernelSession ở core/session.py:49-101
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SessionIdentity:
    """Distill từ SessionIdentity (core/session.py:15-46)."""

    session_id: str
    run_id: str
    task_id: str
    agent_id: str
    parent_session_id: str | None = None
    delegation_id: str | None = None
    depth: int = 0


@dataclass
class KernelSession:
    """Sản phẩm do SessionFactory tạo. Distill từ KernelSession (core/session.py:49)."""

    kernel: FakeKernel
    identity: SessionIdentity
    state: dict
    allowed_capabilities: frozenset[str]
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def is_active(self) -> bool:
        return not self._closed and self.state.get("current_task") is not None

    def close(self) -> None:
        self._closed = True


# ─────────────────────────────────────────────────────────────────────────────
# Creator (factory) — distill từ SessionFactory (core/session.py:104-203)
# ─────────────────────────────────────────────────────────────────────────────
class SessionFactory:
    """The only constructor for root/child sessions; kernel never creates sessions.

    Đây là Creator. Nó đóng gói TOÀN BỘ quyết định "tạo phiên loại nào và dựng
    ra sao". Mỗi phương thức create_* là một biến thể tạo (template tạo) khác nhau.
    """

    def __init__(self, *, kernel: FakeKernel) -> None:
        self.kernel = kernel

    # core/session.py:110-117 — validate phạm vi capability cho phiên gốc
    def _effective_root_scope(self, requested: frozenset[str] | None) -> frozenset[str]:
        available = self.kernel.list_capabilities()
        if requested is None:
            return available
        if not requested <= available:
            unknown = sorted(requested - available)
            raise ValueError(f"Root session requested unknown capabilities: {unknown}")
        return requested

    # ── Factory method #1: create_root (core/session.py:119-146) ──────────────
    def create_root(
        self,
        user_request: str,
        *,
        allowed_capabilities: frozenset[str] | None = None,
    ) -> KernelSession:
        # Template tạo: (1) cấp task_id, (2) cấp identity, (3) validate scope,
        # (4) freeze kernel, (5) dựng state, (6) dựng session, (7) phát event.
        task_id = uuid.uuid4().hex
        identity = SessionIdentity(
            session_id=uuid.uuid4().hex,
            run_id=task_id,
            task_id=task_id,
            agent_id="agent:root",
        )
        scope = self._effective_root_scope(allowed_capabilities)
        self.kernel.freeze()
        state = {"current_task": {"user_request": user_request}}
        session = KernelSession(self.kernel, identity, state, scope)
        self.kernel.publish("task.accepted", {"session_id": identity.session_id, "kind": "root"})
        return session

    # ── Factory method #2: create_child (core/session.py:148-186) ─────────────
    def create_child(
        self,
        parent: KernelSession,
        *,
        delegation_id: str,
        target: str,
        user_request: str,
        requested_scope: frozenset[str] | None = None,
    ) -> KernelSession:
        if not parent.is_active:
            raise RuntimeError("Cannot create a child from an inactive parent session.")
        # None = "kế thừa scope cha"; set rỗng = "cấm tất". (core/session.py:160-164)
        scope = parent.allowed_capabilities if requested_scope is None else requested_scope
        if not scope <= parent.allowed_capabilities:
            raise PermissionError("Child capability scope must be a subset of the parent scope.")
        identity = SessionIdentity(
            session_id=uuid.uuid4().hex,
            run_id=parent.identity.run_id,           # con dùng chung run_id với cha
            task_id=uuid.uuid4().hex,
            agent_id=target,
            parent_session_id=parent.identity.session_id,
            delegation_id=delegation_id,
            depth=parent.identity.depth + 1,
        )
        state = {"current_task": {"user_request": user_request}}
        session = KernelSession(self.kernel, identity, state, frozenset(scope))
        self.kernel.publish("task.accepted", {"session_id": identity.session_id, "kind": "child"})
        return session

    # ── Factory method #3: restore (core/session.py:188-203) ──────────────────
    def restore(
        self,
        *,
        identity: SessionIdentity,
        state: dict,
        allowed_capabilities: frozenset[str],
    ) -> KernelSession:
        self.kernel.freeze()
        if not allowed_capabilities <= self._effective_root_scope(None):
            raise ValueError("Persisted session contains capabilities unavailable in this runtime.")
        session = KernelSession(self.kernel, identity, dict(state), allowed_capabilities)
        if state.get("current_task") is None:
            session.close()
        return session


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG: khi KHÔNG dùng Factory Method (rải if-else ở client)
# ─────────────────────────────────────────────────────────────────────────────
def make_session_the_bad_way(kernel: FakeKernel, kind: str, *, parent=None):
    """Anti-pattern: client tự quyết định loại session và tự dựng từng bước.

    Mỗi chỗ trong code base cần tạo session sẽ phải lặp lại đoạn if-else này.
    Thêm một loại session mới (vd 'resumable') = sửa MỌI chỗ có if-else như vầy.
    Và rất dễ quên một bước (freeze, validate scope, publish event...).
    """
    if kind == "root":
        tid = uuid.uuid4().hex
        ident = SessionIdentity(session_id=uuid.uuid4().hex, run_id=tid, task_id=tid, agent_id="agent:root")
        # QUÊN freeze, QUÊN validate scope, QUÊN publish event -> bug ngầm.
        return KernelSession(kernel, ident, {"current_task": {"user_request": "x"}}, kernel.list_capabilities())
    elif kind == "child":
        tid = uuid.uuid4().hex
        ident = SessionIdentity(
            session_id=uuid.uuid4().hex, run_id=parent.identity.run_id, task_id=tid,
            agent_id="agent:child", parent_session_id=parent.identity.session_id, depth=parent.identity.depth + 1,
        )
        # Ở đây KHÔNG ai kiểm tra "scope con phải là tập con của cha" -> lỗ hổng bảo mật.
        return KernelSession(kernel, ident, {"current_task": {"user_request": "y"}}, parent.allowed_capabilities)
    else:
        raise ValueError(f"unknown kind {kind!r}")


# ─────────────────────────────────────────────────────────────────────────────
# MỞ RỘNG: thêm loại "resumable" CHỈ bằng cách thêm 1 factory method mới
# ─────────────────────────────────────────────────────────────────────────────
class SessionFactoryWithResume(SessionFactory):
    """Open-Closed: thêm biến thể tạo mới, không đụng client cũng không đụng create_root/child."""

    def create_resumable(self, snapshot: dict) -> KernelSession:
        identity = SessionIdentity(
            session_id=uuid.uuid4().hex,
            run_id=snapshot["run_id"],
            task_id=uuid.uuid4().hex,
            agent_id=snapshot.get("agent_id", "agent:root"),
        )
        self.kernel.freeze()
        state = {"current_task": {"user_request": snapshot["user_request"]}, "resumed": True}
        session = KernelSession(self.kernel, identity, state, self._effective_root_scope(None))
        self.kernel.publish("task.accepted", {"session_id": identity.session_id, "kind": "resumable"})
        return session


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — SessionFactory.create_root / create_child (Factory Method)")
    print("Nguồn thật: core/session.py:104-203")
    print("=" * 72)

    kernel = FakeKernel(capabilities=frozenset({"fs_read", "fs_write", "net_get"}))
    factory = SessionFactory(kernel=kernel)

    print("\n[1] Client chỉ gọi factory.create_root(...) — KHÔNG cần biết cách dựng.")
    root = factory.create_root("Sửa lỗi build", allowed_capabilities=frozenset({"fs_read", "fs_write"}))
    print(f"    root.session_id = {root.identity.session_id[:8]}...  scope = {sorted(root.allowed_capabilities)}")
    print(f"    is_active = {root.is_active}  (kernel.frozen = {kernel.frozen})")
    assert root.is_active
    assert kernel.frozen, "create_root phải freeze kernel — bước này nằm trong factory, client khỏi lo"

    print("\n[2] create_child: phạm vi con PHẢI là tập con của cha (scope subsetting).")
    child = factory.create_child(
        root, delegation_id="d1", target="agent:tester",
        requested_scope=frozenset({"fs_read"}), user_request="Chạy test",
    )
    print(f"    child.parent = {child.identity.parent_session_id[:8]}...  depth = {child.identity.depth}")
    print(f"    child.scope = {sorted(child.allowed_capabilities)}  (run_id dùng chung cha: "
          f"{child.identity.run_id == root.identity.run_id})")
    assert child.allowed_capabilities <= root.allowed_capabilities
    assert child.identity.run_id == root.identity.run_id
    assert child.identity.depth == root.identity.depth + 1

    print("\n[3] Factory chặn nâng quyền: con xin quyền cha KHÔNG có -> PermissionError.")
    try:
        factory.create_child(
            root, delegation_id="d2", target="agent:x",
            requested_scope=frozenset({"net_get"}),  # cha chỉ có fs_read/fs_write
            user_request="Tải mạng",
        )
        raise AssertionError("Đáng lẽ phải chặn nâng quyền!")
    except PermissionError as e:
        print(f"    Bị chặn đúng như mong đợi: {e}")

    print("\n[4] restore: dựng lại phiên đã đóng từ state đã lưu.")
    saved_state = {"current_task": None}  # task đã xong -> phiên phải ở trạng thái closed
    restored = factory.restore(
        identity=root.identity, state=saved_state,
        allowed_capabilities=frozenset({"fs_read"}),
    )
    print(f"    restored.is_active = {restored.is_active}  (task=None -> closed)")
    assert not restored.is_active

    print("\n[5] ĐỐI CHỨNG — không dùng factory, client tự dựng (anti-pattern):")
    kernel2 = FakeKernel(capabilities=frozenset({"fs_read", "fs_write", "net_get"}))
    bad_root = make_session_the_bad_way(kernel2, "root")
    print(f"    kernel.frozen sau khi tạo 'bằng tay' = {kernel2.frozen}  (QUÊN freeze!)")
    print(f"    events phát ra = {kernel2.events}  (QUÊN publish 'task.accepted'!)")
    bad_child = make_session_the_bad_way(kernel2, "child", parent=bad_root)
    # Đặt cho con scope rộng hơn cha một cách lén lút — không ai chặn.
    bad_child.allowed_capabilities = frozenset({"fs_read", "fs_write", "net_get", "DANGER"})
    print(f"    con tự ý có quyền 'DANGER' không nằm trong cha = "
          f"{'DANGER' in bad_child.allowed_capabilities}  (LỖ HỔNG bảo mật!)")
    assert not kernel2.frozen and kernel2.events == [], "đúng là anti-pattern quên các bước"

    print("\n[6] MỞ RỘNG (Open-Closed): thêm create_resumable mà KHÔNG sửa code cũ.")
    factory3 = SessionFactoryWithResume(kernel=FakeKernel(frozenset({"fs_read"})))
    resumed = factory3.create_resumable({"run_id": "r-99", "user_request": "Tiếp tục"})
    print(f"    resumed.run_id = {resumed.identity.run_id}  state.resumed = {resumed.state.get('resumed')}")
    # create_root/create_child cũ vẫn dùng được nguyên vẹn:
    assert factory3.create_root("vẫn ok").is_active
    print("    -> create_root cũ vẫn chạy bình thường: KHÔNG có regression.")

    print("\nKẾT LUẬN: Mọi quyết định 'tạo loại session nào + dựng ra sao' được dồn vào")
    print("SessionFactory. Client chỉ gọi tên phương thức; bất biến (freeze, event,")
    print("scope-subset) được bảo đảm ở MỘT chỗ. Thêm loại mới = thêm 1 method.")
    print("\nTẤT CẢ ASSERT ĐỀU PASS.")


if __name__ == "__main__":
    demo()
