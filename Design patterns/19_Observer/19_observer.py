"""
Lesson 19 - Observer Pattern
Neuroscience analogy: Amygdala salience -> broadcast to HPA, motor, sensory, ...

Cau truc file:
  1. Interface Observer + base Subject (WeakSet, copy-on-iter, try/except per observer)
  2. Event class (frozen dataclass)
  3. Demo 1 - Amygdala broadcast: 6 downstream observer + chained subject
  4. Demo 2 - 4 failure modes (exception, leak, infinite loop, mutate event)
  5. Demo 3 - Ellumm LessonProgressPublisher (sync vs concurrent)
  6. Demo 4 - PFC circuit breaker: top-down suppress
"""

from __future__ import annotations

import gc
import logging
import time
import weakref
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any


logging.basicConfig(level=logging.WARNING, format="    [WARN] %(message)s")


# =============================================================================
# 1. Interface + base Subject
# =============================================================================
class Observer(ABC):
    @abstractmethod
    def update(self, event: "Event") -> None: ...


class Subject:
    def __init__(self, name: str = "Subject", use_weakref: bool = True):
        self.name = name
        self._observers: Any = weakref.WeakSet() if use_weakref else set()

    def attach(self, o: Observer) -> None:
        self._observers.add(o)

    def detach(self, o: Observer) -> None:
        self._observers.discard(o)

    def notify(self, event: "Event") -> None:
        for o in list(self._observers):
            try:
                o.update(event)
            except Exception as e:
                logging.warning(f"{type(o).__name__}.update fail: {e}")


# =============================================================================
# 2. Event
# =============================================================================
@dataclass(frozen=True)
class Event:
    kind: str
    salience: float = 0.0
    payload: Any = None
    depth: int = 0


# =============================================================================
# 3. Demo 1 - Amygdala salience broadcast
# =============================================================================
class HPAAxis(Observer):
    def update(self, event: Event) -> None:
        if event.salience >= 0.5:
            print(f"  [HPA]            cortisol release - sal={event.salience:.2f}")


class Insula(Observer):
    def update(self, event: Event) -> None:
        print(f"  [Insula]         interoception spike - heart rate up")


class MotorCortex(Observer):
    def update(self, event: Event) -> None:
        if event.salience >= 0.7:
            print(f"  [MotorCortex]   prepare fight/flight - high salience")
        else:
            print(f"  [MotorCortex]   alert level - readiness up")


class Hippocampus(Observer):
    def update(self, event: Event) -> None:
        print(f"  [Hippocampus]    encode episodic: {event.kind!r}")


class LocusCoeruleus(Observer, Subject):
    """Chained: Observer of amygdala AND Subject broadcasting NA to cortex."""
    def __init__(self):
        Subject.__init__(self, name="LocusCoeruleus")

    def update(self, event: Event) -> None:
        print(f"  [LocusCoeruleus] noradrenaline broadcast (cascade) ->")
        na = Event(kind="noradrenaline", salience=event.salience * 0.8,
                   payload="NA", depth=event.depth + 1)
        if na.depth > 5:
            return
        self.notify(na)


class SensoryCortex(Observer):
    def update(self, event: Event) -> None:
        print(f"      -> [SensoryCortex] sharpen attention (NA received)")


class WorkingMemory(Observer):
    def update(self, event: Event) -> None:
        print(f"      -> [WorkingMemory] hold context for next 30s")


class PFC(Observer):
    def update(self, event: Event) -> None:
        print(f"  [PFC]            evaluate context - sal={event.salience:.2f}")


class Amygdala(Subject):
    def __init__(self):
        super().__init__(name="Amygdala", use_weakref=False)

    def detect(self, stimulus: str, salience: float) -> None:
        print(f"\n  Amygdala detected: {stimulus!r} (salience={salience:.2f})")
        self.notify(Event(kind="salience", salience=salience, payload=stimulus, depth=0))


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_amygdala_broadcast() -> None:
    section("Demo 1 - Amygdala salience broadcast (1 -> 6 observer + chain)")
    amyg = Amygdala()
    hpa, insula, motor, hippo = HPAAxis(), Insula(), MotorCortex(), Hippocampus()
    lc = LocusCoeruleus()
    pfc = PFC()
    for o in (hpa, insula, motor, hippo, lc, pfc):
        amyg.attach(o)
    sensory, wmem = SensoryCortex(), WorkingMemory()
    lc.attach(sensory)
    lc.attach(wmem)

    amyg.detect("car_horn_close", salience=0.85)
    amyg.detect("siren_distant", salience=0.30)


# =============================================================================
# 4. Demo 2 - 4 failure modes
# =============================================================================
class CrashingObserver(Observer):
    def update(self, event: Event) -> None:
        raise ValueError("simulated crash in observer")


class CountingObserver(Observer):
    def __init__(self, name: str):
        self.name = name
        self.count = 0

    def update(self, event: Event) -> None:
        self.count += 1


class CycleA(Observer, Subject):
    def __init__(self):
        Subject.__init__(self, name="CycleA")

    def update(self, event: Event) -> None:
        if event.depth > 5:
            print(f"      [CycleA] depth={event.depth}, stop (anti infinite)")
            return
        print(f"  [CycleA] depth={event.depth} -> notify B")
        self.notify(Event(kind="ping", depth=event.depth + 1))


class CycleB(Observer, Subject):
    def __init__(self):
        Subject.__init__(self, name="CycleB")

    def update(self, event: Event) -> None:
        if event.depth > 5:
            return
        print(f"  [CycleB] depth={event.depth} -> notify A")
        self.notify(Event(kind="pong", depth=event.depth + 1))


def demo_failure_modes() -> None:
    section("Demo 2 - 4 failure modes")

    # 2a - Observer raise -> chain not killed
    print("\n[2a] Observer raise: chain not killed")
    s = Subject(use_weakref=False)
    a = CountingObserver("A")
    bad = CrashingObserver()
    c = CountingObserver("C")
    for x in (a, bad, c):
        s.attach(x)
    s.notify(Event(kind="t"))
    print(f"  count A={a.count} (1=ok), C={c.count} (1=ok despite bad raise)")

    # 2b - Memory leak: strong-ref vs WeakSet
    print("\n[2b] Memory leak: strong-ref Subject vs WeakSet")

    class Tmp(Observer):
        def update(self, event): pass

    s_strong = Subject(use_weakref=False)
    o1 = Tmp()
    o1_ref = weakref.ref(o1)
    s_strong.attach(o1)
    del o1
    gc.collect()
    print(f"  Strong-ref: observer alive = {o1_ref() is not None} <- LEAK")
    print(f"              s_strong size  = {len(list(s_strong._observers))}")

    s_weak = Subject(use_weakref=True)
    o2 = Tmp()
    o2_ref = weakref.ref(o2)
    s_weak.attach(o2)
    del o2
    gc.collect()
    print(f"  Weak-ref:   observer alive = {o2_ref() is not None} <- OK (GC'd)")
    print(f"              s_weak size    = {len(list(s_weak._observers))} (auto-cleaned)")

    # 2c - Infinite cascade -> depth limit
    print("\n[2c] Cycle A<->B with depth limit")
    a, b = CycleA(), CycleB()
    a.attach(b)
    b.attach(a)
    a.notify(Event(kind="start", depth=0))

    # 2d - Mutate event: frozen dataclass blocks
    print("\n[2d] Frozen event: observer cannot mutate")
    evt = Event(kind="x", salience=0.5)
    try:
        evt.salience = 0.9  # type: ignore
    except Exception as e:
        print(f"  OK {type(e).__name__}: {e}")


# =============================================================================
# 5. Demo 3 - Ellumm LessonProgressPublisher
# =============================================================================
@dataclass(frozen=True)
class LessonCompletedEvent(Event):
    kind: str = "lesson_completed"
    user_id: str = ""
    lesson_id: str = ""
    score: float = 0.0


class AchievementSystem(Observer):
    def update(self, event: Event) -> None:
        if isinstance(event, LessonCompletedEvent) and event.score >= 0.8:
            print(f"    [Achievement]  badge unlocked for {event.user_id}")


class NotificationService(Observer):
    def __init__(self, slow: bool = False):
        self.slow = slow

    def update(self, event: Event) -> None:
        if self.slow:
            time.sleep(0.2)
        uid = getattr(event, "user_id", "?")
        print(f"    [Notification] sent to {uid}")


class AnalyticsCollector(Observer):
    def update(self, event: Event) -> None:
        print(f"    [Analytics]    log event: {event.kind}")


class AdaptiveDifficulty(Observer):
    def update(self, event: Event) -> None:
        if isinstance(event, LessonCompletedEvent):
            print(f"    [AdaptiveDiff] recompute next lesson difficulty")


class SocialFeed(Observer):
    def update(self, event: Event) -> None:
        if isinstance(event, LessonCompletedEvent):
            print(f"    [SocialFeed]   post to friends feed")


class AsyncSubject(Subject):
    def __init__(self, max_workers: int = 8):
        super().__init__(name="AsyncSubject", use_weakref=False)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def notify(self, event: Event) -> None:
        snapshot = list(self._observers)
        futures = [self._executor.submit(self._safe_update, o, event) for o in snapshot]
        wait(futures)

    @staticmethod
    def _safe_update(o: Observer, event: Event) -> None:
        try:
            o.update(event)
        except Exception as e:
            logging.warning(f"{type(o).__name__}.update fail: {e}")

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


def demo_ellumm_progress_publisher() -> None:
    section("Demo 3 - Ellumm LessonProgressPublisher: sync vs concurrent")
    obs = [
        AchievementSystem(),
        NotificationService(slow=True),
        AnalyticsCollector(),
        AdaptiveDifficulty(),
        SocialFeed(),
    ]
    evt = LessonCompletedEvent(user_id="u1", lesson_id="19_Observer", score=0.92)

    print("\n[3a] SYNC notify:")
    sp = Subject(name="SyncPub", use_weakref=False)
    for o in obs:
        sp.attach(o)
    t0 = time.perf_counter()
    sp.notify(evt)
    print(f"  total = {(time.perf_counter() - t0) * 1000:.1f} ms")

    print("\n[3b] ASYNC notify (concurrent):")
    ap = AsyncSubject(max_workers=8)
    for o in obs:
        ap.attach(o)
    t0 = time.perf_counter()
    ap.notify(evt)
    print(f"  total = {(time.perf_counter() - t0) * 1000:.1f} ms")
    ap.shutdown()
    print("\n  Async ~ slowest observer; sync ~ sum.")


# =============================================================================
# 6. Demo 4 - PFC circuit breaker
# =============================================================================
class SuppressibleAmygdala(Subject):
    def __init__(self):
        super().__init__(name="Amygdala", use_weakref=False)
        self.suppressed = False

    def detect(self, stimulus: str, salience: float) -> None:
        if self.suppressed:
            print(f"  [Amygdala]  detection muted by PFC")
            return
        print(f"  [Amygdala]  detected {stimulus!r} (sal={salience:.2f})")
        self.notify(Event(kind="salience", salience=salience, payload=stimulus))


class PFCSuppressor(Observer):
    def __init__(self, amygdala: SuppressibleAmygdala, threshold_count: int = 2):
        self._amyg = amygdala
        self._false_alarms = 0
        self._threshold = threshold_count

    def update(self, event: Event) -> None:
        if "false_alarm" in str(event.payload):
            self._false_alarms += 1
            print(f"  [PFC]       false-alarm count = {self._false_alarms}")
            if self._false_alarms >= self._threshold:
                print(f"  [PFC]       -> SUPPRESS amygdala (top-down)")
                self._amyg.suppressed = True


def demo_pfc_suppress() -> None:
    section("Demo 4 - PFC circuit breaker: top-down suppress")
    amyg = SuppressibleAmygdala()
    pfc_supp = PFCSuppressor(amyg, threshold_count=2)
    for o in (HPAAxis(), MotorCortex(), pfc_supp):
        amyg.attach(o)

    print("\n  Event 1 - false alarm:")
    amyg.detect("siren_far_false_alarm", salience=0.6)
    print("\n  Event 2 - false alarm #2 -> PFC suppress:")
    amyg.detect("siren_far_false_alarm", salience=0.6)
    print("\n  Event 3 - real threat after suppress: muted")
    amyg.detect("real_threat", salience=0.95)


# =============================================================================
# 7. RUNNER
# =============================================================================
def main() -> None:
    demo_amygdala_broadcast()
    demo_failure_modes()
    demo_ellumm_progress_publisher()
    demo_pfc_suppress()
    print("\n" + "=" * 70)
    print("  Het demo Lesson 19 - Observer (Amygdala).")
    print("=" * 70)


if __name__ == "__main__":
    main()
