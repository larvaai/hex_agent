"""
Lesson 08 — Composite Pattern
Ví dụ neuroscience: cortical column hierarchy
    SingleNeuron → Minicolumn → CorticalColumn → CorticalArea → Hemisphere
Mọi cấp cùng interface (fire, total_activity, find_by_name, apply_plasticity)
→ client xử lý đồng nhất, đệ quy đóng gói trong Composite.

File này triển khai 9 phần:
    A. ANTI-PATTERN — đệ quy isinstance-based (kém maintainable)
    B. Component interface NeuralUnit (Safe variant)
    C. Leaf: SingleNeuron với Hebbian plasticity
    D. Composite: NeuralComposite + 3 cấp cụ thể
    E. Operations đệ quy: fire, total_activity, find, count, plasticity
    F. Demo build hierarchy + run operations
    G. Demo simulated stroke (xóa 1 column)
    H. Demo extension: thêm cấp Hemisphere không sửa code cũ
    I. Ellumm: MemoryNode hierarchy (atomic → cluster → episode → theme)
"""

from __future__ import annotations
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable


# =============================================================================
# A. ANTI-PATTERN — đệ quy isinstance-based
# =============================================================================
# Để cảm nhận nỗi đau. Mỗi operation cần if-else theo type, lặp DRY.

def total_activity_anti_pattern(node) -> float:
    if hasattr(node, "firing_rate") and not hasattr(node, "_children"):
        return node.firing_rate                                # leaf
    elif hasattr(node, "_children"):
        return sum(total_activity_anti_pattern(c) for c in node._children)
    else:
        raise TypeError(f"Unknown node type: {type(node)}")
# Mỗi operation (fire, find, count, plasticity) phải lặp lại logic này.
# Thêm cấp mới (Hemisphere) = sửa MỌI function dạng này.


# =============================================================================
# B + C + D. Component / Leaf / Composite (Safe variant)
# =============================================================================

class NeuralUnit(ABC):
    """
    Component interface — mọi đơn vị thần kinh ở mọi cấp implement cái này.
    Không có add/remove ở đây → Safe variant.
    """
    name: str

    @abstractmethod
    def fire(self, stimulus: float) -> None: ...

    @abstractmethod
    def total_activity(self) -> float: ...

    @abstractmethod
    def find_by_name(self, target: str) -> Optional["NeuralUnit"]: ...

    @abstractmethod
    def count_neurons(self) -> int: ...

    @abstractmethod
    def apply_hebbian(self, lr: float) -> None: ...


# ----------------------------------------------------------------------------
# C. LEAF
# ----------------------------------------------------------------------------

class SingleNeuron(NeuralUnit):
    """Leaf — đơn vị nhỏ nhất. Có firing rate, weight, threshold."""

    def __init__(self, name: str, weight: float = 0.5, threshold: float = 0.3):
        self.name = name
        self.weight = weight
        self.threshold = threshold
        self.firing_rate: float = 0.0
        self._last_input: float = 0.0

    def fire(self, stimulus: float) -> None:
        self._last_input = stimulus
        net = stimulus * self.weight
        self.firing_rate = max(0.0, net - self.threshold) if net > self.threshold else 0.0

    def total_activity(self) -> float:
        return self.firing_rate

    def find_by_name(self, target: str) -> Optional[NeuralUnit]:
        return self if self.name == target else None

    def count_neurons(self) -> int:
        return 1

    def apply_hebbian(self, lr: float) -> None:
        # Hebbian: weight tăng nếu cả input và output đều fire mạnh
        # ΔW = lr * input * output
        if self._last_input > 0 and self.firing_rate > 0:
            self.weight = min(1.5, self.weight + lr * self._last_input * self.firing_rate)


# ----------------------------------------------------------------------------
# D. COMPOSITE
# ----------------------------------------------------------------------------

class NeuralComposite(NeuralUnit, ABC):
    """
    Composite abstract — chứa NeuralUnit children (có thể là Leaf hoặc Composite khác).
    add/remove/get_children chỉ có ở đây (Safe variant).
    """

    def __init__(self, name: str):
        self.name = name
        self._children: list[NeuralUnit] = []

    # --- Composite-only methods ---
    def add(self, unit: NeuralUnit) -> None:
        self._children.append(unit)

    def remove(self, unit: NeuralUnit) -> None:
        self._children.remove(unit)

    def get_children(self) -> list[NeuralUnit]:
        return list(self._children)

    # --- NeuralUnit interface — đệ quy đóng gói ---
    def fire(self, stimulus: float) -> None:
        for child in self._children:
            child.fire(stimulus)

    def total_activity(self) -> float:
        return sum(c.total_activity() for c in self._children)

    def find_by_name(self, target: str) -> Optional[NeuralUnit]:
        if self.name == target:
            return self
        for child in self._children:
            result = child.find_by_name(target)
            if result is not None:
                return result
        return None

    def count_neurons(self) -> int:
        return sum(c.count_neurons() for c in self._children)

    def apply_hebbian(self, lr: float) -> None:
        for child in self._children:
            child.apply_hebbian(lr)


class Minicolumn(NeuralComposite):
    """Composite cấp 1 — ~80-100 neurons cùng response selectivity."""
    pass


class CorticalColumn(NeuralComposite):
    """Composite cấp 2 — ~10.000 neurons, gồm nhiều minicolumn."""
    pass


class CorticalArea(NeuralComposite):
    """Composite cấp 3 — V1, V2, A1, S1, ..."""
    pass


# =============================================================================
# Helper: build a small cortical region
# =============================================================================

def build_cortical_area(name: str, n_columns: int = 3, n_minicol_per_col: int = 4,
                       n_neurons_per_mini: int = 5, seed: int = 42) -> CorticalArea:
    """Xây 1 cortical area với cấu trúc lồng đầy đủ."""
    random.seed(seed)
    area = CorticalArea(name)
    for c in range(n_columns):
        col = CorticalColumn(f"{name}_col{c}")
        for m in range(n_minicol_per_col):
            mini = Minicolumn(f"{name}_col{c}_mini{m}")
            for n in range(n_neurons_per_mini):
                neuron = SingleNeuron(
                    name=f"{name}_c{c}m{m}n{n}",
                    weight=round(random.uniform(0.3, 1.0), 2),
                    threshold=round(random.uniform(0.1, 0.4), 2),
                )
                mini.add(neuron)
            col.add(mini)
        area.add(col)
    return area


# =============================================================================
# I. ELLUMM — MemoryNode hierarchy
# =============================================================================

class MemoryNode(ABC):
    name: str
    @abstractmethod
    def total_emotion_load(self) -> float: ...
    @abstractmethod
    def find_about(self, query: str) -> list["MemoryNode"]: ...
    @abstractmethod
    def consolidate(self) -> None: ...
    @abstractmethod
    def count_atomic(self) -> int: ...


@dataclass
class AtomicMemory(MemoryNode):
    """Leaf — 1 trải nghiệm đơn."""
    name: str
    content: str
    emotion: float          # 0-1, |valence| × arousal
    tags: list[str] = field(default_factory=list)
    consolidated: bool = False

    def total_emotion_load(self) -> float:
        return self.emotion

    def find_about(self, query: str) -> list[MemoryNode]:
        q = query.lower()
        if q in self.content.lower() or any(q in t.lower() for t in self.tags):
            return [self]
        return []

    def consolidate(self) -> None:
        self.consolidated = True

    def count_atomic(self) -> int:
        return 1


class MemoryComposite(MemoryNode, ABC):
    """Composite abstract cho memory — chứa MemoryNode children."""

    def __init__(self, name: str):
        self.name = name
        self._children: list[MemoryNode] = []

    def add(self, node: MemoryNode) -> None:
        self._children.append(node)

    def total_emotion_load(self) -> float:
        return sum(c.total_emotion_load() for c in self._children)

    def find_about(self, query: str) -> list[MemoryNode]:
        results: list[MemoryNode] = []
        for c in self._children:
            results.extend(c.find_about(query))
        return results

    def consolidate(self) -> None:
        for c in self._children:
            c.consolidate()

    def count_atomic(self) -> int:
        return sum(c.count_atomic() for c in self._children)


class MemoryCluster(MemoryComposite): pass
class EpisodicMemory(MemoryComposite): pass
class ThemeMemory(MemoryComposite): pass


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    print("=" * 64)
    print("F. BUILD CORTICAL AREA + RUN OPERATIONS")
    print("=" * 64)
    v1 = build_cortical_area("V1", n_columns=3, n_minicol_per_col=4, n_neurons_per_mini=5)
    print(f"  Built {v1.name}: {v1.count_neurons()} neurons "
          f"({len(v1.get_children())} columns × "
          f"{len(v1.get_children()[0].get_children())} minicolumns × "
          f"{len(v1.get_children()[0].get_children()[0].get_children())} neurons)")

    # Stimulus presentation — 1 call lan đệ quy xuống mọi neuron
    stim = 0.8
    v1.fire(stim)
    activity_before = v1.total_activity()
    print(f"  After fire(stim={stim}): total_activity = {activity_before:.2f}")

    # Apply Hebbian plasticity 5 lần
    for _ in range(5):
        v1.fire(stim)
        v1.apply_hebbian(lr=0.05)
    activity_after = v1.total_activity()
    print(f"  After 5x Hebbian: total_activity = {activity_after:.2f} (↑ với learning)")

    # Find by name — đệ quy xuyên cây
    target = v1.find_by_name("V1_c1m2n3")
    if target:
        assert isinstance(target, SingleNeuron)
        print(f"  Found neuron '{target.name}': weight={target.weight:.2f}, "
              f"firing_rate={target.firing_rate:.2f}")

    # Find by name của Composite
    col1 = v1.find_by_name("V1_col1")
    if col1:
        print(f"  Found column '{col1.name}': {col1.count_neurons()} neurons inside")

    print()
    print("=" * 64)
    print("G. SIMULATED STROKE — xóa 1 cortical column")
    print("=" * 64)
    pre_stroke_activity = v1.total_activity()
    pre_stroke_count = v1.count_neurons()
    print(f"  Trước stroke: {pre_stroke_count} neurons, activity = {pre_stroke_activity:.2f}")

    # Stroke phá column 1 (5 minicol × 5 neuron = 20 neuron mất)
    col_to_stroke = v1.find_by_name("V1_col1")
    assert col_to_stroke is not None
    v1.remove(col_to_stroke)

    post_stroke_count = v1.count_neurons()
    v1.fire(stim)                                          # firing lại sau stroke
    post_stroke_activity = v1.total_activity()
    print(f"  Sau stroke: {post_stroke_count} neurons, activity = {post_stroke_activity:.2f}")
    print(f"  V1 vẫn xử lý được visual input — chỉ activity giảm tỉ lệ")
    print(f"  (lost ~{pre_stroke_count - post_stroke_count} neurons "
          f"= {(1 - post_stroke_count / pre_stroke_count) * 100:.1f}%)")
    print(f"  → Damage tolerance: phá 1 column không phá area.")
    print(f"    Sinh học: scotoma ở vùng tương ứng visual field, phần khác intact.")

    print()
    print("=" * 64)
    print("H. EXTENSION — thêm cấp Hemisphere KHÔNG sửa class cũ")
    print("=" * 64)

    class Hemisphere(NeuralComposite):
        """Composite cấp 4 — bán cầu, chứa nhiều CorticalArea."""
        pass

    # Build right hemisphere với 3 area
    right_h = Hemisphere("right_hemisphere")
    right_h.add(build_cortical_area("V1_R", seed=1))
    right_h.add(build_cortical_area("V2_R", seed=2))
    right_h.add(build_cortical_area("A1_R", seed=3))

    right_h.fire(0.6)
    print(f"  Hemisphere '{right_h.name}': {right_h.count_neurons()} neurons "
          f"across {len(right_h.get_children())} areas")
    print(f"  Total activity: {right_h.total_activity():.2f}")
    print("  ✓ Thêm cấp Hemisphere — không sửa NeuralUnit, NeuralComposite, hay 3 cấp dưới.")

    print()
    print("=" * 64)
    print("I. ELLUMM — MemoryNode hierarchy")
    print("=" * 64)

    # Build hierarchy: Theme > Episode > Cluster > Atomic
    theme = ThemeMemory("december_2024")

    # Episode 1: Tuần làm việc 1
    ep1 = EpisodicMemory("week_1")
    cluster_morning = MemoryCluster("monday_morning")
    cluster_morning.add(AtomicMemory("a1", "saw apple on desk", emotion=0.2, tags=["apple", "morning"]))
    cluster_morning.add(AtomicMemory("a2", "heard bell at 8am", emotion=0.3, tags=["bell", "morning"]))
    cluster_morning.add(AtomicMemory("a3", "drank coffee", emotion=0.4, tags=["coffee", "morning"]))
    ep1.add(cluster_morning)

    cluster_afternoon = MemoryCluster("monday_afternoon")
    cluster_afternoon.add(AtomicMemory("a4", "snake near garden!", emotion=0.95, tags=["snake", "fear"]))
    cluster_afternoon.add(AtomicMemory("a5", "ran to safety", emotion=0.85, tags=["snake", "escape"]))
    ep1.add(cluster_afternoon)

    theme.add(ep1)

    # Episode 2: Tuần 2 — vui hơn
    ep2 = EpisodicMemory("week_2")
    fun = MemoryCluster("friday_celebration")
    fun.add(AtomicMemory("b1", "received gift from team", emotion=0.7, tags=["gift", "happy"]))
    fun.add(AtomicMemory("b2", "ate chocolate cake", emotion=0.8, tags=["cake", "happy"]))
    ep2.add(fun)
    theme.add(ep2)

    print(f"  Theme '{theme.name}': {theme.count_atomic()} atomic memories")
    print(f"  Total emotion load: {theme.total_emotion_load():.2f}")

    # Search xuyên hierarchy
    snake_memories = theme.find_about("snake")
    print(f"\n  Tìm 'snake' xuyên cây: {len(snake_memories)} kết quả")
    for m in snake_memories:
        if isinstance(m, AtomicMemory):
            print(f"    - {m.name}: '{m.content}' (emotion={m.emotion})")

    happy_memories = theme.find_about("happy")
    print(f"\n  Tìm 'happy' xuyên cây: {len(happy_memories)} kết quả")
    for m in happy_memories:
        if isinstance(m, AtomicMemory):
            print(f"    - {m.name}: '{m.content}' (emotion={m.emotion})")

    # Consolidate xuyên cây
    print(f"\n  Trước consolidate: a1.consolidated = "
          f"{cluster_morning.find_about('apple')[0].consolidated if cluster_morning.find_about('apple') else 'N/A'}")
    theme.consolidate()
    apple_memo = cluster_morning.find_about("apple")[0]
    assert isinstance(apple_memo, AtomicMemory)
    print(f"  Sau theme.consolidate(): a1.consolidated = {apple_memo.consolidated}")
    print(f"  ✓ 1 call lan đệ quy đến mọi atomic memory.")

    # Tìm episode "vui nhất" — operation cấp cao
    print()
    print("  Operation cấp cao: tìm episode 'vui' nhất tháng")
    happy_episodes_load: list[tuple[str, float]] = []
    for ep in theme._children:
        load = ep.total_emotion_load()
        happy_episodes_load.append((ep.name, load))
    top = max(happy_episodes_load, key=lambda x: x[1])
    print(f"    Episode emotion load: {happy_episodes_load}")
    print(f"    Top: {top[0]} ({top[1]:.2f})")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN
# =============================================================================
#
# TRANSPARENT vs SAFE — chọn cái nào?
# ────────────────────────────────────
# Transparent: NeuralUnit có cả add/remove (Leaf raise hoặc no-op).
#   + Client treat leaf và composite hoàn toàn giống nhau.
#   - Leaf có method vô nghĩa, dễ silent bug.
#
# Safe (file này dùng): chỉ NeuralComposite có add/remove.
#   + Type-safe, Leaf không có method vô nghĩa.
#   - Client phải check isinstance(node, NeuralComposite) khi add/remove.
#
# Python hiện đại thường dùng Safe + duck typing — kết hợp tốt nhất.
#
# CÁC PATTERN CẶP ĐÔI VỚI COMPOSITE
# ──────────────────────────────────
# - Iterator (lesson 16): traverse cây theo thứ tự (DFS, BFS, in-order).
#   Composite chứa children, Iterator quy định thứ tự thăm.
# - Visitor (lesson 23): operation phức tạp ngoài hierarchy.
#   Khi cần thêm operation mới mà không sửa Composite class → Visitor.
# - Decorator (lesson 09): wrap một Component bằng layer chức năng.
#   Decorator cũng implement Component interface → có thể chèn vào hierarchy.
# - Builder (lesson 04): xây cây phân cấp từng bước với validation.
#
# DẤU HIỆU OVER-ENGINEERING
# ──────────────────────────
# - Cấu trúc thực ra không phải tree mà chỉ là list flat → đừng dùng Composite.
# - Operation đơn giản (chỉ count, sum) trên collection nhỏ → built-in đủ.
# - Cấp cây ≤ 2 và không bao giờ thêm → just use list.
#
# Architect rule: nếu domain của bạn không có ngôn ngữ tự nhiên kiểu "X chứa
# Y, Y chứa Z, mọi cấp đều có thể fire/process/total" thì có lẽ không phải
# Composite. Cố ép Composite vào flat domain = over-engineering.
"""
"""
