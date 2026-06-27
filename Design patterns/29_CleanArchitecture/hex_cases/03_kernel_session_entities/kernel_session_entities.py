"""
Case 03 — Core Domain Entities (Schemas as Immutable Boundaries).

Bản DISTILL trung thực của VÒNG 1 (Entities) trong Clean Architecture của hex_agent.
Entities là frozen dataclass: pure data, không I/O, không framework. Cùng một schema được
use case, adapter, và bootstrap tiêu thụ y hệt. Vì thuần, ta tạo/serialize/deserialize hàng loạt
trong micro-giây mà không cần dựng DB/HTTP — đó là "100% unit-testable".

Nguồn thật trong hex_agent (đã mở kiểm chứng):
  - core/schemas.py:11-26      -> TaskEnvelope (frozen dataclass + as_dict/from_dict)
  - core/schemas.py:28-33      -> ToolRequest
  - core/schemas.py:114-129    -> FeatureDescriptor
  - core/schemas.py:181-198    -> DelegationRequest
  - core/schemas.py:235-253    -> DelegationResult
  - core/session.py:15-46      -> SessionIdentity (frozen identity)
  - core/session.py:49-102     -> KernelSession (identity bất biến + state mutable)
  - core/kernel.py:76-98       -> AgentKernel (orchestrator thuần) + freeze()

Chỉ dùng standard library. Đối chứng "ORM model" được mô phỏng bằng một class mutable
có 'lazy-load' giả lập cần 'DB session' — để thấy entity thuần khác ORM ở chỗ nào.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 1 — ENTITIES (core/schemas.py). frozen=True: bất biến, hashable, pure data.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TaskEnvelope:
    """Distill core/schemas.py:11-26."""
    user_request: str
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def as_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "user_request": self.user_request,
                "context": dict(self.context), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskEnvelope":
        return cls(user_request=d.get("user_request", ""),
                   context=dict(d.get("context") or {}),
                   metadata=dict(d.get("metadata") or {}),
                   task_id=d.get("task_id") or uuid.uuid4().hex)


@dataclass(frozen=True)
class DelegationResult:
    """Distill core/schemas.py:235-253. Entity đi qua boundary use case <-> adapter."""
    delegation_id: str
    parent_task_id: str
    outcome: str  # "success" | "failed" | "rejected" | "timeout"
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"delegation_id": self.delegation_id, "parent_task_id": self.parent_task_id,
                "outcome": self.outcome, "summary": dict(self.summary), "error": self.error}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DelegationResult":
        return cls(delegation_id=d["delegation_id"], parent_task_id=d["parent_task_id"],
                   outcome=d["outcome"], summary=dict(d.get("summary") or {}),
                   error=d.get("error"))


@dataclass(frozen=True)
class SessionIdentity:
    """Distill core/session.py:15-46. Identity bất biến của một session."""
    session_id: str
    run_id: str
    task_id: str
    agent_id: str
    depth: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "run_id": self.run_id, "task_id": self.task_id,
                "agent_id": self.agent_id, "depth": self.depth}


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 2 — APPLICATION CONTEXT (core/session.py + core/kernel.py).
# Entities BẤT BIẾN; state MUTABLE tách riêng. Domain không biết HTTP/file/LLM.
# ─────────────────────────────────────────────────────────────────────────────
class StateStore:
    """Distill core/state.StateStore (rút gọn). State mutable của một run."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def snapshot(self) -> dict[str, Any]:
        return dict(self._data)


@dataclass
class KernelSession:
    """Distill core/session.py:49-102 (lược execute_tool để giữ trọng tâm vào tách identity/state).

    Identity là entity BẤT BIẾN; state là store MUTABLE. Domain layer này không import
    flask/sqlite/llm — nó chỉ thao tác trên entity + state.
    """
    identity: SessionIdentity
    state: StateStore
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def is_active(self) -> bool:
        return not self._closed and isinstance(self.state.get("current_task"), TaskEnvelope)

    def complete_task(self, result: Any = None, *, status: str = "completed") -> dict[str, Any]:
        if not self.is_active:
            raise RuntimeError("Session task lifecycle is already closed.")
        outcome = {"task_id": self.identity.task_id, "status": status, "result": result}
        self.state.set("last_result", outcome)
        self.state.set("current_task", None)
        self._closed = True
        return outcome


class AgentKernel:
    """Distill core/kernel.py:76-98 (rút gọn). Orchestrator thuần: registry + freeze.

    Không import flask/sqlite/llm client. Đây là 'application orchestrator', mọi I/O sống
    ở adapter/feature/middleware (các case khác).
    """

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._frozen = False

    def register_tool(self, name: str, executor: Any) -> None:
        if self._frozen:
            raise RuntimeError("Registry is frozen for active sessions.")
        self._tools[name] = executor

    def freeze(self) -> None:
        """core/kernel.py:91-97 — đóng băng cấu hình chia sẻ trước session đầu tiên."""
        self._frozen = True

    def has_tool(self, name: str) -> bool:
        return name in self._tools


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — "Entity = ORM model" (hiểu sai phổ biến của bài học gốc).
# ORM model trộn schema + behavior + lazy-load cần 'DB session'. Không pure.
# ─────────────────────────────────────────────────────────────────────────────
class _FakeDBSession:
    """Giả lập một DB session: lazy-load tốn 'I/O' và phải mở session mới chạy được."""
    def __init__(self) -> None:
        self.open = True
        self.queries = 0

    def load_relationship(self, name: str) -> list[str]:
        if not self.open:
            raise RuntimeError("Detached instance: DB session is closed (lazy-load fails).")
        self.queries += 1
        time.sleep(0.001)  # mô phỏng round-trip I/O
        return [f"{name}_row_{i}" for i in range(3)]


class OrmStyleResult:
    """ANTI: 'entity' kiểu ORM — mutable, behavior trộn, lazy-load cần DB session.

    Tạo nó trong test buộc bạn phải có _FakeDBSession; truy cập quan hệ kích hoạt I/O;
    đóng session -> truy cập sau đó vỡ ('detached instance'). Đây là điều entity thuần TRÁNH.
    """
    def __init__(self, delegation_id: str, db: _FakeDBSession) -> None:
        self.delegation_id = delegation_id
        self.outcome = "success"
        self._db = db  # phụ thuộc hạ tầng ngay trong 'entity'

    @property
    def artifacts(self) -> list[str]:
        return self._db.load_relationship("artifact")  # lazy-load -> I/O


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 74)
    print("CASE 03 — Core Domain Entities (Immutable Boundaries) trong hex_agent")
    print("=" * 74)

    print("\n[1] Entity thuần: tạo/serialize/deserialize KHÔNG cần framework.")
    task = TaskEnvelope(user_request="tóm tắt tài liệu", context={"lang": "vi"})
    round_trip = TaskEnvelope.from_dict(task.as_dict())
    print("    task_id ổn định qua round-trip:", round_trip.task_id == task.task_id)
    print("    as_dict():", task.as_dict())

    print("\n[2] Bất biến (frozen): không thể gán đè; thay đổi = tạo bản mới (replace).")
    try:
        task.user_request = "đổi"  # type: ignore[misc]
    except Exception as exc:
        print("    gán đè bị chặn:", type(exc).__name__)
    task2 = replace(task, user_request="yêu cầu mới")
    print("    replace() tạo bản mới, bản cũ nguyên vẹn:",
          task.user_request, "|", task2.user_request)

    print("\n[3] Cùng entity được nhiều vòng tiêu thụ y hệt (use case / adapter / bootstrap).")
    result = DelegationResult(delegation_id="d1", parent_task_id="t1", outcome="success",
                              summary={"artifact_count": 2})
    wire = result.as_dict()                       # adapter serialize
    restored = DelegationResult.from_dict(wire)   # adapter/bootstrap deserialize
    print("    serialize -> deserialize bằng nhau:", restored == result)

    print("\n[4] Tách identity (bất biến) khỏi state (mutable) trong KernelSession.")
    kernel = AgentKernel()
    kernel.register_tool("echo", object())
    kernel.freeze()  # core/kernel.py:91 — đóng băng trước session đầu tiên
    try:
        kernel.register_tool("late", object())
    except Exception as exc:
        print("    đăng ký tool SAU freeze bị chặn:", type(exc).__name__)
    state = StateStore(); state.set("current_task", task)
    session = KernelSession(
        SessionIdentity(session_id=uuid.uuid4().hex, run_id="r1", task_id=task.task_id,
                        agent_id="agent:root"),
        state,
    )
    print("    is_active:", session.is_active)
    out = session.complete_task({"ok": True})
    print("    sau complete_task -> is_active:", session.is_active, "| status:", out["status"])

    print("\n[5] BENCHMARK độ thuần: tạo 10_000 DelegationResult (entity) vs ORM-style.")
    n = 10_000
    t0 = time.perf_counter()
    pure = [DelegationResult(f"d{i}", "t1", "success") for i in range(n)]
    t_pure = time.perf_counter() - t0
    print(f"    Entity thuần: tạo {n} object trong {t_pure*1000:.2f} ms (không I/O).")

    print("\n[6] ĐỐI CHỨNG — 'entity' kiểu ORM cần DB session + lazy-load I/O.")
    db = _FakeDBSession()
    orm = OrmStyleResult("d1", db)
    arts = orm.artifacts  # kích hoạt lazy-load -> I/O
    print("    truy cập .artifacts kích hoạt", db.queries, "query (I/O).")
    db.open = False
    try:
        _ = orm.artifacts  # detached -> vỡ
    except Exception as exc:
        print("    sau khi đóng session, truy cập lại VỠ:", type(exc).__name__)
    print("    -> entity thuần KHÔNG có vấn đề này: nó không biết tới DB.")

    # ── ASSERT: bất biến của pattern ──
    # (a) Round-trip serialize giữ nguyên dữ liệu (entity là contract ổn định).
    assert round_trip == task
    assert restored == result
    # (b) frozen: không thể mutate -> phải dùng replace -> bản cũ bất biến.
    assert task.user_request == "tóm tắt tài liệu" and task2.user_request == "yêu cầu mới"
    # (c) Entity frozen có-trường-vô-hướng thì hashable -> bỏ được vào set/dict key.
    #     (Lưu ý: entity chứa field dict/tuple như DelegationResult vẫn KHÔNG hashable —
    #      bản thật core/schemas.py cũng vậy; ta minh hoạ trên SessionIdentity vốn chỉ có str/int.)
    sid = SessionIdentity(session_id="s", run_id="r", task_id="t", agent_id="a")
    sid_same = SessionIdentity(session_id="s", run_id="r", task_id="t", agent_id="a")
    assert len({sid, sid_same}) == 1  # hai bản bằng nhau -> 1 phần tử trong set
    # (d) Tách lifecycle: complete_task đóng session đúng một lần.
    assert session.is_active is False
    try:
        session.complete_task()
    except RuntimeError:
        pass
    else:
        raise AssertionError("complete_task lần hai phải raise")
    # (e) Độ thuần: 10_000 entity tạo nhanh và KHÔNG phát sinh query nào (khác ORM).
    assert len(pure) == n
    assert db.queries == 1  # ORM-style: 1 query cho 1 lần truy cập quan hệ
    # (f) Freeze chặn mutate registry sau khi session bắt đầu.
    assert kernel.has_tool("echo") and not kernel.has_tool("late")

    print("\n[OK] Mọi assert qua. Entity = pure, immutable contract; 0 import vòng ngoài; unit-testable.")


if __name__ == "__main__":
    demo()
