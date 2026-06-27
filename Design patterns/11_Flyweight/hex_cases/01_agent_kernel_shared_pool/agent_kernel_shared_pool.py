"""
Case 01 — AgentKernel: Shared Frozen Factory + Registry Pool (Flyweight)
========================================================================

Bản DISTILL trung thực từ hex_agent. Nguồn thật được mô phỏng:

  - core/kernel.py:14-22   _deep_freeze(): biến mọi cấu trúc mutable thành
                           proxy bất biến (MappingProxyType cho dict, frozenset
                           cho set, tuple cho list) -> guard immutability.
  - core/kernel.py:91-97   AgentKernel.freeze(): deep-freeze config MỘT lần,
                           freeze registry, bật cờ _frozen.
  - core/registry.py:43-112 CapabilityRegistry: pool _tools (dict keyed theo
                           tên tool); resolve_tool() (103-112) TRẢ VỀ bản
                           ToolResolution cache, KHÔNG tạo instance mới mỗi
                           lần hỏi.
  - core/registry.py:10-20 ToolDescriptor frozen + DEFAULT_DESCRIPTOR (constant
                           singleton dùng chung cho tool không khai báo riêng).
  - core/session.py:104-146 SessionFactory: nơi DUY NHẤT tạo KernelSession;
                           mọi session THAM CHIẾU cùng một kernel bất biến,
                           không bao giờ copy registry/config.
  - core/session.py:141   kernel.freeze() được gọi trước khi session đầu chạy.

Vai trò Flyweight:
  AgentKernel   = Flyweight Factory + Shared Intrinsic Pool (config + executors
                  + descriptors đã freeze, dùng chung cho N session).
  KernelSession = Context (giữ extrinsic state per-task, trỏ tới kernel).
  _deep_freeze + frozen dataclass = Immutability guard.
  SessionFactory = Client lắp ráp Session mà KHÔNG nhân bản Kernel.

Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Immutability guard — distill của core/kernel.py:14-22 (_deep_freeze)
# ---------------------------------------------------------------------------
def deep_freeze(value: Any) -> Any:
    """Biến mọi cấu trúc mutable thành proxy bất biến (như core/kernel.py:14-22)."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: deep_freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(v) for v in value)
    return value


# ---------------------------------------------------------------------------
# Intrinsic state nhỏ — distill core/registry.py:10-20 (ToolDescriptor)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolDescriptor:
    """Metadata bất biến của 1 tool. (core/registry.py:10-18)"""
    kind: str = "tool"
    idempotent: bool = False
    risk: str = "low"


# Constant singleton dùng chung cho mọi tool không có descriptor riêng.
# (core/registry.py:20)  -> đây chính là Flyweight intrinsic được share.
DEFAULT_DESCRIPTOR = ToolDescriptor()


@dataclass(frozen=True)
class ToolResolution:
    """Kết quả tra cứu tool: executor + descriptor. (core/registry.py:23-26)"""
    executor: Any
    descriptor: ToolDescriptor = DEFAULT_DESCRIPTOR


# ---------------------------------------------------------------------------
# CapabilityRegistry — distill core/registry.py:43-112
#   _tools là POOL keyed theo tên; resolve_tool() trả bản cache, không new.
# ---------------------------------------------------------------------------
class CapabilityRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._frozen = False

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError("Capability registry is frozen for active sessions.")

    def freeze(self) -> None:
        self._frozen = True

    def register_tool(self, name: str, executor: Any, *, kind: str = "tool",
                      idempotent: bool = False, risk: str = "low") -> None:
        self._ensure_mutable()
        self._tools[name] = executor
        self._descriptors[name] = ToolDescriptor(kind=kind, idempotent=idempotent, risk=risk)

    def resolve_tool(self, name: str) -> ToolResolution:
        # core/registry.py:103-112 — KHÔNG tạo instance mới mỗi lần hỏi;
        # tool không có descriptor riêng dùng chung DEFAULT_DESCRIPTOR.
        if name in self._tools:
            return ToolResolution(self._tools[name],
                                  self._descriptors.get(name, DEFAULT_DESCRIPTOR))
        raise KeyError(f"No tool registered for {name!r}")

    def list_tools(self) -> list[str]:
        return sorted(self._tools)


# ---------------------------------------------------------------------------
# AgentKernel — Flyweight Factory + Shared Intrinsic Pool
#   distill core/kernel.py:76-98
# ---------------------------------------------------------------------------
@dataclass
class AgentKernel:
    registry: CapabilityRegistry
    config: Mapping[str, Any] = field(default_factory=dict)
    _frozen: bool = False

    def freeze(self) -> None:
        """Freeze shared mutable config MỘT lần. (core/kernel.py:91-97)"""
        if self._frozen:
            return
        self.registry.freeze()
        self.config = deep_freeze(copy.deepcopy(dict(self.config)))
        self._frozen = True

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        # Tra POOL dùng chung; executor + descriptor là intrinsic chia sẻ.
        resolution = self.registry.resolve_tool(tool_name)
        result = resolution.executor.execute(args)
        result["_descriptor_id"] = id(resolution.descriptor)  # để chứng minh share
        return result


# ---------------------------------------------------------------------------
# Context per-task — distill core/session.py (KernelSession + SessionIdentity)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SessionIdentity:
    """Identity bất biến của 1 session. (core/session.py:15-23)"""
    session_id: str
    task_id: str


@dataclass
class KernelSession:
    """Context: giữ extrinsic state per-task, THAM CHIẾU kernel dùng chung.
    (core/session.py:49-85)"""
    kernel: AgentKernel
    identity: SessionIdentity
    scratch: dict[str, Any] = field(default_factory=dict)  # extrinsic, riêng từng session

    def run(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return self.kernel.execute_tool(tool_name, args)


# ---------------------------------------------------------------------------
# SessionFactory — Client lắp ráp Session, KHÔNG nhân bản Kernel
#   distill core/session.py:104-146
# ---------------------------------------------------------------------------
class SessionFactory:
    def __init__(self, *, kernel: AgentKernel) -> None:
        self.kernel = kernel

    def create_root(self, task_id: str) -> KernelSession:
        self.kernel.freeze()  # core/session.py:141 — đông cứng trước session đầu
        return KernelSession(
            kernel=self.kernel,  # CHIA SẺ identity, không copy
            identity=SessionIdentity(session_id=uuid.uuid4().hex, task_id=task_id),
        )


# ---------------------------------------------------------------------------
# Tool executor giả lập tối thiểu bằng stdlib (thay LLM/IO nặng)
# ---------------------------------------------------------------------------
class EchoTool:
    name = "echo_tool"

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "echo": dict(args)}


def build_kernel() -> AgentKernel:
    """distill core/bootstrap.py:56-66 — tạo MỘT kernel với registry + config dùng chung."""
    registry = CapabilityRegistry()
    registry.register_tool("echo", EchoTool(), kind="tool", idempotent=True)
    return AgentKernel(registry=registry, config={"limits": {"max_steps": 20}, "tags": {"a", "b"}})


# ---------------------------------------------------------------------------
# Đối chứng: KHÔNG dùng Flyweight -> mỗi session tự copy kernel
# ---------------------------------------------------------------------------
class HeavySessionNoFlyweight:
    """Anti-pattern: mỗi session DEEP-COPY toàn bộ kernel/registry/config.
    Giống 'mỗi synapse ôm full receptor design' trong bài học gốc."""

    def __init__(self, kernel: AgentKernel, task_id: str) -> None:
        # Sao chép toàn bộ registry + config cho RIÊNG session này -> O(N) bộ nhớ.
        self.kernel = copy.deepcopy(kernel)
        self.task_id = task_id


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — AgentKernel: Shared Frozen Factory + Registry Pool (Flyweight)")
    print("=" * 72)

    print("\n[1] Tạo MỘT kernel (intrinsic: registry + config + executors).")
    kernel = build_kernel()
    factory = SessionFactory(kernel=kernel)

    print("\n[2] SessionFactory tạo 2 session (extrinsic: state per-task).")
    s1 = factory.create_root(task_id="task-A")
    s2 = factory.create_root(task_id="task-B")
    print(f"    session_1.id={s1.identity.session_id[:8]}  task={s1.identity.task_id}")
    print(f"    session_2.id={s2.identity.session_id[:8]}  task={s2.identity.task_id}")

    print("\n[3] Hai session CHIA SẺ cùng một kernel (so sánh identity 'is').")
    print(f"    s1.kernel is s2.kernel  -> {s1.kernel is s2.kernel}")
    assert s1.kernel is s2.kernel, "Flyweight: N session phải dùng chung 1 kernel"

    print("\n[4] Registry pool KHÔNG bị nhân bản theo session.")
    print(f"    s1.kernel.registry is s2.kernel.registry -> "
          f"{s1.kernel.registry is s2.kernel.registry}")
    assert s1.kernel.registry is s2.kernel.registry

    print("\n[5] resolve_tool() trả descriptor DÙNG CHUNG (cùng DEFAULT_DESCRIPTOR / cache).")
    r1 = s1.run("echo", {"msg": "xin chao"})
    r2 = s2.run("echo", {"msg": "tu task B"})
    print(f"    r1={r1['echo']}  r2={r2['echo']}")
    # Mỗi session chạy độc lập nhưng descriptor (intrinsic) là cùng một object.
    print(f"    descriptor id giống nhau giữa 2 lần gọi -> "
          f"{r1['_descriptor_id'] == r2['_descriptor_id']}")
    assert r1["_descriptor_id"] == r2["_descriptor_id"]

    print("\n[6] Sau freeze(), kernel BẤT BIẾN: config là MappingProxyType, set thành frozenset.")
    print(f"    type(kernel.config) = {type(kernel.config).__name__}")
    assert isinstance(kernel.config, MappingProxyType)
    assert isinstance(kernel.config["tags"], frozenset)
    mutate_failed = False
    try:
        kernel.config["limits"] = {}  # type: ignore[index]
    except TypeError:
        mutate_failed = True
    print(f"    Thử mutate kernel.config -> bị chặn? {mutate_failed}")
    assert mutate_failed, "Flyweight phải immutable sau freeze"

    print("\n[7] Registry cũng bị khóa: không register thêm tool khi đã freeze.")
    register_failed = False
    try:
        kernel.registry.register_tool("late", EchoTool())
    except RuntimeError:
        register_failed = True
    print(f"    Thử register tool sau freeze -> bị chặn? {register_failed}")
    assert register_failed

    print("\n[8] ĐỐI CHỨNG — KHÔNG dùng Flyweight (mỗi session deep-copy kernel):")
    # Dùng kernel CHƯA freeze cho đối chứng; freeze biến config thành mappingproxy
    # vốn không pickle/deepcopy được — bản thân điều đó cũng cho thấy vì sao share
    # (Flyweight) tốt hơn copy.
    raw_kernel = build_kernel()
    h1 = HeavySessionNoFlyweight(raw_kernel, "task-A")
    h2 = HeavySessionNoFlyweight(raw_kernel, "task-B")
    print(f"    h1.kernel is h2.kernel -> {h1.kernel is h2.kernel}  (FALSE = mỗi bản 1 copy)")
    print(f"    h1.kernel is raw_kernel -> {h1.kernel is raw_kernel}  (FALSE = phí bộ nhớ)")
    assert h1.kernel is not h2.kernel
    assert h1.kernel is not raw_kernel
    print("    => N session = N bản copy registry+config. Memory O(N) thay vì O(1).")

    print("\n[KẾT] Flyweight: K=1 kernel bất biến phục vụ N session. Memory O(1)+O(N extrinsic).")
    print("All asserts passed.")


if __name__ == "__main__":
    demo()
