"""
CASE 02 — KernelSession + SessionIdentity: Aggregate cho ngữ cảnh thực thi 1 task.

Bản DISTILL trung thực, CHỈ dùng thư viện chuẩn Python 3.14, KHÔNG import hex_agent.

NGUỒN THẬT đã mở & kiểm chứng (path:line trong /Users/uspro/Desktop/namnson/hex_agent):
  - core/session.py:15-46    SessionIdentity — Value Object (frozen=True), danh tính bất biến
  - core/session.py:49-101   KernelSession — Aggregate Root (mutable, vòng đời 1 task):
        * 57       _closed: field(init=False, repr=False) — state riêng tư, đánh dấu đã đóng
        * 59-61    is_active — INVARIANT: chưa đóng VÀ current_task vẫn là TaskEnvelope
        * 63-73    call_context() — query dựng ngữ cảnh gọi tool
        * 75-85    execute_tool() — command, GÁC bằng is_active (đóng rồi thì từ chối)
        * 87-98    complete_task() — command: set current_task=None, _closed=True, PUBLISH event
        * 100-101  fail_task() — biến thể của complete_task với status="failed"
  - core/session.py:104-203  SessionFactory — Factory (nơi DUY NHẤT tạo session):
        * 110-117  _effective_root_scope() — validate capabilities yêu cầu ⊆ khả dụng
        * 119-146  create_root() — dựng identity + StateStore + publish 'task.accepted'
        * 148-186  create_child() — INVARIANT: scope con ⊆ scope cha (line 163-164)
        * 188-203  restore() — phục dựng aggregate từ checkpoint
  - core/state.py:8-28       StateStore — internal entity/data bag chỉ AR chạm tới

Trong code thật, KernelSession bọc StateStore + chia sẻ AgentKernel (LLM, registry, event bus).
Bản distill thay AgentKernel nặng bằng FakeKernel tối thiểu (registry tĩnh + event bus in-memory),
giữ NGUYÊN: danh tính bất biến, vòng đời _closed/is_active, publish event, factory chặn
construct sai, và bất biến "scope con ⊆ scope cha".

So với code thật: bỏ TaskEnvelope/ToolCallContext nhiều field, dùng dataclass tối giản; giữ đúng
vai trò pattern. TaskEnvelope thật ở core/schemas.py — ở đây thay bằng class Task gọn.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


# ── Value Object: danh tính bất biến (session.py:15-46) ───────────────────────────
@dataclass(frozen=True)
class SessionIdentity:
    """Danh tính của 1 session — frozen, không sửa được sau khi tạo (immutable identity)."""
    session_id: str
    run_id: str
    task_id: str
    agent_id: str
    parent_session_id: str | None = None
    depth: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id, "run_id": self.run_id, "task_id": self.task_id,
            "agent_id": self.agent_id, "parent_session_id": self.parent_session_id,
            "depth": self.depth,
        }


@dataclass
class Task:
    """Bản distill của TaskEnvelope (core/schemas.py) — chỉ giữ field cần cho demo."""
    user_request: str
    task_id: str
    context: dict[str, Any] = field(default_factory=dict)


# ── Internal entity / data bag: chỉ AR chạm tới (core/state.py:8-28) ──────────────
class StateStore:
    """Kho state in-memory của 1 session, KHÔNG được leak ra ngoài aggregate."""
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value


# ── Hạ tầng được thay bằng fake tối thiểu (code thật: AgentKernel) ────────────────
class FakeEventBus:
    """Event bus in-memory thay cho kernel.events thật (publish/append)."""
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish(self, event_type: str, fields: dict[str, Any]) -> None:
        self.published.append((event_type, dict(fields)))


class FakeKernel:
    """Thay AgentKernel: chỉ giữ registry tĩnh + event bus. execute_tool là stub."""
    def __init__(self, available_tools: list[str]) -> None:
        self._tools = list(available_tools)
        self.events = FakeEventBus()

    def list_tools(self) -> list[str]:
        return list(self._tools)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None,
                     context: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "capability": tool_name, "data": {"echo": args or {}},
                "metadata": dict(context)}


# ── AGGREGATE ROOT: KernelSession (session.py:49-101) ─────────────────────────────
@dataclass
class KernelSession:
    """Sở hữu state có thể thay đổi của MỘT task; dịch vụ chung nằm trên kernel.

    Consistency boundary: không thể mutate state của session khác; sau khi complete/fail
    (_closed=True) thì execute_tool bị từ chối (chống use-after-completion).
    """
    kernel: FakeKernel
    identity: SessionIdentity
    state: StateStore
    allowed_capabilities: frozenset[str]
    _closed: bool = field(default=False, init=False, repr=False)   # session.py:57

    @property
    def is_active(self) -> bool:
        # session.py:59-61 — INVARIANT: chưa đóng VÀ vẫn còn current_task
        return (not self._closed) and isinstance(self.state.get("current_task"), Task)

    def call_context(self) -> dict[str, Any]:
        # session.py:63-73 — dựng ngữ cảnh gọi tool từ identity (đã rút gọn)
        i = self.identity
        return {
            "run_id": i.run_id, "task_id": i.task_id, "session_id": i.session_id,
            "parent_session_id": i.parent_session_id, "actor_id": i.agent_id,
            "allowed_capabilities": sorted(self.allowed_capabilities),
        }

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        # session.py:75-85 — GÁC bằng is_active; đóng rồi thì trả lỗi, không ném
        if not self.is_active:
            return {"ok": False, "capability": tool_name, "error": "Session is not active.",
                    "metadata": {"session_closed": True}}
        if tool_name not in self.allowed_capabilities:
            return {"ok": False, "capability": tool_name,
                    "error": f"Capability {tool_name!r} ngoài scope của session."}
        return self.kernel.execute_tool(tool_name, args, context=self.call_context())

    def complete_task(self, result: Any = None, *, status: str = "completed") -> dict[str, Any]:
        # session.py:87-98 — đổi state ATOMIC + publish event ngay trong method
        if not self.is_active:
            raise RuntimeError("Session task lifecycle is already closed.")
        outcome = {"task_id": self.identity.task_id, "status": status, "result": result}
        self.state.set("last_result", outcome)
        self.state.set("current_task", None)
        self._closed = True
        self.kernel.events.publish(
            "task.completed" if status == "completed" else "task.failed",
            {**self.call_context(), "status": status},
        )
        return outcome

    def fail_task(self, reason: str, **extra: Any) -> dict[str, Any]:
        # session.py:100-101
        return self.complete_task({"reason": reason, **extra}, status="failed")


# ── FACTORY: nơi DUY NHẤT tạo session (session.py:104-203) ────────────────────────
class SessionFactory:
    """Constructor duy nhất cho root/child session; kernel không bao giờ tự tạo session."""

    def __init__(self, *, kernel: FakeKernel) -> None:
        self.kernel = kernel

    def _effective_root_scope(self, requested: frozenset[str] | None) -> frozenset[str]:
        # session.py:110-117 — validate scope yêu cầu ⊆ khả dụng
        available = frozenset(self.kernel.list_tools())
        if requested is None:
            return available
        if not requested <= available:
            unknown = sorted(requested - available)
            raise ValueError(f"Root session requested unknown capabilities: {unknown}")
        return requested

    def create_root(self, user_request: str, *,
                    allowed_capabilities: frozenset[str] | None = None) -> KernelSession:
        # session.py:119-146 — dựng identity + StateStore + publish 'task.accepted'
        task = Task(user_request=user_request, task_id=uuid.uuid4().hex)
        identity = SessionIdentity(session_id=uuid.uuid4().hex, run_id=task.task_id,
                                   task_id=task.task_id, agent_id="agent:root")
        scope = self._effective_root_scope(allowed_capabilities)
        state = StateStore()
        state.set("current_task", task)
        session = KernelSession(self.kernel, identity, state, scope)
        self.kernel.events.publish("task.accepted", session.call_context())
        return session

    def create_child(self, parent: KernelSession, *, target: str, user_request: str,
                     requested_scope: frozenset[str] | None = None) -> KernelSession:
        # session.py:148-186 — INVARIANT: scope con ⊆ scope cha
        if not parent.is_active:
            raise RuntimeError("Cannot create a child from an inactive parent session.")
        # None nghĩa là "kế thừa scope cha"; set rỗng tường minh nghĩa "từ chối tất cả".
        scope = parent.allowed_capabilities if requested_scope is None else requested_scope
        if not scope <= parent.allowed_capabilities:
            raise PermissionError("Child capability scope must be a subset of the parent scope.")
        task = Task(user_request=user_request, task_id=uuid.uuid4().hex)
        identity = SessionIdentity(
            session_id=uuid.uuid4().hex, run_id=parent.identity.run_id, task_id=task.task_id,
            agent_id=target, parent_session_id=parent.identity.session_id,
            depth=parent.identity.depth + 1,
        )
        state = StateStore()
        state.set("current_task", task)
        session = KernelSession(self.kernel, identity, state, frozenset(scope))
        self.kernel.events.publish("task.accepted", session.call_context())
        return session


# ── ĐỐI CHỨNG: tạo session "trần", bỏ qua factory ────────────────────────────────
def naive_make_session(kernel: FakeKernel, scope: set[str]) -> KernelSession:
    """Phản ví dụ: dựng session bằng tay, KHÔNG qua factory.

    Hậu quả: chẳng ai validate scope ⊆ khả dụng, chẳng ai set current_task,
    chẳng ai publish 'task.accepted'. Aggregate sinh ra ở trạng thái không hợp lệ.
    (Xem 35_Aggregate.md, anti-pattern 'Missing factory'.)
    """
    identity = SessionIdentity(session_id="x", run_id="x", task_id="x", agent_id="agent:rogue")
    return KernelSession(kernel, identity, StateStore(), frozenset(scope))


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — KernelSession aggregate (distill từ core/session.py)")
    print("=" * 72)

    kernel = FakeKernel(available_tools=["fs.read", "fs.write", "net.fetch"])
    factory = SessionFactory(kernel=kernel)

    # 1) Factory dựng root session đúng cách
    root = factory.create_root("Sửa bug login", allowed_capabilities=frozenset({"fs.read", "fs.write"}))
    print(f"[1] create_root -> session={root.identity.session_id[:8]}, "
          f"is_active={root.is_active}, scope={sorted(root.allowed_capabilities)}")
    assert root.is_active is True
    assert kernel.events.published[-1][0] == "task.accepted"

    # 2) SessionIdentity là VALUE OBJECT bất biến -> không gán lại được
    try:
        root.identity.session_id = "hacked"   # type: ignore[misc]
        raise AssertionError("Đáng lẽ frozen dataclass phải chặn gán lại")
    except Exception as e:  # FrozenInstanceError là con của Exception
        print(f"[2] SessionIdentity immutable đúng như mong đợi: {type(e).__name__}")

    # 3) execute_tool khi active -> OK; ngoài scope -> bị từ chối
    ok = root.execute_tool("fs.read", {"path": "a.py"})
    denied = root.execute_tool("net.fetch", {"url": "http://x"})
    print(f"[3] fs.read ok={ok['ok']}; net.fetch (ngoài scope) ok={denied['ok']} "
          f"-> error={denied['error']!r}")
    assert ok["ok"] is True and denied["ok"] is False

    # 4) Factory enforce INVARIANT: scope con ⊆ scope cha
    child = factory.create_child(root, target="agent:worker", user_request="đọc file",
                                 requested_scope=frozenset({"fs.read"}))
    print(f"[4] create_child OK: depth={child.identity.depth}, "
          f"parent={child.identity.parent_session_id[:8]}, scope={sorted(child.allowed_capabilities)}")
    assert child.identity.depth == 1
    try:
        factory.create_child(root, target="agent:bad", user_request="leo thang",
                             requested_scope=frozenset({"fs.read", "net.fetch"}))
        raise AssertionError("Đáng lẽ phải chặn vì net.fetch không có trong scope cha")
    except PermissionError as e:
        print(f"[4b] Chặn leo thang scope đúng như mong đợi: {e}")

    # 5) Factory chặn construct sai ngay từ đầu (scope yêu cầu không khả dụng)
    try:
        factory.create_root("xài tool lạ", allowed_capabilities=frozenset({"db.drop"}))
        raise AssertionError("Đáng lẽ phải chặn vì db.drop không khả dụng")
    except ValueError as e:
        print(f"[5] Factory chặn capability không khả dụng: {e}")

    # 6) complete_task: đổi state ATOMIC + publish event + khoá session
    events_before = len(kernel.events.published)
    outcome = root.complete_task(result={"fixed": True})
    print(f"[6] complete_task -> status={outcome['status']}, is_active={root.is_active}; "
          f"event mới publish: {kernel.events.published[-1][0]!r}")
    assert root.is_active is False
    assert kernel.events.published[-1][0] == "task.completed"
    assert len(kernel.events.published) == events_before + 1

    # 7) INVARIANT use-after-completion: đóng rồi thì execute_tool bị từ chối
    after = root.execute_tool("fs.read", {"path": "b.py"})
    print(f"[7] execute_tool sau khi đóng -> ok={after['ok']}, "
          f"session_closed={after['metadata']['session_closed']}")
    assert after["ok"] is False and after["metadata"]["session_closed"] is True

    # 8) complete_task lần 2 -> ném lỗi (không double-complete)
    try:
        root.complete_task()
        raise AssertionError("Đáng lẽ phải ném vì đã đóng")
    except RuntimeError as e:
        print(f"[8] Double-complete bị chặn đúng như mong đợi: {e}")

    # 9) StateStore là internal — child không thấy state của root
    assert child.state is not root.state
    print(f"[9] Mỗi session sở hữu StateStore riêng: child.state is root.state = "
          f"{child.state is root.state}")

    # 10) ĐỐI CHỨNG: session dựng tay bỏ qua factory -> không hợp lệ
    print("-" * 72)
    print("[10] ĐỐI CHỨNG: naive_make_session (bỏ qua factory)")
    rogue = naive_make_session(kernel, {"fs.read"})
    print(f"     is_active={rogue.is_active} (vì không ai set current_task) "
          f"-> aggregate sinh ra ở trạng thái KHÔNG hợp lệ, không có event 'task.accepted'")
    assert rogue.is_active is False

    print("=" * 72)
    print("PASS — danh tính bất biến, vòng đời gác chặt, factory enforce mọi invariant.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
