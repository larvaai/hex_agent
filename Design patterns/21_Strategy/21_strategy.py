"""
Lesson 21 - Strategy Pattern
Neuroscience analogy: LeDoux's dual-route fear (low road vs high road)

Cau truc file:
  1. Strategy interface + ConcreteStrategies + Context
  2. Demo 1 - ThreatDetector with LowRoad / HighRoad / Hybrid
  3. Demo 2 - 3 anti-patterns (hardcoded, shared mutable state, side effect)
  4. Demo 3 - Ellumm LessonRecommendationEngine with 3 strategies
  5. Demo 4 - Closure as strategy (Pythonic alternative)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol


# =============================================================================
# 1. Domain types
# =============================================================================
@dataclass(frozen=True)
class Stimulus:
    visual_features: tuple   # e.g. ("long", "curved", "static")
    motion: str = "none"     # "none" | "slow" | "sudden"
    location: str = "ground"


@dataclass(frozen=True)
class ThreatDecision:
    level: float        # 0..1
    confidence: float   # 0..1
    latency_ms: float
    reason: str = ""


# =============================================================================
# 2. Strategy interface (Protocol-style; class hoac function deu satisfy)
# =============================================================================
class ThreatStrategy(Protocol):
    def __call__(self, stim: Stimulus) -> ThreatDecision: ...


# Class-based strategies
class LowRoadStrategy:
    """Fast pattern match: thalamus -> amygdala. ~12ms, accuracy thap."""
    LATENCY_MS = 12.0

    def __call__(self, stim: Stimulus) -> ThreatDecision:
        # Thicker pattern matching: chi can vai feature trigger
        snake_features = {"long", "curved"}
        if snake_features.issubset(set(stim.visual_features)) or stim.motion == "sudden":
            return ThreatDecision(
                level=0.85, confidence=0.4, latency_ms=self.LATENCY_MS,
                reason="low road: matched 'snake_shape' or sudden motion"
            )
        return ThreatDecision(
            level=0.0, confidence=0.4, latency_ms=self.LATENCY_MS,
            reason="low road: no shape/motion trigger"
        )


class HighRoadStrategy:
    """Full cortical parse + memory + PFC eval. ~300ms, accuracy cao."""
    LATENCY_MS = 300.0

    def __init__(self, episodic_memory: Optional[Dict[str, str]] = None):
        # Don't share mutable state: cap qua constructor.
        # Episodic: feature_signature -> known_label
        # Keys: sorted(features) + "," + motion (if not none) + "@" + location
        self.memory = episodic_memory or {
            "curved,long,static@ground": "stick",
            "curved,long,sudden@ground": "snake",
            "coiled,long,static@ground": "rope",
        }

    def __call__(self, stim: Stimulus) -> ThreatDecision:
        sig = ",".join(sorted(stim.visual_features)) + "@" + stim.location
        # Match motion when relevant
        sig_with_motion = ",".join(sorted(stim.visual_features)) + ("," + stim.motion if stim.motion != "none" else "") + "@" + stim.location
        label = self.memory.get(sig_with_motion) or self.memory.get(sig, "unknown")
        if label == "snake":
            return ThreatDecision(0.95, 0.95, self.LATENCY_MS, f"high road: identified as 'snake'")
        if label in ("stick", "rope"):
            return ThreatDecision(0.05, 0.95, self.LATENCY_MS, f"high road: identified as '{label}', not threat")
        return ThreatDecision(0.5, 0.6, self.LATENCY_MS, f"high road: unknown shape, moderate uncertainty")


class HybridStrategy:
    """Run low first; if level > 0.5 then escalate to high (verify)."""

    def __init__(self, low: ThreatStrategy, high: ThreatStrategy):
        self.low = low
        self.high = high

    def __call__(self, stim: Stimulus) -> ThreatDecision:
        decision = self.low(stim)
        if decision.level > 0.5:
            # Escalate
            verified = self.high(stim)
            return ThreatDecision(
                level=verified.level,
                confidence=verified.confidence,
                latency_ms=decision.latency_ms + verified.latency_ms,
                reason=f"hybrid: low triggered ({decision.reason}) -> high verified ({verified.reason})"
            )
        return decision


# =============================================================================
# 3. Context
# =============================================================================
class ThreatDetector:
    def __init__(self, strategy: ThreatStrategy):
        self._strategy = strategy

    def set_strategy(self, s: ThreatStrategy) -> None:
        self._strategy = s

    def detect(self, stim: Stimulus) -> ThreatDecision:
        return self._strategy(stim)


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# =============================================================================
# 4. Demo 1 - ThreatDetector with 3 strategies
# =============================================================================
def demo_threat_detector() -> None:
    section("Demo 1 - ThreatDetector: low road / high road / hybrid")

    stimuli = [
        Stimulus(("long", "curved"), motion="static", location="ground"),    # stick
        Stimulus(("long", "curved"), motion="sudden", location="ground"),    # snake!
        Stimulus(("long", "coiled"), motion="static", location="ground"),    # rope
        Stimulus(("short", "round"), motion="none",   location="ground"),    # stone (no threat)
    ]

    low = LowRoadStrategy()
    high = HighRoadStrategy()
    hybrid = HybridStrategy(low, high)

    detector = ThreatDetector(strategy=low)
    for stim in stimuli:
        print(f"\n  Stimulus: {stim.visual_features} motion={stim.motion}")
        for name, strat in [("low", low), ("high", high), ("hybrid", hybrid)]:
            detector.set_strategy(strat)
            d = detector.detect(stim)
            print(f"    [{name:6s}] level={d.level:.2f} conf={d.confidence:.2f} "
                  f"lat={d.latency_ms:6.1f}ms  {d.reason}")


# =============================================================================
# 5. Demo 2 - Anti-patterns
# =============================================================================
def demo_antipattern_hardcoded() -> None:
    section("Demo 2a - Anti-pattern: hardcoded selection (defeats DI)")

    class BadDetector:
        """if/elif on mode string instead of injecting Strategy."""
        def __init__(self, mode: str):
            self.mode = mode  # "low" | "high" | "hybrid"

        def detect(self, stim: Stimulus) -> ThreatDecision:
            if self.mode == "low":
                # Inline 30 lines of low-road logic...
                return ThreatDecision(0.85, 0.4, 12, "inline low")
            elif self.mode == "high":
                # Inline 30 lines of high-road logic...
                return ThreatDecision(0.5, 0.95, 300, "inline high")
            elif self.mode == "hybrid":
                # Inline 50 lines of hybrid logic...
                return ThreatDecision(0.85, 0.95, 312, "inline hybrid")
            else:
                raise ValueError(f"unknown mode {self.mode!r}")

    print("\n  BadDetector mixes selection + logic in one class.")
    print("  Adding 'EmotionPrimedStrategy' = modify BadDetector (Open/Closed violated).")
    print("  Cannot test strategies in isolation.")
    print("  Fix: inject Strategy via constructor; selection logic in Factory/registry outside.")


def demo_antipattern_shared_state() -> None:
    section("Demo 2b - Anti-pattern: shared mutable state between strategies")

    # WRONG: module-level counter
    _shared_calls = {"low": 0, "high": 0}

    class BadLowStrategy:
        def __call__(self, stim):
            _shared_calls["low"] += 1  # leak!
            return ThreatDecision(0.85, 0.4, 12, f"call #{_shared_calls['low']}")

    class BadHighStrategy:
        def __call__(self, stim):
            _shared_calls["high"] += 1
            return ThreatDecision(0.5, 0.95, 300, f"call #{_shared_calls['high']}")

    print("\n  Two strategies sharing _shared_calls dict.")
    print("  -> Race condition in concurrent context.")
    print("  -> Test isolation broken: order of tests changes counter values.")
    print("  Fix: each strategy holds OWN state, or state lives in Context.")


def demo_antipattern_side_effect() -> None:
    section("Demo 2c - Anti-pattern: strategy with side effect")

    class BadStrategyWithSideEffect:
        def __call__(self, stim):
            # WRONG: write to DB / send email inside strategy
            print("    [SIDE EFFECT] sending alert to ops...")
            return ThreatDecision(0.85, 0.4, 12, "fired alert as side effect")

    print("\n  Strategy executes side effect (alert ops) inside __call__.")
    print("  -> Cannot test without mocking ops system.")
    print("  -> Replay = duplicate alerts.")
    print("  Fix: return INTENT (e.g. AlertIntent), Context decides whether to fire.")
    print("       'Functional core, imperative shell'.")


def demo_failure_modes() -> None:
    demo_antipattern_hardcoded()
    demo_antipattern_shared_state()
    demo_antipattern_side_effect()


# =============================================================================
# 6. Demo 3 - Ellumm LessonRecommendationEngine
# =============================================================================
@dataclass(frozen=True)
class Lesson:
    id: int
    title: str
    pattern_category: str   # "Creational" | "Structural" | "Behavioral"
    difficulty: int         # 1..5

@dataclass
class UserProfile:
    user_id: str
    completed_lessons: List[int] = field(default_factory=list)
    quiz_scores: Dict[int, float] = field(default_factory=dict)  # lesson_id -> score


class RecommendationStrategy(Protocol):
    def __call__(self, user: UserProfile, all_lessons: List[Lesson]) -> List[Lesson]: ...


class PopularityStrategy:
    """Top-N theo popularity (gia lap)."""
    def __init__(self, popularity_map: Dict[int, int]):
        self.popularity_map = popularity_map

    def __call__(self, user, all_lessons):
        not_done = [l for l in all_lessons if l.id not in user.completed_lessons]
        return sorted(not_done, key=lambda l: -self.popularity_map.get(l.id, 0))[:3]


class PersonalizedStrategy:
    """Recommend lesson cung category voi cac lesson user hoan thanh."""
    def __call__(self, user, all_lessons):
        completed = [l for l in all_lessons if l.id in user.completed_lessons]
        liked_categories = {l.pattern_category for l in completed}
        if not liked_categories:
            return []  # cold start
        candidates = [l for l in all_lessons
                      if l.id not in user.completed_lessons
                      and l.pattern_category in liked_categories]
        return candidates[:3]


class SkillGapStrategy:
    """Recommend lesson cung category voi cac lesson user score thap."""
    def __call__(self, user, all_lessons):
        if not user.quiz_scores:
            return []
        weak_lessons = [lid for lid, score in user.quiz_scores.items() if score < 0.7]
        weak_cats = {l.pattern_category for l in all_lessons if l.id in weak_lessons}
        candidates = [l for l in all_lessons
                      if l.id not in user.completed_lessons
                      and l.pattern_category in weak_cats]
        return sorted(candidates, key=lambda l: l.difficulty)[:3]


class RecommendationEngine:
    """Context co adaptive selection."""

    def __init__(self,
                 popularity: RecommendationStrategy,
                 personalized: RecommendationStrategy,
                 skill_gap: RecommendationStrategy):
        self.popularity = popularity
        self.personalized = personalized
        self.skill_gap = skill_gap

    def pick_strategy(self, user: UserProfile) -> tuple[str, RecommendationStrategy]:
        """Adaptive: chon strategy theo data co san."""
        if len(user.completed_lessons) == 0:
            return ("popularity", self.popularity)  # cold start
        if user.quiz_scores and len(user.quiz_scores) >= 2:
            return ("skill_gap", self.skill_gap)
        return ("personalized", self.personalized)

    def recommend(self, user: UserProfile, all_lessons: List[Lesson]):
        name, strat = self.pick_strategy(user)
        return name, strat(user, all_lessons)


def demo_ellumm_recommendation() -> None:
    section("Demo 3 - Ellumm LessonRecommendation: 3 strategies, adaptive selection")

    all_lessons = [
        Lesson(1, "Singleton",        "Creational", 2),
        Lesson(2, "Builder",          "Creational", 3),
        Lesson(3, "Factory Method",   "Creational", 3),
        Lesson(4, "Prototype",        "Creational", 4),
        Lesson(5, "Adapter",          "Structural", 2),
        Lesson(6, "Decorator",        "Structural", 3),
        Lesson(7, "Facade",           "Structural", 2),
        Lesson(8, "Iterator",         "Behavioral", 3),
        Lesson(9, "State",            "Behavioral", 4),
        Lesson(10, "Strategy",        "Behavioral", 3),
        Lesson(11, "Visitor",         "Behavioral", 5),
    ]
    popularity_map = {1: 100, 2: 30, 3: 50, 4: 20, 5: 80, 6: 90, 7: 60, 8: 70, 9: 40, 10: 75, 11: 20}

    engine = RecommendationEngine(
        popularity=PopularityStrategy(popularity_map),
        personalized=PersonalizedStrategy(),
        skill_gap=SkillGapStrategy(),
    )

    users = [
        UserProfile("cold_start"),
        UserProfile("structural_fan",
                    completed_lessons=[5, 6],
                    quiz_scores={}),
        UserProfile("weak_in_creational",
                    completed_lessons=[1],
                    quiz_scores={1: 0.5, 2: 0.4}),
    ]

    for u in users:
        name, recs = engine.recommend(u, all_lessons)
        rec_titles = [l.title for l in recs]
        print(f"\n  {u.user_id}:")
        print(f"    completed = {u.completed_lessons}, scores = {u.quiz_scores}")
        print(f"    chosen strategy = {name}")
        print(f"    recommended    = {rec_titles}")


# =============================================================================
# 7. Demo 4 - Closure as strategy (Pythonic)
# =============================================================================
def demo_closure_strategy() -> None:
    section("Demo 4 - Closure as strategy (Pythonic alternative)")

    # Strategy = function. Khong can class.
    paranoid_low = lambda s: ThreatDecision(0.99, 0.4, 12, "paranoid: assume threat")
    chill_low    = lambda s: ThreatDecision(0.0,  0.4, 12, "chill: ignore everything")

    # Co the parametrize bang closure
    def threshold_strategy(threshold: float) -> ThreatStrategy:
        def detect(s: Stimulus) -> ThreatDecision:
            score = 0.85 if "curved" in s.visual_features else 0.0
            return ThreatDecision(score, 0.5, 12,
                                  f"closure threshold={threshold}, score={score}")
        return detect

    detector = ThreatDetector(strategy=paranoid_low)
    s = Stimulus(("long", "curved"), motion="static")
    print(f"\n  Stimulus: {s.visual_features}")

    for name, strat in [
        ("paranoid_low", paranoid_low),
        ("chill_low", chill_low),
        ("threshold(0.5)", threshold_strategy(0.5)),
        ("threshold(0.9)", threshold_strategy(0.9)),
    ]:
        detector.set_strategy(strat)
        d = detector.detect(s)
        print(f"    [{name:18s}] level={d.level:.2f}  {d.reason}")

    print("\n  -> Functions/closures are first-class. No class needed for simple strategies.")


# =============================================================================
# RUNNER
# =============================================================================
def main() -> None:
    demo_threat_detector()
    demo_failure_modes()
    demo_ellumm_recommendation()
    demo_closure_strategy()
    print("\n" + "=" * 70)
    print("  Het demo Lesson 21 - Strategy (Dual-route fear).")
    print("=" * 70)


if __name__ == "__main__":
    main()
