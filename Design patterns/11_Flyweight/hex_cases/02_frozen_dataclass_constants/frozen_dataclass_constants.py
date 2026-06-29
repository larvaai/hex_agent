"""
Case 02 — Frozen Dataclass Constants: intrinsic state bất biến, chia sẻ
========================================================================

Bản DISTILL trung thực từ hex_agent. Nguồn thật được mô phỏng:

  - core/schemas.py:28-34   ToolRequest là @dataclass(frozen=True) -> bất biến,
                            hashable, dùng được làm dict key.
  - core/schemas.py:114-129 FeatureDescriptor frozen (name, version, capabilities,
                            enabled, description) — intrinsic identity của 1 feature.
  - core/registry.py:10-20  ToolDescriptor frozen + DEFAULT_DESCRIPTOR (constant
                            singleton dùng chung cho mọi tool không khai báo riêng).
  - features/example_echo.py:9-13  FEATURE = FeatureDescriptor(...) định nghĩa
                            MỘT LẦN ở module level; install() tái dùng cùng instance,
                            không tạo mới mỗi lần gọi.
  - core/session.py:15-23   SessionIdentity frozen — identity bất biến của session.

Vai trò Flyweight:
  Frozen dataclass            = Flyweight (intrinsic: structure + giá trị bất biến).
  Module-level constant        = instance dùng chung (FEATURE, DEFAULT_DESCRIPTOR).
  Client (tool/feature/session) = dùng constant mà không nhân bản.
  @dataclass(frozen=True)      = immutability guard ở mức ngôn ngữ.

Bài học gốc nhấn: Flyweight PHẢI immutable mới an toàn khi chia sẻ qua nhiều
context. frozen dataclass ép buộc điều đó ngay ở tầng ngôn ngữ -> chặn bug
"mutable Flyweight" (sửa 1 receptor mà 100T synapse cùng đổi theo).

Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Frozen value types — distill core/schemas.py
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolRequest:
    """distill core/schemas.py:28-34 — bất biến, hashable."""
    name: str
    # tuple thay vì dict để giữ tính hashable (đúng tinh thần frozen intrinsic).
    args: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class FeatureDescriptor:
    """distill core/schemas.py:114-129 — intrinsic identity của 1 feature."""
    name: str
    version: str = "0.1"
    capabilities: tuple[str, ...] = ()
    enabled: bool = True
    description: str = ""


@dataclass(frozen=True)
class ToolDescriptor:
    """distill core/registry.py:10-18."""
    kind: str = "tool"
    idempotent: bool = False
    risk: str = "low"


# Constant singleton — distill core/registry.py:20
DEFAULT_DESCRIPTOR = ToolDescriptor()

# Module-level FEATURE constant — distill features/example_echo.py:9-13
# Định nghĩa MỘT LẦN; mọi lần install() tái dùng đúng instance này.
FEATURE = FeatureDescriptor(
    name="example_echo",
    capabilities=("echo",),
    description="Trivial echo tool used by smoke tests and as a feature-plugin example.",
)


@dataclass(frozen=True)
class SessionIdentity:
    """distill core/session.py:15-23 — identity bất biến của session."""
    session_id: str
    task_id: str


# ---------------------------------------------------------------------------
# Registry tối thiểu để minh họa FEATURE được tái dùng (không tạo mới)
# ---------------------------------------------------------------------------
class TinyRegistry:
    def __init__(self) -> None:
        self.features: dict[str, FeatureDescriptor] = {}

    def register_feature(self, descriptor: FeatureDescriptor) -> None:
        self.features[descriptor.name] = descriptor


def install(registry: TinyRegistry) -> FeatureDescriptor:
    """distill features/example_echo.py:23-25 — tái dùng FEATURE module-level."""
    registry.register_feature(FEATURE)
    return FEATURE


# ---------------------------------------------------------------------------
# Đối chứng: "mutable Flyweight" — bug đặc trưng của bài học gốc
# ---------------------------------------------------------------------------
@dataclasses.dataclass  # KHÔNG frozen -> mutable
class BadDescriptor:
    """Anti-pattern: descriptor MUTABLE dùng chung -> sửa 1 chỗ, mọi nơi đổi theo."""
    kind: str = "tool"
    idempotent: bool = False
    risk: str = "low"


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — Frozen Dataclass Constants (Flyweight intrinsic immutable)")
    print("=" * 72)

    print("\n[1] FEATURE là constant module-level: install() KHÔNG tạo instance mới.")
    reg1, reg2 = TinyRegistry(), TinyRegistry()
    f1 = install(reg1)
    f2 = install(reg2)
    print(f"    f1 is f2 is FEATURE -> {f1 is f2 is FEATURE}")
    assert f1 is f2 is FEATURE, "Flyweight: tái dùng 1 instance dùng chung"
    print(f"    reg1.features['example_echo'] is reg2.features['example_echo'] -> "
          f"{reg1.features['example_echo'] is reg2.features['example_echo']}")
    assert reg1.features["example_echo"] is reg2.features["example_echo"]

    print("\n[2] DEFAULT_DESCRIPTOR là singleton dùng chung cho mọi tool 'mặc định'.")
    d_echo = DEFAULT_DESCRIPTOR
    d_noop = DEFAULT_DESCRIPTOR
    print(f"    d_echo is d_noop -> {d_echo is d_noop}")
    assert d_echo is d_noop

    print("\n[3] frozen dataclass là HASHABLE -> dùng được làm dict key / set member.")
    r1 = ToolRequest(name="echo", args=(("msg", "hi"),))
    r2 = ToolRequest(name="echo", args=(("msg", "hi"),))
    print(f"    r1 == r2 -> {r1 == r2}   hash(r1) == hash(r2) -> {hash(r1) == hash(r2)}")
    assert r1 == r2 and hash(r1) == hash(r2)
    cache: dict[ToolRequest, int] = {}
    cache[r1] = 1
    cache[r2] = cache.get(r2, 0) + 99  # r2 trùng key với r1
    print(f"    Dùng làm dict key -> cache[r1] = {cache[r1]} (r2 ghi đè cùng slot)")
    assert cache[r1] == 100 and len(cache) == 1

    print("\n[4] Cố mutate frozen dataclass -> bị chặn (FrozenInstanceError).")
    mutate_failed = False
    try:
        r1.name = "changed"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        mutate_failed = True
    print(f"    Thử r1.name = 'changed' -> bị chặn? {mutate_failed}")
    assert mutate_failed

    print("\n[5] Muốn 'đổi' thì tạo bản MỚI bằng replace() (intrinsic cũ giữ nguyên).")
    f_disabled = dataclasses.replace(FEATURE, enabled=False)
    print(f"    FEATURE.enabled={FEATURE.enabled}  f_disabled.enabled={f_disabled.enabled}")
    print(f"    FEATURE is f_disabled -> {FEATURE is f_disabled}")
    assert FEATURE.enabled is True and f_disabled.enabled is False
    assert FEATURE is not f_disabled, "replace tạo bản mới, không sửa bản gốc dùng chung"

    print("\n[6] ĐỐI CHỨNG — 'mutable Flyweight' (bug bài học gốc):")
    shared_bad = BadDescriptor(kind="tool")
    alias_a = shared_bad  # 2 'tool' cùng tham chiếu 1 descriptor mutable
    alias_b = shared_bad
    alias_a.risk = "HIGH"  # sửa 1 alias...
    print(f"    Sửa alias_a.risk='HIGH' -> alias_b.risk = {alias_b.risk!r} (BỊ ĐỔI THEO!)")
    assert alias_b.risk == "HIGH", "minh họa: mutable + shared = race condition disaster"
    print("    => Đây là lý do Flyweight PHẢI immutable. frozen=True chặn đúng bug này.")

    print("\n[KẾT] frozen dataclass = Flyweight intrinsic an toàn: bất biến, hashable, share được.")
    print("All asserts passed.")


if __name__ == "__main__":
    demo()
