"""
Lesson 01 — Singleton Pattern
Ví dụ neuroscience: Locus Coeruleus (LC) là nguồn norepinephrine duy nhất
phát tới toàn não. Mọi vùng cần đọc/ghi mức arousal đều phải tham chiếu
cùng 1 instance LC.

File này minh họa 3 cách cài Singleton trong Python:
    A. __new__ override               (cổ điển, rõ ràng)
    B. Metaclass                      (tổng quát, áp dụng nhiều class)
    C. Module-level singleton         (Pythonic nhất)

Mỗi cách có ưu/nhược riêng — thảo luận ở cuối file.
"""

from __future__ import annotations
import threading
from typing import Optional


# =============================================================================
# CÁCH A — __new__ override với thread-safe lazy init
# =============================================================================

class LocusCoeruleus:
    """
    Locus Coeruleus mô phỏng — Singleton phát norepinephrine (NE) toàn cục.

    Bất biến (invariant):
        - Tồn tại đúng 1 instance trong toàn vòng đời chương trình.
        - ne_level luôn ∈ [0, 100].
    """
    _instance: Optional["LocusCoeruleus"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "LocusCoeruleus":
        # Double-checked locking: kiểm tra ngoài lock trước cho nhanh,
        # rồi kiểm tra lại trong lock để đảm bảo thread-safe.
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False  # chống __init__ chạy lại
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        # __init__ luôn được Python gọi sau __new__, kể cả khi instance
        # đã tồn tại → cần guard để init đúng 1 lần.
        if getattr(self, "_initialized", False):
            return
        self._ne_level: float = 30.0       # baseline arousal
        self._subscribers: list[str] = []  # các vùng não đang lắng nghe
        self._initialized = True

    # --- API chính: phát và đọc norepinephrine ---

    def release_norepinephrine(self, target_level: float) -> None:
        """Đẩy NE lên target_level, có clamp 0..100."""
        self._ne_level = max(0.0, min(100.0, target_level))

    def read_arousal(self) -> float:
        return self._ne_level

    def register_region(self, region_name: str) -> None:
        """Một vùng não đăng ký lắng nghe LC (chuẩn bị cho Observer pattern lesson sau)."""
        self._subscribers.append(region_name)

    @property
    def regions(self) -> list[str]:
        return list(self._subscribers)


# =============================================================================
# CÁCH B — Metaclass: Singleton-hóa bất kỳ class nào
# =============================================================================

class SingletonMeta(type):
    """
    Metaclass áp Singleton lên mọi class dùng nó.
    Cú pháp:  class MyClass(metaclass=SingletonMeta): ...
    """
    _instances: dict[type, object] = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        # __call__ của metaclass = "khi class được gọi như hàm" (tức là tạo instance)
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class GlobalEmotionState(metaclass=SingletonMeta):
    """
    State cảm xúc toàn cục của Ellumm. Mọi module đọc/ghi cùng 1 instance.
    """
    def __init__(self) -> None:
        self.arousal: float = 30.0    # mức kích hoạt chung
        self.valence: float = 0.0     # tích cực / tiêu cực  (-50..+50)
        self.cortisol: float = 5.0    # stress hormone
        self.dopamine: float = 20.0   # reward / prediction error

    def snapshot(self) -> dict:
        return {
            "arousal": self.arousal,
            "valence": self.valence,
            "cortisol": self.cortisol,
            "dopamine": self.dopamine,
        }


# =============================================================================
# CÁCH C — Module-level singleton (Pythonic)
# =============================================================================
# Trong Python, một module chỉ được import đúng 1 lần (Python tự cache trong
# sys.modules). Vì vậy, một biến cấp module CHÍNH LÀ Singleton tự nhiên,
# không cần Lock, không cần metaclass.
#
# Cách dùng: trong project thật, đặt object này trong file riêng (ví dụ
# `arousal_state.py`) rồi `from arousal_state import arousal_state`.
# Ở đây mô phỏng bằng đối tượng module-level dưới dạng dataclass đơn giản.

class _ArousalStateModule:
    arousal: float = 30.0

arousal_state = _ArousalStateModule()  # ← đây là singleton "thật"


# =============================================================================
# DEMO — chứng minh cả 3 cách đều giữ đúng 1 instance
# =============================================================================

def demo() -> None:
    print("=" * 60)
    print("CÁCH A — LocusCoeruleus(__new__ override)")
    print("=" * 60)
    lc1 = LocusCoeruleus()
    lc2 = LocusCoeruleus()
    print(f"  lc1 is lc2 ?  {lc1 is lc2}")           # True
    print(f"  id(lc1) == id(lc2)?  {id(lc1) == id(lc2)}")

    # Mô phỏng: amygdala phát hiện stress → đẩy NE lên 85
    lc1.release_norepinephrine(85)
    # Hippocampus đọc qua một biến khác — vẫn thấy 85
    print(f"  Sau khi amygdala đẩy NE=85, hippocampus đọc: {lc2.read_arousal()}")

    # Đăng ký các vùng "nghe" LC (chuẩn bị cho Observer pattern)
    lc1.register_region("prefrontal_cortex")
    lc2.register_region("hippocampus")
    lc1.register_region("amygdala")
    print(f"  Subscribers từ lc1.regions: {lc1.regions}")
    print(f"  Subscribers từ lc2.regions: {lc2.regions}")
    print("  → Cùng list, vì cùng 1 instance.")

    print()
    print("=" * 60)
    print("CÁCH B — GlobalEmotionState (metaclass)")
    print("=" * 60)
    g1 = GlobalEmotionState()
    g2 = GlobalEmotionState()
    print(f"  g1 is g2 ?  {g1 is g2}")               # True
    g1.cortisol = 80
    g1.dopamine = 5
    print(f"  Snapshot từ g2 sau khi g1 set cortisol=80, dopamine=5:")
    print(f"    {g2.snapshot()}")

    print()
    print("=" * 60)
    print("CÁCH C — Module-level singleton (Pythonic)")
    print("=" * 60)
    print(f"  arousal_state.arousal trước: {arousal_state.arousal}")
    arousal_state.arousal = 72.5
    # Trong ứng dụng thật, module khác `from this_file import arousal_state`
    # → vẫn cùng 1 object.
    print(f"  Sau khi gán = 72.5: {arousal_state.arousal}")

    print()
    print("=" * 60)
    print("THẤT BẠI CỐ TÌNH — nếu KHÔNG dùng Singleton")
    print("=" * 60)

    class NaiveLC:
        def __init__(self) -> None:
            self.ne = 30.0

    amygdala_lc = NaiveLC()
    hippocampus_lc = NaiveLC()
    amygdala_lc.ne = 90  # amygdala nghĩ đang stress dữ dội
    print(f"  amygdala_lc.ne = {amygdala_lc.ne}, hippocampus_lc.ne = {hippocampus_lc.ne}")
    print("  → State phân mảnh: 2 vùng não đọc 2 mức arousal khác nhau cho")
    print("    cùng một sự kiện. Đây là loại bug 'eventual inconsistency'")
    print("    rất khó debug trong hệ thống thật.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN: 3 CÁCH — DÙNG CÁI NÀO?
# =============================================================================
#
# A. __new__ override
#    + Tường minh, dễ dạy, dễ debug.
#    + Có thể tự kiểm soát thread-safety chi tiết.
#    - Verbose. Nếu cần Singleton-hóa nhiều class → lặp code.
#    Khi nào dùng: dạy học, hoặc 1 class duy nhất trong toàn project.
#
# B. Metaclass
#    + Tổng quát: 1 SingletonMeta áp được vô số class.
#    + Tách concern (logic Singleton) khỏi class nghiệp vụ.
#    - Metaclass khó hiểu hơn cho người mới — abuse → khó maintain.
#    - Conflict nếu class đã có metaclass khác (ví dụ ABCMeta).
#    Khi nào dùng: framework / library cần áp Singleton lên nhiều class.
#
# C. Module-level singleton
#    + Pythonic nhất. Không cần Lock, không cần kỹ thuật.
#    + Test dễ: chỉ cần monkeypatch attribute hoặc thay module trong test.
#    - Không thật sự "lazy" (load lúc import). Không subclass được.
#    Khi nào dùng: 95% trường hợp Singleton trong Python — đây là default tốt.
#
# QUY TẮC NGÓN TAY CÁI:
#    Nếu phải hỏi "có nên dùng Singleton không?" → câu trả lời thường là KHÔNG.
#    Hãy hỏi tiếp "có thể dùng Dependency Injection thay không?". Nếu được, dùng DI.
#    Singleton chỉ chính đáng khi state thực sự là toàn cục về mặt domain
#    (ví dụ LC trong não, không phải repository trong app web).
