"""
Lesson 20 - State Pattern
Neuroscience analogy: Sleep stages (Wake / NREM1 / NREM2 / NREM3 / REM)

Cau truc file:
  1. State interface + Context (SleepCycleBrain)
  2. 5 ConcreteStates: Wake, NREM1, NREM2, NREM3, REM
  3. Demo 1 - sleep cycle simulation, stimulus injection
  4. Demo 2 - failure modes (if/elif anti-pattern, lock-in, invalid transition)
  5. Demo 3 - Ellumm LessonViewState with guards
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# =============================================================================
# 1. State interface + Context
# =============================================================================
class SleepState(ABC):
    name: str = "?"

    def on_enter(self, ctx: "SleepCycleBrain") -> None:
        pass

    def on_exit(self, ctx: "SleepCycleBrain") -> None:
        pass

    @abstractmethod
    def process_stimulus(self, ctx: "SleepCycleBrain", stim: "Stimulus") -> None: ...

    @abstractmethod
    def tick(self, ctx: "SleepCycleBrain", dt: float) -> None: ...


@dataclass(frozen=True)
class Stimulus:
    kind: str        # "sound", "light", "alarm"
    loudness: float  # 0..1


class SleepCycleBrain:
    """Context. Giu state hien tai + cycle metadata."""

    def __init__(self, initial: "SleepState"):
        self._state: SleepState = initial
        self.in_state_time: float = 0.0
        self.cycle_count: int = 0
        self.nrem3_done_this_cycle: bool = False
        self.atonia: bool = False
        self.glymphatic_active: bool = False
        self.dreaming: bool = False
        self.history: List[str] = [initial.name]
        self._state.on_enter(self)

    def set_state(self, new: "SleepState") -> None:
        if new is self._state:
            return
        try:
            self._state.on_exit(self)
        except Exception as e:
            print(f"  [WARN] on_exit raise: {e} (continuing transition)")
        prev = self._state
        self._state = new
        self.in_state_time = 0.0
        self.history.append(new.name)
        print(f"    transition: {prev.name} -> {new.name}")
        self._state.on_enter(self)

    def handle_stimulus(self, stim: Stimulus) -> None:
        self._state.process_stimulus(self, stim)

    def tick(self, dt: float) -> None:
        self.in_state_time += dt
        self._state.tick(self, dt)


# =============================================================================
# 2. ConcreteStates - Singletons (stateless, tiet kiem memory)
# =============================================================================
class WakeState(SleepState):
    name = "Wake"

    def on_enter(self, ctx: SleepCycleBrain) -> None:
        ctx.atonia = False
        ctx.glymphatic_active = False
        ctx.dreaming = False
        print(f"  [Wake]   on_enter: full motor, sensory active")

    def process_stimulus(self, ctx: SleepCycleBrain, stim: Stimulus) -> None:
        print(f"  [Wake]   react fully to {stim.kind} (loudness={stim.loudness:.2f})")

    def tick(self, ctx: SleepCycleBrain, dt: float) -> None:
        # Sleep pressure builds; after 16h awake -> fall asleep
        # Demo: fall asleep after just 3 ticks
        if ctx.in_state_time >= 3.0:
            ctx.set_state(NREM1)


class NREM1State(SleepState):
    name = "NREM1"

    def on_enter(self, ctx: SleepCycleBrain) -> None:
        ctx.atonia = False
        print(f"  [NREM1]  on_enter: theta waves, easy to wake")

    def process_stimulus(self, ctx: SleepCycleBrain, stim: Stimulus) -> None:
        if stim.loudness >= 0.3:
            print(f"  [NREM1]  loud stim ({stim.loudness:.2f}) -> wake")
            ctx.set_state(WAKE)
        else:
            print(f"  [NREM1]  quiet stim, drift deeper")

    def tick(self, ctx: SleepCycleBrain, dt: float) -> None:
        if ctx.in_state_time >= 2.0:
            ctx.set_state(NREM2)


class NREM2State(SleepState):
    name = "NREM2"

    def on_enter(self, ctx: SleepCycleBrain) -> None:
        ctx.atonia = False
        print(f"  [NREM2]  on_enter: sleep spindles + K-complex (declarative consolidation)")

    def process_stimulus(self, ctx: SleepCycleBrain, stim: Stimulus) -> None:
        if stim.loudness >= 0.6:
            print(f"  [NREM2]  loud stim -> wake")
            ctx.set_state(WAKE)
        elif stim.loudness >= 0.3:
            print(f"  [NREM2]  K-complex response, no wake")

    def tick(self, ctx: SleepCycleBrain, dt: float) -> None:
        # First half of cycle: go deeper to NREM3.
        # Second half (after NREM3 done): go to REM.
        if ctx.in_state_time >= 3.0:
            if not ctx.nrem3_done_this_cycle:
                ctx.set_state(NREM3)
            else:
                ctx.set_state(REM)


class NREM3State(SleepState):
    name = "NREM3"

    def on_enter(self, ctx: SleepCycleBrain) -> None:
        ctx.atonia = False
        ctx.glymphatic_active = True
        print(f"  [NREM3]  on_enter: delta waves, GLYMPHATIC clearance, GH release")

    def on_exit(self, ctx: SleepCycleBrain) -> None:
        ctx.glymphatic_active = False
        ctx.nrem3_done_this_cycle = True
        print(f"  [NREM3]  on_exit: glymphatic done (procedural memory consolidated)")

    def process_stimulus(self, ctx: SleepCycleBrain, stim: Stimulus) -> None:
        if stim.loudness >= 0.85:
            print(f"  [NREM3]  VERY loud ({stim.loudness:.2f}) -> wake (rare)")
            ctx.set_state(WAKE)
        else:
            print(f"  [NREM3]  ignore stim (deep sleep, hard to rouse)")

    def tick(self, ctx: SleepCycleBrain, dt: float) -> None:
        if ctx.in_state_time >= 4.0:
            ctx.set_state(NREM2)  # back up to NREM2 before REM


class REMState(SleepState):
    name = "REM"

    def on_enter(self, ctx: SleepCycleBrain) -> None:
        ctx.atonia = True   # paralysis!
        ctx.dreaming = True
        print(f"  [REM]    on_enter: ATONIA (motor paralysis), vivid dreaming")

    def on_exit(self, ctx: SleepCycleBrain) -> None:
        ctx.atonia = False
        ctx.dreaming = False
        ctx.nrem3_done_this_cycle = False  # reset for next cycle
        print(f"  [REM]    on_exit: atonia released, emotional integration done")

    def process_stimulus(self, ctx: SleepCycleBrain, stim: Stimulus) -> None:
        if stim.loudness >= 0.7:
            print(f"  [REM]    very loud -> wake")
            ctx.set_state(WAKE)
        else:
            print(f"  [REM]    incorporate {stim.kind!r} into dream narrative")

    def tick(self, ctx: SleepCycleBrain, dt: float) -> None:
        if ctx.in_state_time >= 3.0:
            ctx.cycle_count += 1
            print(f"    [cycle #{ctx.cycle_count} complete]")
            ctx.set_state(NREM2)  # back to NREM2, start next cycle


# Singletons
WAKE = WakeState()
NREM1 = NREM1State()
NREM2 = NREM2State()
NREM3 = NREM3State()
REM = REMState()


# =============================================================================
# 3. Demo 1 - Sleep cycle simulation
# =============================================================================
def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_sleep_cycle() -> None:
    section("Demo 1 - Sleep cycle: Wake -> NREM1->2->3->2 -> REM -> ...")
    brain = SleepCycleBrain(initial=WAKE)
    print(f"\n  Initial state: {brain._state.name}")

    # Simulate 25 ticks - should go through ~2 cycles
    print("\n  Simulating with stimulus injections at strategic moments:")
    stim_schedule = {
        2:  Stimulus("phone_buzz", 0.2),   # in Wake
        5:  Stimulus("door_close", 0.4),   # in NREM1 - should wake
        12: Stimulus("dog_bark",   0.5),   # in NREM2 - K-complex
        16: Stimulus("loud_truck", 0.7),   # in NREM3 - might not wake
        22: Stimulus("alarm_soft", 0.3),   # in REM - dream incorporation
    }
    for t in range(25):
        if t in stim_schedule:
            print(f"\n  tick={t}: stimulus {stim_schedule[t]}")
            brain.handle_stimulus(stim_schedule[t])
        brain.tick(dt=1.0)

    print(f"\n  History: {' -> '.join(brain.history)}")
    print(f"  Cycles completed: {brain.cycle_count}")


# =============================================================================
# 4. Demo 2 - Failure modes
# =============================================================================
def demo_if_elif_antipattern() -> None:
    section("Demo 2a - if/elif anti-pattern (de minh hoa, khong dung production)")

    class IfElifBrain:
        STAGES = ("wake", "nrem1", "nrem2", "nrem3", "rem")

        def __init__(self):
            self.stage = "wake"
            self.atonia = False
            self.glymphatic_active = False

        def process_stimulus(self, stim_loud: float) -> None:
            # Logic of all 5 states stuffed here
            if self.stage == "wake":
                print(f"    [wake]  react fully")
            elif self.stage == "nrem1":
                if stim_loud >= 0.3:
                    self.stage = "wake"; print(f"    [nrem1] -> wake")
            elif self.stage == "nrem2":
                if stim_loud >= 0.6:
                    self.stage = "wake"
            elif self.stage == "nrem3":
                if stim_loud >= 0.85:
                    self.stage = "wake"
            elif self.stage == "rem":
                if stim_loud >= 0.7:
                    self.stage = "wake"
            else:
                raise ValueError(f"Unknown stage {self.stage!r}")

        # And now imagine 4 more methods like this... each with same if/elif
        # Adding "Hypnagogic" state means modifying ALL methods.

    print("\n  IfElifBrain.process_stimulus: 1 method, 5 branches.")
    print("  Adding 'Hypnagogic' state -> must modify EVERY method (Open/Closed violated).")
    print("  With 5 states x 4 methods = 20 branches across the class.")
    print("  -> Use State pattern instead.")


def demo_lock_in() -> None:
    section("Demo 2b - State lock-in: forgotten transition")

    class StuckState(SleepState):
        name = "Stuck"

        def process_stimulus(self, ctx, stim): print("  [Stuck] received stim, but cannot transition")
        def tick(self, ctx, dt): pass  # Forgot to ever set_state!

    brain = SleepCycleBrain(initial=StuckState())
    for _ in range(10):
        brain.tick(1.0)
    print(f"  After 10 ticks, state = {brain._state.name} (locked in)")
    print("  Fix: every state's tick() must eventually have a transition path,")
    print("       OR be a designed terminal state (e.g. 'Cancelled').")


def demo_invalid_transition() -> None:
    section("Demo 2c - Invalid transition: REM from Wake (narcolepsy analog)")

    class GuardedBrain(SleepCycleBrain):
        ALLOWED: Dict[str, set] = {
            "Wake":  {"NREM1"},
            "NREM1": {"Wake", "NREM2"},
            "NREM2": {"NREM1", "NREM3", "REM", "Wake"},
            "NREM3": {"NREM2", "Wake"},
            "REM":   {"NREM2", "Wake"},
        }

        def set_state(self, new: SleepState) -> None:
            if new.name not in self.ALLOWED.get(self._state.name, set()):
                raise ValueError(f"Invalid: {self._state.name} -> {new.name}")
            super().set_state(new)

    brain = GuardedBrain(initial=WAKE)
    print("\n  Try Wake -> REM directly (narcolepsy):")
    try:
        brain.set_state(REM)
    except ValueError as e:
        print(f"  OK guard caught: {e}")

    print("\n  Valid path Wake -> NREM1:")
    brain.set_state(NREM1)
    print(f"  state = {brain._state.name}")


def demo_failure_modes() -> None:
    demo_if_elif_antipattern()
    demo_lock_in()
    demo_invalid_transition()


# =============================================================================
# 5. Demo 3 - Ellumm LessonViewState with guards + entry/exit
# =============================================================================
@dataclass
class LessonContext:
    lesson_id: str
    read_progress: float = 0.0   # 0..1
    quiz_score: Optional[float] = None
    state_name: str = "Idle"
    audit_log: List[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.audit_log.append(msg)
        print(f"    [audit] {msg}")


class ViewState(ABC):
    name: str = "?"

    @abstractmethod
    def can_enter(self, ctx: LessonContext) -> Tuple[bool, str]: ...

    def on_enter(self, ctx: LessonContext) -> None:
        ctx.log(f"enter {self.name}")

    def on_exit(self, ctx: LessonContext) -> None:
        ctx.log(f"exit {self.name}")


class IdleState(ViewState):
    name = "Idle"
    def can_enter(self, ctx): return (True, "")


class ReadingState(ViewState):
    name = "Reading"
    def can_enter(self, ctx): return (True, "")


class QuizState(ViewState):
    name = "Quiz"
    def can_enter(self, ctx):
        if ctx.read_progress < 0.9:
            return (False, f"must read >=90%, currently {ctx.read_progress:.0%}")
        return (True, "")


class ReviewingState(ViewState):
    name = "Reviewing"
    def can_enter(self, ctx):
        if ctx.quiz_score is None:
            return (False, "must complete Quiz first")
        return (True, "")


class CompletedState(ViewState):
    name = "Completed"
    def can_enter(self, ctx):
        if ctx.quiz_score is None or ctx.quiz_score < 0.7:
            return (False, f"need score >=0.7, have {ctx.quiz_score}")
        return (True, "")


class LessonView:
    def __init__(self, lesson_id: str):
        self.ctx = LessonContext(lesson_id=lesson_id)
        self._state: ViewState = IdleState()
        self.ctx.state_name = self._state.name
        self._state.on_enter(self.ctx)

    def transition_to(self, new: ViewState) -> None:
        ok, reason = new.can_enter(self.ctx)
        if not ok:
            print(f"  REJECTED transition {self._state.name} -> {new.name}: {reason}")
            return
        self._state.on_exit(self.ctx)
        self._state = new
        self.ctx.state_name = new.name
        new.on_enter(self.ctx)


def demo_ellumm_lessonview() -> None:
    section("Demo 3 - Ellumm LessonViewState (guards + entry/exit)")
    view = LessonView("20_State")
    print()

    print("  Try Quiz before reading (rejected):")
    view.transition_to(QuizState())

    print("\n  Reading...")
    view.transition_to(ReadingState())
    view.ctx.read_progress = 0.95
    print(f"  read_progress = {view.ctx.read_progress:.0%}")

    print("\n  Now Quiz (allowed):")
    view.transition_to(QuizState())
    view.ctx.quiz_score = 0.85
    print(f"  quiz_score = {view.ctx.quiz_score}")

    print("\n  Reviewing:")
    view.transition_to(ReviewingState())

    print("\n  Completed (score 0.85 >= 0.7 OK):")
    view.transition_to(CompletedState())

    print("\n  Audit log:")
    for line in view.ctx.audit_log:
        print(f"    - {line}")


# =============================================================================
# RUNNER
# =============================================================================
def main() -> None:
    demo_sleep_cycle()
    demo_failure_modes()
    demo_ellumm_lessonview()
    print("\n" + "=" * 70)
    print("  Het demo Lesson 20 - State (Sleep stages).")
    print("=" * 70)


if __name__ == "__main__":
    main()
