# -*- coding: utf-8 -*-
"""
Lesson 14 — Command Pattern
Analogy: Motor planning — SMA → BG (invoker) → PMC → M1 → spinal cord (receiver),
        cerebellum (comparator) corrects errors.

Cấu trúc:
  Section 1: Anti-pattern (gọi receiver trực tiếp)
  Section 2: Command interface + Receiver (Arm)
  Section 3: Concrete commands: Reach, Grip, Release
  Section 4: Invoker (BasalGanglia) — queue + history + undo
  Section 5: MacroCommand (Composite + Command) — drink_water sequence
  Section 6: Cerebellar comparator — kiểm tra expected vs actual
  Section 7: Failure cases — apraxia (params sai), parkinson (invoker chết),
             ataxia (no comparator), stale undo, macro undo sai thứ tự
  Section 8: Ellumm — ActionCommand cho agent action với undo + log + replay
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable, Any
from copy import deepcopy


# ============================================================
# SECTION 1: ANTI-PATTERN
# ============================================================
class NaiveArm:
    def __init__(self):
        self.position = (0, 0, 0)
        self.gripping = False
    def move_to(self, p): self.position = p
    def grip(self): self.gripping = True
    def release(self): self.gripping = False


def anti_pattern_demo():
    arm = NaiveArm()
    arm.move_to((10, 5, 0))
    arm.grip()
    arm.move_to((0, 0, 5))
    arm.release()
    # ❌ Không undo được. Không log. Không macro replay.


# ============================================================
# SECTION 2: RECEIVER + COMMAND INTERFACE
# ============================================================
class Arm:
    """RECEIVER — object thực sự thực thi action."""
    def __init__(self):
        self.position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.gripping: bool = False
        self.holding: Optional[str] = None

    def set_position(self, p): self.position = p
    def set_grip(self, g, item=None):
        self.gripping = g
        self.holding = item if g else None

    def __repr__(self):
        return f"Arm(pos={self.position}, grip={self.gripping}, holding={self.holding})"


class Command(ABC):
    """COMMAND interface."""
    @abstractmethod
    def execute(self) -> None: ...
    @abstractmethod
    def undo(self) -> None: ...
    @property
    def name(self) -> str:
        return type(self).__name__


# ============================================================
# SECTION 3: CONCRETE COMMANDS
# ============================================================
@dataclass
class ReachCommand(Command):
    arm: Arm
    target: Tuple[float, float, float]
    _prev_position: Optional[Tuple[float, float, float]] = field(default=None, init=False)

    def execute(self):
        self._prev_position = self.arm.position  # snapshot for undo
        self.arm.set_position(self.target)

    def undo(self):
        if self._prev_position is None:
            raise RuntimeError("Cannot undo before execute")
        self.arm.set_position(self._prev_position)


@dataclass
class GripCommand(Command):
    arm: Arm
    item: str
    _prev_state: Optional[Tuple[bool, Optional[str]]] = field(default=None, init=False)

    def execute(self):
        self._prev_state = (self.arm.gripping, self.arm.holding)
        self.arm.set_grip(True, self.item)

    def undo(self):
        if self._prev_state is None:
            raise RuntimeError("Cannot undo before execute")
        self.arm.set_grip(*self._prev_state)


@dataclass
class ReleaseCommand(Command):
    arm: Arm
    _prev_state: Optional[Tuple[bool, Optional[str]]] = field(default=None, init=False)

    def execute(self):
        self._prev_state = (self.arm.gripping, self.arm.holding)
        self.arm.set_grip(False)

    def undo(self):
        if self._prev_state is None:
            raise RuntimeError("Cannot undo before execute")
        self.arm.set_grip(*self._prev_state)


# ============================================================
# SECTION 4: INVOKER — BasalGanglia
# ============================================================
class BasalGanglia:
    """INVOKER — queue commands, history cho undo, replay log."""
    def __init__(self, max_history: int = 100):
        self.queue: List[Command] = []
        self.history: List[Command] = []
        self.replay_log: List[str] = []
        self.max_history = max_history
        self.frozen: bool = False  # mô phỏng Parkinson

    def submit(self, cmd: Command):
        if self.frozen:
            self.replay_log.append(f"[FROZEN] {cmd.name} not initiated")
            return
        self.queue.append(cmd)

    def step(self):
        """Thực thi 1 command từ queue."""
        if self.frozen or not self.queue:
            return
        cmd = self.queue.pop(0)
        cmd.execute()
        self.history.append(cmd)
        self.replay_log.append(f"EXEC {cmd.name}")
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def step_all(self):
        while self.queue:
            self.step()

    def undo_last(self) -> Optional[Command]:
        if not self.history: return None
        cmd = self.history.pop()
        cmd.undo()
        self.replay_log.append(f"UNDO {cmd.name}")
        return cmd

    def replay_log_str(self) -> str:
        return " | ".join(self.replay_log)


# ============================================================
# SECTION 5: MACRO COMMAND — Composite + Command
# ============================================================
class MacroCommand(Command):
    def __init__(self, cmds: List[Command], label: str = "macro"):
        self.cmds = cmds
        self.label = label

    def execute(self):
        for c in self.cmds:
            c.execute()

    def undo(self):
        for c in reversed(self.cmds):  # ← reverse order!
            c.undo()

    @property
    def name(self):
        return f"Macro<{self.label}>"


# ============================================================
# SECTION 6: CEREBELLAR COMPARATOR
# ============================================================
class CerebellarComparator:
    """So sánh expected (model dự đoán) vs actual (sensor); sinh correction."""
    def __init__(self, predictor: Callable[[Command], Any], tolerance: float = 0.5):
        self.predictor = predictor
        self.tolerance = tolerance

    def verify_and_correct(self, cmd: Command, arm: Arm) -> Optional[Command]:
        if isinstance(cmd, ReachCommand):
            expected = self.predictor(cmd)
            actual = arm.position
            error = sum(abs(e - a) for e, a in zip(expected, actual))
            if error > self.tolerance:
                # sinh correction command để bù lệch
                correction_target = tuple(2 * e - a for e, a in zip(expected, actual))
                return ReachCommand(arm=arm, target=correction_target)
        return None


# ============================================================
# DEMOS
# ============================================================
def demo_basic():
    print("=" * 64)
    print("DEMO 1 — Basic execute + undo")
    print("=" * 64)
    arm = Arm()
    bg = BasalGanglia()
    print(f"  Trước: {arm}")

    bg.submit(ReachCommand(arm, (10, 5, 0)))
    bg.submit(GripCommand(arm, "cup"))
    bg.step_all()
    print(f"  Sau execute: {arm}")
    print(f"  Replay log: {bg.replay_log_str()}")

    bg.undo_last()
    print(f"  Sau undo grip: {arm}")
    bg.undo_last()
    print(f"  Sau undo reach: {arm}")


def demo_macro():
    print()
    print("=" * 64)
    print("DEMO 2 — Macro: drink_water sequence")
    print("=" * 64)
    arm = Arm()
    bg = BasalGanglia()
    drink_water = MacroCommand([
        ReachCommand(arm, (10, 5, 0)),     # với tay tới ly
        GripCommand(arm, "cup"),            # nắm
        ReachCommand(arm, (0, 0, 5)),       # đưa lên miệng
        ReachCommand(arm, (10, 5, 0)),      # đặt xuống
        ReleaseCommand(arm),                # buông
    ], label="drink_water")

    bg.submit(drink_water)
    bg.step_all()
    print(f"  Sau drink_water: {arm}")

    bg.undo_last()
    print(f"  Sau undo macro: {arm}  (về trạng thái khởi đầu)")


def demo_comparator():
    print()
    print("=" * 64)
    print("DEMO 3 — Cerebellar comparator (correction khi overshoot)")
    print("=" * 64)
    arm = Arm()

    # Mô phỏng arm bị "ataxia": khi reach (x,y,z) → thực tế đi tới (x*1.3, y, z) (overshoot)
    class AtaxicArm(Arm):
        def set_position(self, p):
            super().set_position((p[0] * 1.3, p[1], p[2]))

    ataxic = AtaxicArm()
    target = (10.0, 5.0, 0.0)
    cmd = ReachCommand(ataxic, target)
    cmd.execute()
    print(f"  Target: {target}")
    print(f"  Actual sau reach: {ataxic.position}  (overshoot do ataxia)")

    cerebellum = CerebellarComparator(predictor=lambda c: c.target, tolerance=0.5)
    correction = cerebellum.verify_and_correct(cmd, ataxic)
    if correction:
        print(f"  Cerebellum sinh correction: target={correction.target}")
        correction.execute()
        # actual sẽ là target * 1.3 lại lệch nữa, nhưng demo idea
        print(f"  Sau correction: {ataxic.position}")
    print("  → Trong não thật, cerebellum học predictor (forward model) nên correction chính xác hơn theo thời gian.")


def demo_parkinson():
    print()
    print("=" * 64)
    print("DEMO 4 — Failure: Parkinson (invoker frozen)")
    print("=" * 64)
    arm = Arm()
    bg = BasalGanglia()
    bg.frozen = True  # mô phỏng

    bg.submit(ReachCommand(arm, (5, 5, 0)))
    bg.submit(GripCommand(arm, "cup"))
    bg.step_all()
    print(f"  Sau submit nhưng BG frozen: {arm}")
    print(f"  Replay log: {bg.replay_log_str()}")
    print("  → Bệnh nhân Parkinson biết muốn làm gì nhưng không initiate được.")


def demo_apraxia():
    print()
    print("=" * 64)
    print("DEMO 5 — Failure: Apraxia (command thiếu params đúng)")
    print("=" * 64)
    arm = Arm()
    bg = BasalGanglia()

    # Mô phỏng SMA hỏng: target bị scramble
    bad_cmd = ReachCommand(arm, target=(99, 99, 99))  # sai target
    bg.submit(bad_cmd)
    bg.step_all()
    print(f"  Bệnh nhân được bảo 'với tới ly nước (10,5,0)'")
    print(f"  Nhưng SMA encode target sai: {arm}")
    print("  → Apraxia: biết object, biết ý định, nhưng motor command sai.")


def demo_macro_undo_order():
    print()
    print("=" * 64)
    print("DEMO 6 — Failure: macro undo sai thứ tự")
    print("=" * 64)
    arm = Arm()

    class BadMacro(Command):
        def __init__(self, cmds): self.cmds = cmds
        def execute(self):
            for c in self.cmds: c.execute()
        def undo(self):
            for c in self.cmds: c.undo()  # ❌ không reverse

    seq = [
        ReachCommand(arm, (10, 0, 0)),
        GripCommand(arm, "cup"),
        ReachCommand(arm, (0, 0, 5)),
    ]
    bad = BadMacro(seq)
    bad.execute()
    print(f"  Sau execute: {arm}")

    try:
        bad.undo()  # sẽ thất bại vì undo Reach trước Reach mới chưa nhớ state đúng
        print(f"  Sau bad-undo: {arm}  ← state không quay đúng vị trí ban đầu")
    except Exception as e:
        print(f"  Lỗi: {e}")
    print("  → Bài học: undo macro phải reverse order.")


# ============================================================
# SECTION 8: ELLUMM — ActionCommand
# ============================================================
class MemoryStore:
    def __init__(self):
        self.episodes: dict = {}
    def write(self, key, data):
        self.episodes[key] = data
    def delete(self, key):
        return self.episodes.pop(key, None)
    def get(self, key):
        return self.episodes.get(key)


@dataclass
class EncodeMemoryCommand(Command):
    store: MemoryStore
    key: str
    data: dict
    _prev: Optional[Any] = field(default=None, init=False)

    def execute(self):
        self._prev = self.store.episodes.get(self.key)
        self.store.write(self.key, deepcopy(self.data))

    def undo(self):
        if self._prev is None:
            self.store.delete(self.key)
        else:
            self.store.write(self.key, self._prev)


@dataclass
class RecallCommand(Command):
    store: MemoryStore
    key: str
    result: Any = field(default=None, init=False)

    def execute(self):
        self.result = self.store.get(self.key)
    def undo(self):
        self.result = None  # read không cần undo, chỉ clear cache


def demo_ellumm():
    print()
    print("=" * 64)
    print("DEMO 7 — Ellumm: ActionCommand với undo + replay log")
    print("=" * 64)
    store = MemoryStore()
    bg = BasalGanglia()

    bg.submit(EncodeMemoryCommand(store, "ep_001", {"event": "saw dog", "salience": 0.7}))
    bg.submit(EncodeMemoryCommand(store, "ep_002", {"event": "ate apple", "salience": 0.3}))
    bg.submit(RecallCommand(store, "ep_001"))
    bg.step_all()

    print(f"  Store sau encode 2 episode: {list(store.episodes.keys())}")
    last_recall = bg.history[-1]
    print(f"  Recall ep_001 result: {last_recall.result}")

    bg.undo_last()  # undo recall
    bg.undo_last()  # undo encode ep_002
    print(f"  Sau 2 undo: {list(store.episodes.keys())}  (ep_002 đã rollback)")

    print(f"\n  Replay log đầy đủ:")
    for entry in bg.replay_log:
        print(f"    {entry}")


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    demo_basic()
    demo_macro()
    demo_comparator()
    demo_parkinson()
    demo_apraxia()
    demo_macro_undo_order()
    demo_ellumm()
    print()
    print("=" * 64)
    print("Lesson 14 — Command: COMPLETE")
    print("=" * 64)
