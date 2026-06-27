"""
Lesson 25 - Open/Closed Principle (OCP)
Neuroscience analogy: synaptic plasticity + DG pattern separation + adult neurogenesis
                      -> add new without overwriting old.

Cau truc file:
  PART 1 - Domain types (Question, ScoreResult)
  PART 2 - Abstract QuizScorer + 2 impl tu lesson 24 (Standard, NegativeMarking)
  PART 3 - 2 scorer MOI (Weighted, PartialCredit) - extension, 0 sua class cu
  PART 4 - Decorator: TimePenaltyDecorator (cross-cutting)
  PART 5 - Notifier hierarchy: Email + Sms + Push + Composite (fanout)
  PART 6 - Anti-example: OcpViolationScorer (if/elif tren type tag) - LAM SAO
  PART 7 - Plugin Registry: ScorerRegistry decorator-based
  PART 8 - 5 demo:
        1. Add 2 scorer moi: 0 file cu thay doi
        2. Decorator chain: TimePenalty(NegativeMarking) + TimePenalty(Standard)
        3. Anti-example doi chieu: file count + line count
        4. Composite notifier fanout
        5. Registry-driven instantiation tu config string

Chay:
    python 25_ocp.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Set, Type


# =============================================================================
# PART 1 - Domain types
# =============================================================================

@dataclass(frozen=True)
class Question:
    qid: str
    correct_answer: str
    weight: float = 1.0  # Standard scorer ignores; WeightedScorer uses


@dataclass(frozen=True)
class ScoreResult:
    points: float
    total: float

    @property
    def percent(self) -> float:
        return (self.points / self.total) * 100 if self.total else 0.0


# =============================================================================
# PART 2 - Abstract QuizScorer + 2 impl tu lesson 24
# =============================================================================
# Interface DONG: signature score(answers) -> ScoreResult.
# Khi them variant moi, KHONG SUA interface, KHONG SUA impl cu.

class QuizScorer(ABC):
    @abstractmethod
    def score(self, answers: Dict[str, str]) -> ScoreResult:
        """Cham diem. Khong duoc raise tru ngoai trach hop khai bao."""
        ...


class StandardScorer(QuizScorer):
    """1 diem moi cau dung. Tu lesson 24 - khong sua."""

    def __init__(self, answer_key: Dict[str, str]):
        self.answer_key = answer_key

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        points = sum(
            1.0 for q, correct in self.answer_key.items()
            if answers.get(q) == correct
        )
        return ScoreResult(points=points, total=float(len(self.answer_key)))


class NegativeMarkingScorer(QuizScorer):
    """+1 dung, -0.25 sai. Tu lesson 24 - khong sua."""

    def __init__(self, answer_key: Dict[str, str]):
        self.answer_key = answer_key

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        raw = 0.0
        for q, correct in self.answer_key.items():
            given = answers.get(q)
            if given == correct:
                raw += 1.0
            elif given is not None:
                raw -= 0.25
        return ScoreResult(points=max(0.0, raw), total=float(len(self.answer_key)))


# =============================================================================
# PART 3 - 2 scorer MOI - dung OCP: them class moi, KHONG sua class cu
# =============================================================================

class WeightedScorer(QuizScorer):
    """Moi cau co weight rieng. Cau cuoi quan trong hon -> weight cao hon."""

    def __init__(self, questions: List[Question]):
        self.questions = questions

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        earned = sum(
            q.weight for q in self.questions
            if answers.get(q.qid) == q.correct_answer
        )
        total = sum(q.weight for q in self.questions)
        return ScoreResult(points=earned, total=total)


class PartialCreditScorer(QuizScorer):
    """Multi-select: cho diem ti le |chosen ∩ correct| / |correct|.
    answers la Dict[qid, str voi cac option phan cach boi ',']."""

    def __init__(self, answer_keys: Dict[str, Set[str]]):
        # qid -> set of correct options (e.g. {"A", "C"})
        self.answer_keys = answer_keys

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        total = 0.0
        for qid, correct_set in self.answer_keys.items():
            given = answers.get(qid, "")
            chosen_set = {opt.strip() for opt in given.split(",") if opt.strip()}
            if not correct_set:
                continue
            ratio = len(chosen_set & correct_set) / len(correct_set)
            # Penalize wrong picks: subtract them proportionally
            wrong_picks = len(chosen_set - correct_set)
            ratio = max(0.0, ratio - wrong_picks / len(correct_set))
            total += ratio
        return ScoreResult(points=total, total=float(len(self.answer_keys)))


# =============================================================================
# PART 4 - Decorator pattern (cross-cutting OCP)
# =============================================================================
# TimePenaltyDecorator wrap BAT KY scorer nao. Khong sua interface, khong sua impl.

class TimePenaltyDecorator(QuizScorer):
    """Tru diem theo thoi gian tre. Wrap inner scorer."""

    def __init__(self, inner: QuizScorer, time_taken_sec: float,
                 max_sec: float, penalty_per_minute_late: float = 0.5):
        self.inner = inner
        self.time_taken_sec = time_taken_sec
        self.max_sec = max_sec
        self.penalty_per_minute_late = penalty_per_minute_late

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        result = self.inner.score(answers)
        if self.time_taken_sec <= self.max_sec:
            return result
        late_minutes = (self.time_taken_sec - self.max_sec) / 60.0
        penalty = late_minutes * self.penalty_per_minute_late
        adjusted = max(0.0, result.points - penalty)
        return ScoreResult(points=adjusted, total=result.total)


# =============================================================================
# PART 5 - Notifier hierarchy + Composite
# =============================================================================

class Notifier(Protocol):
    def notify(self, user_id: str, result: ScoreResult) -> None: ...


class EmailNotifier:
    def __init__(self):
        self.outbox: List[str] = []

    def notify(self, user_id: str, result: ScoreResult) -> None:
        self.outbox.append(
            f"EMAIL -> {user_id}: {result.points:.2f}/{result.total:.2f} "
            f"({result.percent:.0f}%)"
        )


class SmsNotifier:
    """Class MOI - khong sua EmailNotifier."""

    def __init__(self):
        self.outbox: List[str] = []

    def notify(self, user_id: str, result: ScoreResult) -> None:
        self.outbox.append(
            f"SMS -> {user_id}: Score {result.points:.1f}/{result.total:.1f}"
        )


class PushNotifier:
    """Class MOI - khong sua EmailNotifier hay SmsNotifier."""

    def __init__(self):
        self.outbox: List[str] = []

    def notify(self, user_id: str, result: ScoreResult) -> None:
        self.outbox.append(
            f"PUSH -> {user_id}: You scored {result.percent:.0f}%! Tap to see details."
        )


class CompositeNotifier:
    """Fanout: 1 call -> nhieu notifier. Themed: them notifier moi 0 sua method."""

    def __init__(self, *notifiers: Notifier):
        self.notifiers = list(notifiers)

    def notify(self, user_id: str, result: ScoreResult) -> None:
        for n in self.notifiers:
            n.notify(user_id, result)


# =============================================================================
# PART 6 - ANTI-EXAMPLE: vi pham OCP voi if/elif tren type tag
# =============================================================================
# DAY LA STYLE TE - dung de doi chieu. KHONG copy.

class OcpViolationScorer:
    """if/elif tren quiz_type. Moi yeu cau moi = sua method ngay duoi day."""

    def __init__(self, answer_key: Dict[str, str],
                 weights: Optional[Dict[str, float]] = None,
                 partial_keys: Optional[Dict[str, Set[str]]] = None):
        # Param signature phinh theo so loai - them loai moi them param
        self.answer_key = answer_key
        self.weights = weights or {}
        self.partial_keys = partial_keys or {}

    def score(self, quiz_type: str, answers: Dict[str, str]) -> ScoreResult:
        # ----- Method nay PHAI SUA moi khi them quiz_type -----
        if quiz_type == "standard":
            points = sum(
                1.0 for q, c in self.answer_key.items()
                if answers.get(q) == c
            )
            return ScoreResult(points=points, total=float(len(self.answer_key)))
        elif quiz_type == "negative":
            raw = 0.0
            for q, c in self.answer_key.items():
                g = answers.get(q)
                if g == c:
                    raw += 1.0
                elif g is not None:
                    raw -= 0.25
            return ScoreResult(points=max(0.0, raw), total=float(len(self.answer_key)))
        elif quiz_type == "weighted":
            earned = sum(
                self.weights.get(q, 1.0) for q, c in self.answer_key.items()
                if answers.get(q) == c
            )
            total = sum(self.weights.get(q, 1.0) for q in self.answer_key)
            return ScoreResult(points=earned, total=total)
        elif quiz_type == "partial_credit":
            total = 0.0
            for qid, correct_set in self.partial_keys.items():
                given = answers.get(qid, "")
                chosen_set = {o.strip() for o in given.split(",") if o.strip()}
                if not correct_set:
                    continue
                ratio = len(chosen_set & correct_set) / len(correct_set)
                wrong_picks = len(chosen_set - correct_set)
                ratio = max(0.0, ratio - wrong_picks / len(correct_set))
                total += ratio
            return ScoreResult(points=total, total=float(len(self.partial_keys)))
        # Them "time_bounded", "adaptive", "bonus_question" -> SUA TIEP TU DAY
        else:
            raise ValueError(f"Unknown quiz_type: {quiz_type}")


# =============================================================================
# PART 7 - Plugin Registry (config-driven OCP)
# =============================================================================

class ScorerRegistry:
    """Decorator-based registry. Class moi tu dang ky qua @ScorerRegistry.register."""

    _registry: Dict[str, Type[QuizScorer]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[Type[QuizScorer]], Type[QuizScorer]]:
        def decorator(scorer_cls: Type[QuizScorer]) -> Type[QuizScorer]:
            if name in cls._registry:
                raise ValueError(f"Scorer '{name}' already registered")
            cls._registry[name] = scorer_cls
            return scorer_cls
        return decorator

    @classmethod
    def create(cls, name: str, **kwargs) -> QuizScorer:
        if name not in cls._registry:
            raise KeyError(f"No scorer registered as '{name}'. "
                           f"Available: {list(cls._registry)}")
        return cls._registry[name](**kwargs)

    @classmethod
    def list_names(cls) -> List[str]:
        return sorted(cls._registry)


# Dang ky cac scorer da co - khong sua class, chi them decorator-wrapper:
@ScorerRegistry.register("standard")
class _RegisteredStandardScorer(StandardScorer):
    """Registry alias cua StandardScorer. Khong sua StandardScorer goc."""


@ScorerRegistry.register("negative")
class _RegisteredNegativeScorer(NegativeMarkingScorer):
    pass


@ScorerRegistry.register("weighted")
class _RegisteredWeightedScorer(WeightedScorer):
    pass


@ScorerRegistry.register("partial")
class _RegisteredPartialScorer(PartialCreditScorer):
    pass


# =============================================================================
# PART 8 - DEMO
# =============================================================================

def demo_1_extension_no_modification():
    print("=" * 70)
    print("DEMO 1 - Them 2 scorer moi: 0 file cu thay doi")
    print("=" * 70)

    answer_key = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
    answers = {"q1": "A", "q2": "B", "q3": "X", "q4": "D"}  # 3/4

    # Cu (lesson 24)
    standard = StandardScorer(answer_key)
    negative = NegativeMarkingScorer(answer_key)

    # Moi (lesson 25) - khong sua StandardScorer hay NegativeMarkingScorer
    questions = [
        Question("q1", "A", weight=1.0),
        Question("q2", "B", weight=1.0),
        Question("q3", "C", weight=2.0),  # cau kho hon
        Question("q4", "D", weight=3.0),  # cau cuoi quan trong nhat
    ]
    weighted = WeightedScorer(questions)

    partial_keys = {
        "q1": {"A", "C"},   # 2 dap an dung
        "q2": {"B"},
        "q3": {"C", "D"},
        "q4": {"D"},
    }
    partial_answers = {"q1": "A,C", "q2": "B", "q3": "C", "q4": "D,X"}
    partial = PartialCreditScorer(partial_keys)

    print(f"  StandardScorer:        {standard.score(answers).points:.2f}/4.00")
    print(f"  NegativeMarkingScorer: {negative.score(answers).points:.2f}/4.00")
    print(f"  WeightedScorer:        {weighted.score(answers).points:.2f}/7.00 "
          f"(q4 weight=3, sai q3 weight=2)")
    print(f"  PartialCreditScorer:   {partial.score(partial_answers).points:.2f}/4.00 "
          f"(q4 chon dap an du -> tru)")
    print()
    print("  Files modified de them WeightedScorer + PartialCreditScorer: 0")
    print("  Files added: 1 (chinh la 25_ocp.py voi 2 class moi)")
    print()


def demo_2_decorator_chain():
    print("=" * 70)
    print("DEMO 2 - Decorator: TimePenalty wrap moi scorer (cross-cutting)")
    print("=" * 70)

    answer_key = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
    answers = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}  # all correct

    base_standard = StandardScorer(answer_key)
    base_negative = NegativeMarkingScorer(answer_key)

    # Wrap standard voi time penalty: nop tre 3 phut, -0.5/phut = -1.5
    timed_standard = TimePenaltyDecorator(
        inner=base_standard,
        time_taken_sec=600 + 180,  # max 600 + late 180
        max_sec=600,
        penalty_per_minute_late=0.5,
    )

    # Wrap negative voi time penalty: nop dung gio, khong tru
    timed_negative_ontime = TimePenaltyDecorator(
        inner=base_negative,
        time_taken_sec=500,  # < max_sec
        max_sec=600,
        penalty_per_minute_late=0.5,
    )

    print(f"  Standard (no decorator):           {base_standard.score(answers).points:.2f}/4.00")
    print(f"  TimePenalty(Standard) +3min late:  {timed_standard.score(answers).points:.2f}/4.00 "
          f"(4.00 - 1.50 = 2.50)")
    print(f"  TimePenalty(Negative) on-time:     {timed_negative_ontime.score(answers).points:.2f}/4.00 "
          f"(no penalty)")
    print()
    print("  Decorator them 1 class - khong sua StandardScorer / NegativeMarkingScorer")
    print()


def demo_3_anti_example():
    print("=" * 70)
    print("DEMO 3 - Anti-example: OcpViolationScorer voi if/elif")
    print("=" * 70)

    # Cung 4 input, cung output - nhung qua method 100+ dong
    answer_key = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
    answers = {"q1": "A", "q2": "B", "q3": "X", "q4": "D"}
    weights = {"q1": 1.0, "q2": 1.0, "q3": 2.0, "q4": 3.0}

    bad = OcpViolationScorer(
        answer_key=answer_key,
        weights=weights,
        partial_keys={"q1": {"A"}, "q2": {"B"}, "q3": {"C"}, "q4": {"D"}},
    )

    print(f"  bad.score('standard', ...):  {bad.score('standard', answers).points:.2f}/4.00")
    print(f"  bad.score('weighted', ...):  {bad.score('weighted', answers).points:.2f}/7.00")
    print(f"  bad.score('negative', ...):  {bad.score('negative', answers).points:.2f}/4.00")
    print()
    print("  Cung output, nhung:")
    print("    - 1 method 'score()' = ~50 dong if/elif")
    print("    - Them 'time_bounded' / 'adaptive' / 'bonus' = SUA giua method")
    print("    - Param signature phinh: answer_key + weights + partial_keys + ...")
    print("    - Test 1 case phai khoi tao het param - boilerplate phinh")
    print("    - Sai typo 'weigted' chi phat hien runtime (else: raise)")
    print()
    print("  Doi chieu OCP:")
    print("    OCP version: 4 class doc lap, moi class 10-20 dong, score() pure")
    print("    Anti version: 1 class 50 dong, score() impure (param phu thuoc quiz_type)")
    print()


def demo_4_composite_notifier():
    print("=" * 70)
    print("DEMO 4 - CompositeNotifier: Email + SMS + Push fanout")
    print("=" * 70)

    email = EmailNotifier()
    sms = SmsNotifier()
    push = PushNotifier()

    # Composite: 1 call -> 3 channel
    fanout = CompositeNotifier(email, sms, push)

    result = ScoreResult(points=3.0, total=4.0)
    fanout.notify("alice", result)

    # Them Slack ngay sau day - 0 sua CompositeNotifier
    class SlackNotifier:
        def __init__(self): self.outbox: List[str] = []
        def notify(self, user_id: str, r: ScoreResult) -> None:
            self.outbox.append(f"SLACK -> #ellumm-quiz: {user_id} scored {r.percent:.0f}%")

    slack = SlackNotifier()
    fanout_with_slack = CompositeNotifier(email, sms, push, slack)
    fanout_with_slack.notify("bob", ScoreResult(points=4.0, total=4.0))

    print("  Outboxes after fanout('alice') + fanout_with_slack('bob'):")
    print(f"    Email: {email.outbox}")
    print(f"    SMS:   {sms.outbox}")
    print(f"    Push:  {push.outbox}")
    print(f"    Slack: {slack.outbox}")
    print()
    print("  Them SlackNotifier: 1 class moi, 0 sua Email/Sms/Push/Composite")
    print()


def demo_5_registry():
    print("=" * 70)
    print("DEMO 5 - Plugin Registry: load scorer tu config string")
    print("=" * 70)

    print(f"  Registered scorers: {ScorerRegistry.list_names()}")
    print()

    answer_key = {"q1": "A", "q2": "B", "q3": "C"}
    answers = {"q1": "A", "q2": "B", "q3": "X"}

    # Config string co the den tu YAML / JSON / DB
    config = [
        ("standard", {"answer_key": answer_key}),
        ("negative", {"answer_key": answer_key}),
    ]

    for name, kwargs in config:
        scorer = ScorerRegistry.create(name, **kwargs)
        result = scorer.score(answers)
        print(f"  Registry.create('{name}'): {result.points:.2f}/{result.total:.2f}")

    # Them scorer hoan toan moi runtime - 0 sua code core
    @ScorerRegistry.register("bonus")
    class BonusScorer(QuizScorer):
        """Cau dung q1 = 1 diem; cau bonus 'bonus' = 5 diem."""
        def __init__(self, answer_key: Dict[str, str], bonus_key: Dict[str, str]):
            self.answer_key = answer_key
            self.bonus_key = bonus_key
        def score(self, answers: Dict[str, str]) -> ScoreResult:
            std = sum(1.0 for q,c in self.answer_key.items() if answers.get(q)==c)
            bonus = sum(5.0 for q,c in self.bonus_key.items() if answers.get(q)==c)
            return ScoreResult(points=std+bonus,
                               total=float(len(self.answer_key) + 5*len(self.bonus_key)))

    bonus_scorer = ScorerRegistry.create(
        "bonus",
        answer_key={"q1": "A"},
        bonus_key={"bonus": "Z"},
    )
    res = bonus_scorer.score({"q1": "A", "bonus": "Z"})
    print(f"  Registry.create('bonus'): {res.points:.2f}/{res.total:.2f}")
    print(f"  Updated registry:         {ScorerRegistry.list_names()}")
    print()
    print("  3rd-party / config-driven extension - 0 sua core, 0 redeploy can")
    print()


# =============================================================================
# Main
# =============================================================================

def main():
    print()
    print("#" * 70)
    print("# LESSON 25 - Open/Closed Principle (OCP)")
    print("# Open for extension, closed for modification")
    print("# Synaptic plasticity: them spine moi, khong xoa spine cu")
    print("#" * 70)
    print()

    demo_1_extension_no_modification()
    demo_2_decorator_chain()
    demo_3_anti_example()
    demo_4_composite_notifier()
    demo_5_registry()

    print("=" * 70)
    print("Tom tat:")
    print("  - 4 scorer (Standard/Negative/Weighted/Partial) doc lap, swap 1 dong DI")
    print("  - Decorator (TimePenalty) wrap bat ky scorer - cross-cutting")
    print("  - Composite notifier fanout - them channel = +1 class")
    print("  - Plugin registry: load runtime, 3rd-party safe")
    print("  - Anti-example chi de doi chieu - KHONG copy style do")
    print("  - Buoc tiep theo (Lesson 26 LSP): subclass phai giu CONTRACT cua interface")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
