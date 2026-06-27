"""
Lesson 05 — Prototype Pattern
Ví dụ neuroscience: motor template + mirror neuron — não clone template hành động
đã học (reach_and_grasp, avoid_threat, ...) thay vì rebuild from scratch
mỗi lần thực hiện. Apraxia = "Prototype Registry hỏng".

File này triển khai 6 phần:
    A. ANTI-PATTERN — rebuild motor program từ raw primitives
    B. MotorTemplate (Prototype) với __deepcopy__ override
    C. Demo shallow vs deep copy bug
    D. PrototypeRegistry với 4 template
    E. Demo apraxia (registry miss / template corruption)
    F. Ellumm: BehavioralTemplateLibrary
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Any, Optional


# =============================================================================
# A. ANTI-PATTERN — rebuild from scratch mỗi lần
# =============================================================================
# Chỉ để minh họa nỗi đau. Trong thực tế, "build motor program" có thể là:
# - load từ disk (chậm)
# - chạy expensive optimization (chậm)
# - require multi-step coordination assembly (dài, dễ sai)

def build_motor_program_from_scratch(action: str, target: tuple) -> dict:
    """Giả lập rebuild from scratch — chậm và dễ duplication."""
    # ... 100+ dòng coordination logic ...
    # Mỗi lần gọi = re-derive từ đầu, không tận dụng template đã có
    return {
        "action": action,
        "muscle_groups": ["biceps", "deltoid", "wrist_flexors"],
        "target": target,
        "coordination_matrix": {"phase_0": [0.1, 0.2, 0.3], "phase_1": [0.4, 0.5, 0.6]},
        # ... rất nhiều field nữa được derive lại mỗi lần
    }


# =============================================================================
# B. PROTOTYPE — MotorTemplate với deep-copy control
# =============================================================================

@dataclass
class CoordinationMatrix:
    """Nested mutable state — đây là chỗ shallow vs deep copy quan trọng."""
    phases: dict[str, list[float]] = field(default_factory=dict)

    def add_phase(self, name: str, weights: list[float]) -> None:
        self.phases[name] = weights


@dataclass
class MotorTemplate:
    """
    Prototype của một motor program đã được học.
    Lưu trong premotor cortex / cerebellum / basal ganglia (analogy).
    """
    name: str
    muscle_groups: list[str] = field(default_factory=list)
    coordination_matrix: CoordinationMatrix = field(default_factory=CoordinationMatrix)
    target_position: Optional[tuple] = None
    grip_type: str = "neutral"
    learning_rate: float = 0.05
    # Reference tới một global lookup table — KHÔNG nên deep copy
    # (immutable + shared toàn hệ)
    GLOBAL_REFLEX_TABLE: dict[str, Any] = field(default_factory=lambda: _GLOBAL_REFLEX)

    def __deepcopy__(self, memo: dict) -> "MotorTemplate":
        """
        Override để CHỦ ĐỘNG kiểm soát: cái nào deep, cái nào share.
        Đây là khác biệt giữa "Prototype dùng được" và "Prototype có bug".
        """
        # Tạo instance mới, chỉ copy những field cần độc lập
        new = MotorTemplate(
            name=self.name,                                        # str → immutable, ok
            muscle_groups=copy.deepcopy(self.muscle_groups, memo), # MUTABLE → deep
            coordination_matrix=copy.deepcopy(self.coordination_matrix, memo),  # nested → deep
            target_position=self.target_position,                  # tuple → immutable, ok
            grip_type=self.grip_type,                              # str → immutable, ok
            learning_rate=self.learning_rate,                      # float → immutable, ok
        )
        # CỐ TÌNH share GLOBAL_REFLEX_TABLE — không deep copy
        new.GLOBAL_REFLEX_TABLE = self.GLOBAL_REFLEX_TABLE
        memo[id(self)] = new
        return new

    def clone(self) -> "MotorTemplate":
        """API rõ ràng cho client — gọi deepcopy với memo dict."""
        return copy.deepcopy(self)

    def execute(self) -> str:
        return (f"Executing '{self.name}' towards {self.target_position} "
                f"with grip={self.grip_type}, muscles={self.muscle_groups}")


# Global lookup table — tất cả template share, không deep copy
_GLOBAL_REFLEX = {
    "withdraw_pain": "spinal_reflex_arc",
    "blink": "facial_nerve_reflex",
}


# =============================================================================
# C. DEMO SHALLOW vs DEEP — bug kinh điển
# =============================================================================

def demo_shallow_vs_deep() -> None:
    print("=" * 64)
    print("C. SHALLOW vs DEEP COPY — bug kinh điển của Prototype")
    print("=" * 64)

    # Tạo template gốc
    template = MotorTemplate(
        name="reach_and_grasp",
        muscle_groups=["biceps", "deltoid", "wrist_flexors"],
    )
    template.coordination_matrix.add_phase("phase_0", [0.1, 0.2, 0.3])

    # --- SHALLOW COPY: dùng copy.copy() ---
    plan_shallow_A = copy.copy(template)
    plan_shallow_B = copy.copy(template)

    # Tweak plan_shallow_A
    plan_shallow_A.muscle_groups.append("triceps")     # ⚠️ SHARED reference
    plan_shallow_A.coordination_matrix.add_phase("phase_1", [0.4, 0.5, 0.6])

    print("\n  SHALLOW COPY — sau khi tweak plan_shallow_A:")
    print(f"    template.muscle_groups: {template.muscle_groups}")
    print(f"    plan_shallow_A.muscle_groups: {plan_shallow_A.muscle_groups}")
    print(f"    plan_shallow_B.muscle_groups: {plan_shallow_B.muscle_groups}")
    print(f"    template.coord.phases keys: {list(template.coordination_matrix.phases.keys())}")
    print("    ⚠️ Cả 3 cùng bị thay đổi — đây là BUG: shallow share nested mutable.")

    # Reset cho demo deep
    template2 = MotorTemplate(
        name="reach_and_grasp",
        muscle_groups=["biceps", "deltoid", "wrist_flexors"],
    )
    template2.coordination_matrix.add_phase("phase_0", [0.1, 0.2, 0.3])

    # --- DEEP COPY (qua clone()) ---
    plan_deep_A = template2.clone()
    plan_deep_B = template2.clone()
    plan_deep_A.muscle_groups.append("triceps")
    plan_deep_A.coordination_matrix.add_phase("phase_1", [0.4, 0.5, 0.6])

    print("\n  DEEP COPY (clone()) — sau khi tweak plan_deep_A:")
    print(f"    template2.muscle_groups: {template2.muscle_groups}")
    print(f"    plan_deep_A.muscle_groups: {plan_deep_A.muscle_groups}")
    print(f"    plan_deep_B.muscle_groups: {plan_deep_B.muscle_groups}")
    print(f"    template2.coord.phases keys: {list(template2.coordination_matrix.phases.keys())}")
    print("    ✓ Prototype và clone B không bị ảnh hưởng — đúng kỳ vọng.")

    # GLOBAL_REFLEX_TABLE cố ý share — verify
    print(f"\n  Shared global ref: id(template2.GLOBAL_REFLEX_TABLE) == "
          f"id(plan_deep_A.GLOBAL_REFLEX_TABLE) ? "
          f"{id(template2.GLOBAL_REFLEX_TABLE) == id(plan_deep_A.GLOBAL_REFLEX_TABLE)}")
    print("    → Cố tình share (read-only global) — tiết kiệm bộ nhớ.")


# =============================================================================
# D. PROTOTYPE REGISTRY
# =============================================================================

class TemplateNotFound(Exception):
    """Apraxia tương đương trong code — registry không tìm thấy template."""


class PrototypeRegistry:
    """
    Lưu các prototype có tên. Client lookup by name + clone.
    Trong não, đây là motor template library ở premotor cortex/cerebellum.
    """
    def __init__(self) -> None:
        self._templates: dict[str, MotorTemplate] = {}

    def register(self, name: str, template: MotorTemplate) -> None:
        self._templates[name] = template

    def get(self, name: str) -> MotorTemplate:
        if name not in self._templates:
            # Đây là apraxia: biết muốn làm gì, nhưng không clone được template
            raise TemplateNotFound(
                f"Template '{name}' không có trong registry. "
                f"(Sinh học: ideomotor apraxia — IPL/SMA tổn thương)"
            )
        return self._templates[name].clone()        # luôn deep clone

    def list_names(self) -> list[str]:
        return list(self._templates.keys())


# =============================================================================
# F. ELLUMM — BehavioralTemplateLibrary
# =============================================================================

@dataclass
class BehavioralProgram:
    """Template hành vi cấp cao trong Ellumm — tổ hợp cảm xúc + motor + learning."""
    name: str
    emotion_response_curve: list[float]      # mutable, deep clone
    motor_activation: dict[str, float]       # mutable, deep clone
    learning_rate_modifier: float = 1.0      # immutable
    encoding_priority: float = 0.5           # immutable
    target_stimulus: Optional[Any] = None    # set khi clone

    def clone(self) -> "BehavioralProgram":
        return copy.deepcopy(self)

    def execute(self) -> str:
        peak_motor = max(self.motor_activation.items(), key=lambda kv: kv[1])
        return (f"[{self.name}] target={self.target_stimulus}, "
                f"peak motor: {peak_motor[0]}={peak_motor[1]:.2f}, "
                f"emotion peak: {max(self.emotion_response_curve):.2f}")


class BehavioralTemplateLibrary:
    """Registry behavioral template trong Ellumm."""
    def __init__(self) -> None:
        self._lib: dict[str, BehavioralProgram] = {}
        self._populate_defaults()

    def _populate_defaults(self) -> None:
        self._lib["approach_food"] = BehavioralProgram(
            name="approach_food",
            emotion_response_curve=[0.2, 0.5, 0.7, 0.6, 0.4],   # tăng arousal khi tiếp cận
            motor_activation={"forelimb_reach": 0.8, "head_orient": 0.9, "leg_step": 0.6},
            learning_rate_modifier=1.5,
            encoding_priority=0.6,
        )
        self._lib["avoid_threat"] = BehavioralProgram(
            name="avoid_threat",
            emotion_response_curve=[0.3, 0.8, 0.95, 0.9, 0.7],
            motor_activation={"leg_retract": 0.95, "head_turn": 0.85, "freeze_briefly": 0.7},
            learning_rate_modifier=2.5,            # học nhanh hơn cho aversive
            encoding_priority=0.95,
        )
        self._lib["explore_novel"] = BehavioralProgram(
            name="explore_novel",
            emotion_response_curve=[0.4, 0.5, 0.5, 0.45, 0.4],
            motor_activation={"head_scan": 0.7, "approach_slow": 0.5, "sniff": 0.6},
            learning_rate_modifier=1.2,
            encoding_priority=0.5,
        )
        self._lib["freeze_predator"] = BehavioralProgram(
            name="freeze_predator",
            emotion_response_curve=[0.95, 0.9, 0.85, 0.8, 0.75],
            motor_activation={"all_motor_inhibit": 0.99, "diaphragm_quiet": 0.9},
            learning_rate_modifier=3.0,
            encoding_priority=1.0,
        )

    def get(self, name: str, **tweaks) -> BehavioralProgram:
        if name not in self._lib:
            raise TemplateNotFound(f"BehavioralProgram '{name}' không có")
        program = self._lib[name].clone()
        for k, v in tweaks.items():
            setattr(program, k, v)
        return program


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    demo_shallow_vs_deep()

    print()
    print("=" * 64)
    print("D. PROTOTYPE REGISTRY — motor template library")
    print("=" * 64)

    registry = PrototypeRegistry()
    # Setup library với 3 template đã học
    reach_template = MotorTemplate(
        name="reach_and_grasp", grip_type="power",
        muscle_groups=["biceps", "deltoid", "wrist_flexors"],
    )
    reach_template.coordination_matrix.add_phase("transport", [0.3, 0.7, 1.0, 0.8, 0.4])
    reach_template.coordination_matrix.add_phase("grasp", [0.0, 0.2, 0.6, 0.9, 1.0])
    registry.register("reach_and_grasp_power", reach_template)

    precision_template = MotorTemplate(
        name="precision_grip", grip_type="precision",
        muscle_groups=["thumb_opponens", "index_flexor", "FDS"],
    )
    precision_template.coordination_matrix.add_phase("transport", [0.4, 0.6, 0.7, 0.5, 0.3])
    registry.register("precision_grip", precision_template)

    avoid_template = MotorTemplate(
        name="withdraw_hand", grip_type="none",
        muscle_groups=["biceps_rapid", "deltoid_post"],
    )
    avoid_template.coordination_matrix.add_phase("withdraw", [1.0, 0.9, 0.5, 0.1])
    registry.register("withdraw_hand_fast", avoid_template)

    print(f"  Registry chứa: {registry.list_names()}")

    # Clone + tùy biến cho situation cụ thể
    print("\n  Tình huống: cốc cà phê ở (0.4, 0.2, 0.1)")
    plan = registry.get("reach_and_grasp_power")
    plan.target_position = (0.4, 0.2, 0.1)
    print(f"    {plan.execute()}")

    print("\n  Tình huống: cầm bút ở (0.3, 0.1, 0.05)")
    plan2 = registry.get("precision_grip")
    plan2.target_position = (0.3, 0.1, 0.05)
    print(f"    {plan2.execute()}")

    print("\n  Tình huống: chạm vật nóng → withdraw")
    plan3 = registry.get("withdraw_hand_fast")
    plan3.target_position = None
    print(f"    {plan3.execute()}")

    # Verify template gốc không bị tweak
    print(f"\n  Template gốc 'reach_and_grasp_power'.target_position: "
          f"{registry._templates['reach_and_grasp_power'].target_position} (None — không bị thay đổi ✓)")

    print()
    print("=" * 64)
    print("E. APRAXIA SIMULATION — template không tồn tại")
    print("=" * 64)
    try:
        bad = registry.get("brush_teeth_complex_sequence")
    except TemplateNotFound as e:
        print(f"  ✓ {e}")
        print("  → Trong não thật: bệnh nhân biết muốn làm, có sức cơ, ")
        print("    nhưng route 'intention → clone template' bị đứt.")

    print()
    print("=" * 64)
    print("F. ELLUMM — BehavioralTemplateLibrary với clone + tweak")
    print("=" * 64)
    library = BehavioralTemplateLibrary()

    # Stimulus 1: thấy thức ăn ở (2, 0)
    program1 = library.get("approach_food", target_stimulus="apple_at_2_0")
    print(f"  Stimulus 1: {program1.execute()}")

    # Stimulus 2: nghe tiếng động lớn → avoid
    program2 = library.get("avoid_threat", target_stimulus="loud_bang_left")
    program2.motor_activation["leg_retract"] = 1.0       # tweak: max urgency
    print(f"  Stimulus 2: {program2.execute()}")

    # Stimulus 3: vật mới → explore
    program3 = library.get("explore_novel", target_stimulus="unfamiliar_object")
    print(f"  Stimulus 3: {program3.execute()}")

    # Verify template gốc không bị tweak
    fresh_avoid = library.get("avoid_threat")
    print(f"\n  Template 'avoid_threat' gốc, leg_retract: "
          f"{fresh_avoid.motor_activation['leg_retract']} (0.95 — không bị thay đổi ✓)")

    print()
    print("=" * 64)
    print("RUNTIME EXTENSIBILITY — thêm template mới mà không sửa code")
    print("=" * 64)
    new_template = BehavioralProgram(
        name="play_with_juvenile",
        emotion_response_curve=[0.5, 0.6, 0.7, 0.65, 0.5],
        motor_activation={"approach_gentle": 0.6, "vocalize_short": 0.5, "head_tilt": 0.4},
        learning_rate_modifier=1.0,
        encoding_priority=0.4,
    )
    library._lib["play_with_juvenile"] = new_template       # register runtime
    program4 = library.get("play_with_juvenile", target_stimulus="puppy_in_view")
    print(f"  Stimulus 4 (template mới): {program4.execute()}")
    print("  ✓ Thêm 'play_with_juvenile' không sửa class, không restart engine.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN: KHI NÀO PROTOTYPE THỰC SỰ TỎA SÁNG
# =============================================================================
#
# 1. ĐẮT KHI CONSTRUCT
#    - Object load từ DB/network/file lớn → cache 1 prototype, clone n lần.
#    - Object qua expensive optimization (ML model setup, motor planning) →
#      "warmed-up instance" làm prototype.
#
# 2. NHIỀU VARIANT CẤU HÌNH
#    - 1 base "config" + nhiều variant nhỏ → đỡ class hierarchy bùng nổ.
#    - Game NPC: 1 base enemy template, clone với tweak (HP, damage, color).
#    - Test fixtures: 1 setup template, clone cho mỗi test case.
#
# 3. RUNTIME EXTENSIBILITY
#    - User/admin có thể tạo "loại mới" mà không cần dev sửa code +
#      redeploy. Chỉ cần register prototype mới vào registry.
#    - CMS template, Photoshop brush preset, motor library trong robotics.
#
# 4. HOT-RELOAD
#    - Tweak prototype → mọi clone tương lai phản ánh thay đổi.
#    - Game balancing, ML hyperparameter tuning, behavioral evolution.
#
# CÁI BẪY LỚN NHẤT: deep vs shallow.
# ─────────────────────────────────
# Nếu bạn không override __deepcopy__ và prototype có nested mutable
# (list, dict, custom class với mutable fields), `copy.copy()` sẽ gây bug
# share-state ngầm.
#
# Quy tắc: khi viết Prototype, ngồi xuống liệt kê TỪNG field — đánh dấu
# "deep" hay "share". Override __deepcopy__ nếu logic không trivial.
# Test bằng cách clone 2 instance, modify 1, assert cái kia không thay đổi.
"""
"""
