# -*- coding: utf-8 -*-
"""
Lesson 13 — Chain of Responsibility
Analogy: Pain pathway — nociceptor → spinal cord → brainstem → thalamus → cortex.

Cấu trúc:
  Section 1: Anti-pattern (mega switch-case)
  Section 2: Handler base + Outcome contract
  Section 3: Concrete handlers (5 tầng pain pathway)
  Section 4: Demo các scenario:
    - Pain bình thường → đi qua hết chain
    - Pain cường độ cao + Aδ-fiber → spinal reflex trigger nhưng vẫn forward
    - Combat mode → brainstem inhibit
    - Aβ-fiber active (touch) → gate control STOP ở tủy
  Section 5: Failure case — quên forward, chain cycle
  Section 6: Extension — thêm OpioidGate
  Section 7: Ellumm — stimulus processing chain
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List


# ============================================================
# SECTION 1: ANTI-PATTERN
# ============================================================
def handle_pain_naive(signal: dict) -> dict:
    """❌ Mega switch-case — vi phạm SRP, khó extend."""
    if signal.get('intensity', 0) > 9 and signal.get('fiber') == 'A_delta':
        signal['reflex'] = True
    if signal.get('combat_mode'):
        signal['intensity'] *= 0.3
    if signal.get('A_beta_active'):
        signal['gated'] = True
        return signal
    if signal.get('intensity', 0) > 0:
        signal['perceived'] = True
    return signal


# ============================================================
# SECTION 2: SIGNAL + OUTCOME + HANDLER BASE
# ============================================================
@dataclass
class PainSignal:
    intensity: float           # 0-10
    fiber_type: str            # 'A_delta' (sharp) / 'C' (dull) / 'A_beta' (touch)
    location: str              # 'finger' / 'foot' / ...
    A_beta_active: bool = False  # touch concurrent → gate
    combat_mode: bool = False
    opioid_active: bool = False
    # Handler trace
    reflex_triggered: bool = False
    log: List[str] = field(default_factory=list)


@dataclass
class Outcome:
    signal: PainSignal
    terminated: bool = False
    final_handler: Optional[str] = None


class PainHandler(ABC):
    """Base class với fluent set_next + skeleton handle."""
    def __init__(self):
        self._next: Optional[PainHandler] = None

    def set_next(self, h: 'PainHandler') -> 'PainHandler':
        self._next = h
        return h  # cho phép fluent chain

    def handle(self, sig: PainSignal) -> Outcome:
        outcome = self._handle(sig)
        if outcome.terminated:
            outcome.final_handler = type(self).__name__
            return outcome
        if self._next:
            return self._next.handle(outcome.signal)
        outcome.final_handler = type(self).__name__
        return outcome

    @abstractmethod
    def _handle(self, sig: PainSignal) -> Outcome: ...


# ============================================================
# SECTION 3: CONCRETE HANDLERS
# ============================================================
class GateControl(PainHandler):
    """Aβ-fiber (touch) gate pain ở dorsal horn — Melzack & Wall 1965."""
    def _handle(self, sig):
        if sig.A_beta_active and sig.intensity < 8:
            sig.log.append("GateControl: A_beta gates pain → STOP")
            return Outcome(signal=sig, terminated=True)
        sig.log.append("GateControl: pass")
        return Outcome(signal=sig, terminated=False)


class SpinalReflex(PainHandler):
    """Reflex withdraw nếu pain cường độ cao + sharp."""
    def _handle(self, sig):
        if sig.intensity > 8 and sig.fiber_type == 'A_delta':
            sig.reflex_triggered = True
            sig.log.append(f"SpinalReflex: TRIGGER WITHDRAW ({sig.location})")
        else:
            sig.log.append("SpinalReflex: no reflex")
        return Outcome(signal=sig, terminated=False)  # vẫn forward


class BrainstemModulator(PainHandler):
    """PAG/RVM descending inhibition — combat mode hoặc opioid."""
    def _handle(self, sig):
        if sig.combat_mode or sig.opioid_active:
            old = sig.intensity
            sig.intensity *= 0.3
            sig.log.append(f"BrainstemModulator: inhibit {old:.1f}→{sig.intensity:.1f}")
        else:
            sig.log.append("BrainstemModulator: no inhibit")
        return Outcome(signal=sig, terminated=False)


class ThalamicRelay(PainHandler):
    """VPL — relay đơn thuần."""
    def _handle(self, sig):
        if sig.intensity < 1.5:
            sig.log.append(f"ThalamicRelay: subthreshold ({sig.intensity:.1f}<1.5) → STOP")
            return Outcome(signal=sig, terminated=True)
        sig.log.append("ThalamicRelay: forward to cortex")
        return Outcome(signal=sig, terminated=False)


class CorticalProcessor(PainHandler):
    """S1 + ACC + Insula — perceive pain."""
    def _handle(self, sig):
        sig.log.append(
            f"CorticalProcessor: PERCEIVED — loc={sig.location}, intensity={sig.intensity:.1f}, "
            f"sharp={sig.fiber_type=='A_delta'}"
        )
        return Outcome(signal=sig, terminated=True)


# ============================================================
# Build standard chain
# ============================================================
def build_pain_chain() -> PainHandler:
    head = GateControl()
    head.set_next(SpinalReflex()).set_next(BrainstemModulator()) \
        .set_next(ThalamicRelay()).set_next(CorticalProcessor())
    return head


# ============================================================
# SECTION 4: DEMOS
# ============================================================
def print_log(label, sig):
    print(f"\n  [{label}]")
    for line in sig.log:
        print(f"    {line}")
    print(f"    final: reflex={sig.reflex_triggered}, intensity={sig.intensity:.1f}")


def demo_normal_pain():
    print("=" * 64)
    print("DEMO 1 — Pain bình thường (chạm lò nóng)")
    print("=" * 64)
    chain = build_pain_chain()
    sig = PainSignal(intensity=9.0, fiber_type='A_delta', location='right_hand')
    chain.handle(sig)
    print_log("hot stove", sig)


def demo_gate_control():
    print()
    print("=" * 64)
    print("DEMO 2 — Gate control (xoa chỗ đau → giảm pain)")
    print("=" * 64)
    chain = build_pain_chain()
    sig = PainSignal(intensity=5.0, fiber_type='C', location='leg', A_beta_active=True)
    chain.handle(sig)
    print_log("rub the bruise", sig)


def demo_combat_mode():
    print()
    print("=" * 64)
    print("DEMO 3 — Combat mode (descending inhibition)")
    print("=" * 64)
    chain = build_pain_chain()
    sig = PainSignal(intensity=7.0, fiber_type='A_delta', location='shoulder', combat_mode=True)
    chain.handle(sig)
    print_log("wounded in combat", sig)


def demo_subthreshold():
    print()
    print("=" * 64)
    print("DEMO 4 — Subthreshold sau brainstem inhibit (terminate ở thalamus)")
    print("=" * 64)
    chain = build_pain_chain()
    sig = PainSignal(intensity=4.0, fiber_type='C', location='back', opioid_active=True)
    chain.handle(sig)
    print_log("opioid active", sig)


# ============================================================
# SECTION 5: FAILURE CASES
# ============================================================
def demo_forget_forward():
    print()
    print("=" * 64)
    print("DEMO 5 — Failure: handler quên forward (request bị nuốt)")
    print("=" * 64)

    class BadHandler(PainHandler):
        def _handle(self, sig):
            sig.log.append("BadHandler: 'forgot' to terminate or forward properly")
            return Outcome(signal=sig, terminated=True)  # cố ý terminate

    bad = BadHandler()
    bad.set_next(CorticalProcessor())
    sig = PainSignal(intensity=8, fiber_type='A_delta', location='hand')
    bad.handle(sig)
    print_log("bad chain", sig)
    print("  → CorticalProcessor không bao giờ được gọi → não không biết bệnh nhân đau.")


def demo_cycle_protection():
    print()
    print("=" * 64)
    print("DEMO 6 — Failure: chain cycle → infinite recursion (mô phỏng có guard)")
    print("=" * 64)

    class GuardedHandler(PainHandler):
        _max_depth = 10
        def handle(self, sig, _depth=0):
            if _depth > self._max_depth:
                sig.log.append(f"{type(self).__name__}: CYCLE DETECTED → break")
                return Outcome(signal=sig, terminated=True)
            outcome = self._handle(sig)
            if outcome.terminated: return outcome
            if self._next:
                return self._next.handle(outcome.signal, _depth + 1) \
                    if isinstance(self._next, GuardedHandler) else self._next.handle(outcome.signal)
            return outcome
        def _handle(self, sig):
            sig.log.append(f"{type(self).__name__}: pass")
            return Outcome(signal=sig, terminated=False)

    class A(GuardedHandler): pass
    class B(GuardedHandler): pass
    a, b = A(), B()
    a._next = b
    b._next = a  # cycle
    sig = PainSignal(intensity=5, fiber_type='C', location='x')
    a.handle(sig)
    print_log("cycle a↔b", sig)


# ============================================================
# SECTION 6: EXTENSION (Open-Closed)
# ============================================================
class OpioidGate(PainHandler):
    """Insert được vào chain mà KHÔNG sửa các handler khác."""
    def _handle(self, sig):
        if sig.opioid_active and sig.intensity < 6:
            sig.log.append("OpioidGate: opioid blocks moderate pain → STOP")
            return Outcome(signal=sig, terminated=True)
        sig.log.append("OpioidGate: pass")
        return Outcome(signal=sig, terminated=False)


def demo_extension():
    print()
    print("=" * 64)
    print("DEMO 7 — Extension: thêm OpioidGate vào chain (Open-Closed)")
    print("=" * 64)
    head = GateControl()
    head.set_next(OpioidGate()).set_next(SpinalReflex()) \
        .set_next(BrainstemModulator()).set_next(ThalamicRelay()) \
        .set_next(CorticalProcessor())
    sig = PainSignal(intensity=5.5, fiber_type='C', location='back', opioid_active=True)
    head.handle(sig)
    print_log("with OpioidGate", sig)


# ============================================================
# SECTION 7: ELLUMM — Stimulus processing chain
# ============================================================
@dataclass
class Stimulus:
    content: str
    novelty: float = 0.5     # 0-1
    salience: float = 0.5
    valence: float = 0.0
    encoded: bool = False
    log: List[str] = field(default_factory=list)


class StimulusHandler(ABC):
    def __init__(self):
        self._next: Optional[StimulusHandler] = None
    def set_next(self, h):
        self._next = h
        return h
    def handle(self, s: Stimulus) -> Stimulus:
        terminated = self._handle(s)
        if terminated: return s
        if self._next: return self._next.handle(s)
        return s
    @abstractmethod
    def _handle(self, s: Stimulus) -> bool: ...


class NoveltyFilter(StimulusHandler):
    def _handle(self, s):
        if s.novelty < 0.2:
            s.log.append(f"NoveltyFilter: too familiar (novelty={s.novelty}) → DROP")
            return True
        s.log.append(f"NoveltyFilter: novel enough ({s.novelty}) → pass")
        return False


class SalienceFilter(StimulusHandler):
    def _handle(self, s):
        if s.salience < 0.3:
            s.log.append(f"SalienceFilter: low salience ({s.salience}) → DROP")
            return True
        s.log.append(f"SalienceFilter: salient ({s.salience}) → pass")
        return False


class EmotionalAmplifier(StimulusHandler):
    def _handle(self, s):
        if abs(s.valence) > 0.5:
            s.salience = min(1.0, s.salience * 1.5)
            s.log.append(f"EmotionalAmplifier: |valence|={abs(s.valence)} → boost salience to {s.salience:.2f}")
        else:
            s.log.append("EmotionalAmplifier: neutral, no boost")
        return False


class MemoryEncoder(StimulusHandler):
    def _handle(self, s):
        if s.salience > 0.5:
            s.encoded = True
            s.log.append(f"MemoryEncoder: ENCODED (final salience={s.salience:.2f})")
        else:
            s.log.append(f"MemoryEncoder: skipped (salience={s.salience:.2f}<0.5)")
        return True  # always terminal


def demo_ellumm():
    print()
    print("=" * 64)
    print("DEMO 8 — Ellumm: stimulus processing chain")
    print("=" * 64)
    head = NoveltyFilter()
    head.set_next(SalienceFilter()).set_next(EmotionalAmplifier()).set_next(MemoryEncoder())

    cases = [
        Stimulus("wall is white", novelty=0.05, salience=0.1),
        Stimulus("usual coffee mug", novelty=0.4, salience=0.2),
        Stimulus("snake on path", novelty=0.9, salience=0.6, valence=-0.9),
        Stimulus("birthday surprise", novelty=0.85, salience=0.4, valence=0.8),
    ]
    for c in cases:
        head.handle(c)
        print(f"\n  Stimulus: '{c.content}' → encoded={c.encoded}")
        for line in c.log:
            print(f"    {line}")


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    demo_normal_pain()
    demo_gate_control()
    demo_combat_mode()
    demo_subthreshold()
    demo_forget_forward()
    demo_cycle_protection()
    demo_extension()
    demo_ellumm()
    print()
    print("=" * 64)
    print("Lesson 13 — Chain of Responsibility: COMPLETE")
    print("=" * 64)
