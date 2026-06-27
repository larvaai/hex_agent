"""
Lesson 26 - Liskov Substitution Principle (LSP)
Neuroscience analogy: Hodgkin-Huxley AP contract + pyramidal neuron uniformity.
                      Substitute pyramidal-pyramidal: mạch giữ. Substitute pyramidal-glia: mạch vỡ.

Cau truc file:
  PART 1 - Domain types (ScoreResult)
  PART 2 - Abstract QuizScorer + GOOD impl (StandardScorer) - LSP compliant
  PART 3 - 4 LSP VIOLATOR impls:
        - StrictScorer       (strengthen precondition)
        - BuggyScorer        (weaken postcondition)
        - MutatingScorer     (side-effect surprise)
        - NetworkScorer      (exception type change)
  PART 4 - 4 LSP-COMPLIANT refactor cho 4 violator
  PART 5 - Liskov contract test suite (abstract test - chay tren MOI subclass)
  PART 6 - Square != Rectangle classic example
  PART 7 - Demo:
        1. Run contract test tren GOOD impl + 4 violator -> 4 fail
        2. Run contract test tren 4 sau-refactor -> all pass
        3. OCP collapse: caller phai isinstance khi co violator
        4. OCP restored: caller pure polymorphic sau refactor
        5. Square vs Rectangle: assertion fail

Chay:
    python 26_lsp.py
"""
from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple, Type


# =============================================================================
# PART 1 - Domain types
# =============================================================================

@dataclass(frozen=True)
class ScoreResult:
    points: float
    total: float

    @property
    def percent(self) -> float:
        return (self.points / self.total) * 100 if self.total else 0.0


# =============================================================================
# PART 2 - Abstract QuizScorer + GOOD impl
# =============================================================================
# CONTRACT cua QuizScorer (document tuong minh - LSP can contract):
#
#   precondition:
#     - answers: dict[str, str], CO THE rong
#     - cac key chua trong answer_key se duoc bo qua
#
#   postcondition:
#     - return ScoreResult voi points >= 0 va points <= total + epsilon
#     - total > 0 (luon co it nhat 1 cau trong answer_key)
#
#   invariant:
#     - scorer instance immutable sau __init__
#     - score() la pure function: KHONG mutate input, KHONG side-effect ngam
#
#   exception:
#     - chi raise ValueError neu input sai schema
#
#   side-effect:
#     - KHONG (no DB write, no network, no log)
# =============================================================================

class QuizScorer(ABC):
    """Contract: see module docstring + class header above."""

    @abstractmethod
    def score(self, answers: Dict[str, str]) -> ScoreResult:
        ...


class StandardScorer(QuizScorer):
    """LSP-compliant. Reference impl tu lesson 24/25."""

    def __init__(self, answer_key: Dict[str, str]):
        if not answer_key:
            raise ValueError("answer_key must be non-empty")
        self._answer_key = dict(answer_key)  # copy to enforce immutability

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        if not isinstance(answers, dict):
            raise ValueError("answers must be a dict")
        points = sum(
            1.0 for q, c in self._answer_key.items()
            if answers.get(q) == c
        )
        return ScoreResult(points=points, total=float(len(self._answer_key)))


# =============================================================================
# PART 3 - 4 LSP VIOLATORS - cac kieu vi pham
# =============================================================================

class StrictScorer(QuizScorer):
    """VIOLATION 1 - STRENGTHEN PRECONDITION.
    Base accept empty dict; sub raise -> caller hop le voi base, fail voi sub."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = dict(answer_key)

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        if not answers:
            # Strengthen: base cho phep empty, sub khong cho.
            raise ValueError("StrictScorer requires non-empty answers")
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points=points, total=float(len(self._answer_key)))


class BuggyScorer(QuizScorer):
    """VIOLATION 2 - WEAKEN POSTCONDITION.
    Base hua points >= 0; sub tra negative -> leaderboard sai."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = dict(answer_key)

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        # Tru qua tay + offset am - khong clamp. Voi input thuong, output am.
        raw = -10.0  # bug: starting offset luon lam ket qua am cho input ngan
        for q, c in self._answer_key.items():
            if answers.get(q) == c:
                raw += 1.0
            else:
                raw -= 1.0
        return ScoreResult(points=raw, total=float(len(self._answer_key)))


class MutatingScorer(QuizScorer):
    """VIOLATION 3 - SIDE-EFFECT SURPRISE.
    Base la pure; sub mutate input -> caller cache reference bi corrupt."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = dict(answer_key)

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        # Mutate input - caller khong ngo
        answers["__processed__"] = "true"
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points=points, total=float(len(self._answer_key)))


class NetworkScorer(QuizScorer):
    """VIOLATION 4 - EXCEPTION TYPE CHANGE.
    Base chi raise ValueError; sub raise ConnectionError -> caller try/except thoat."""

    def __init__(self, answer_key: Dict[str, str], simulate_offline: bool = True):
        self._answer_key = dict(answer_key)
        self._simulate_offline = simulate_offline

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        if self._simulate_offline:
            # Exception type khong khai bao trong base
            raise ConnectionError("Backend offline; cannot fetch dynamic rule")
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points=points, total=float(len(self._answer_key)))


# =============================================================================
# PART 4 - 4 LSP-COMPLIANT REFACTOR
# =============================================================================

class FixedStrictScorer(QuizScorer):
    """REFACTOR violation 1: bo precondition strengthening.
    Empty answers -> tra ScoreResult(0, total) thay vi raise."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = dict(answer_key)

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        if not isinstance(answers, dict):
            raise ValueError("answers must be a dict")
        # Khong raise voi empty - return 0/total
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points=points, total=float(len(self._answer_key)))


class FixedBuggyScorer(QuizScorer):
    """REFACTOR violation 2: clamp points >= 0 trong return."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = dict(answer_key)

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        raw = -2.0
        for q, c in self._answer_key.items():
            if answers.get(q) == c:
                raw += 1.0
            else:
                raw -= 1.0
        # Clamp - giu postcondition points >= 0
        clamped = max(0.0, raw)
        return ScoreResult(points=clamped, total=float(len(self._answer_key)))


class FixedMutatingScorer(QuizScorer):
    """REFACTOR violation 3: copy input thay vi mutate."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = dict(answer_key)

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        # Copy ngay tu dau - moi mutate cuc bo, khong leak ra caller
        local = dict(answers)
        local["__processed__"] = "true"  # vo hai vi local
        points = sum(1.0 for q, c in self._answer_key.items() if local.get(q) == c)
        return ScoreResult(points=points, total=float(len(self._answer_key)))


class FixedNetworkScorer(QuizScorer):
    """REFACTOR violation 4: wrap ConnectionError thanh ValueError (hoac fallback)."""

    def __init__(self, answer_key: Dict[str, str], simulate_offline: bool = True):
        self._answer_key = dict(answer_key)
        self._simulate_offline = simulate_offline

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        try:
            if self._simulate_offline:
                raise ConnectionError("Backend offline")
            return self._score_online(answers)
        except ConnectionError:
            # Wrap thanh fallback - khong leak exception type ra caller
            # Lua chon: tra ScoreResult mac dinh, hoac raise ValueError de caller xu ly
            # O day chon: raise ValueError voi message ro
            raise ValueError("Cannot score: backend offline (fallback unavailable)")

    def _score_online(self, answers: Dict[str, str]) -> ScoreResult:
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points=points, total=float(len(self._answer_key)))


# =============================================================================
# PART 5 - Liskov Contract Test Suite
# =============================================================================
# Abstract test - chay tren MOI subclass cua QuizScorer.
# Subclass nao FAIL = vi pham LSP.

ANSWER_KEY = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
ANSWERS_PARTIAL = {"q1": "A", "q2": "B", "q3": "X", "q4": "D"}
ANSWERS_EMPTY: Dict[str, str] = {}


class LiskovContractFailure(AssertionError):
    """Raised when a subclass violates the QuizScorer contract."""


def liskov_test_returns_score_result(scorer: QuizScorer) -> None:
    """Postcondition: return type must be ScoreResult."""
    result = scorer.score(ANSWERS_PARTIAL)
    if not isinstance(result, ScoreResult):
        raise LiskovContractFailure(
            f"score() must return ScoreResult, got {type(result).__name__}"
        )


def liskov_test_points_non_negative(scorer: QuizScorer) -> None:
    """Postcondition: points >= 0."""
    result = scorer.score(ANSWERS_PARTIAL)
    if result.points < 0:
        raise LiskovContractFailure(
            f"points must be >= 0, got {result.points}"
        )


def liskov_test_points_bounded(scorer: QuizScorer) -> None:
    """Postcondition: points <= total + small epsilon."""
    result = scorer.score(ANSWERS_PARTIAL)
    if result.points > result.total + 0.001:
        raise LiskovContractFailure(
            f"points {result.points} exceeds total {result.total}"
        )


def liskov_test_accepts_empty(scorer: QuizScorer) -> None:
    """Precondition: empty answers must NOT raise (base allows it)."""
    try:
        result = scorer.score(ANSWERS_EMPTY)
        if not isinstance(result, ScoreResult):
            raise LiskovContractFailure("must return ScoreResult on empty input")
    except ValueError as e:
        # ValueError on empty = strengthen precondition
        raise LiskovContractFailure(
            f"score() on empty raised ValueError ({e}) - strengthens precondition"
        )


def liskov_test_no_input_mutation(scorer: QuizScorer) -> None:
    """Invariant: input dict must NOT be mutated (pure)."""
    answers = {"q1": "A", "q2": "B"}
    snapshot = copy.deepcopy(answers)
    try:
        scorer.score(answers)
    except (ValueError, KeyError):
        # Schema errors are fine - we only care about mutation
        pass
    if answers != snapshot:
        raise LiskovContractFailure(
            f"score() mutated input. Before={snapshot}, after={answers}"
        )


def liskov_test_only_value_error(scorer: QuizScorer) -> None:
    """Exception: only ValueError is allowed for invalid input.
    Run with valid input - should NOT raise anything beyond declared types."""
    try:
        scorer.score(ANSWERS_PARTIAL)
    except ValueError:
        # ValueError is fine for declared schema issues
        # but with valid input it shouldn't even raise that
        raise LiskovContractFailure(
            "score() raised ValueError on valid input - undocumented strict precondition"
        )
    except Exception as e:
        # Any other exception type = contract violation
        raise LiskovContractFailure(
            f"score() raised {type(e).__name__}({e}) - "
            f"only ValueError is allowed in contract"
        )


CONTRACT_TESTS: List[Tuple[str, Callable[[QuizScorer], None]]] = [
    ("returns ScoreResult", liskov_test_returns_score_result),
    ("points >= 0", liskov_test_points_non_negative),
    ("points <= total", liskov_test_points_bounded),
    ("accepts empty input", liskov_test_accepts_empty),
    ("no input mutation", liskov_test_no_input_mutation),
    ("only ValueError raised", liskov_test_only_value_error),
]


def run_contract_tests(scorer_name: str, scorer: QuizScorer) -> Tuple[int, int]:
    """Returns (passed, failed). Bat ca exception khong phai ValueError - vi pham contract."""
    passed = 0
    failed = 0
    for test_name, test_fn in CONTRACT_TESTS:
        try:
            test_fn(scorer)
            passed += 1
        except LiskovContractFailure as e:
            failed += 1
            print(f"    [FAIL] {scorer_name:24s} {test_name:25s} -> {e}")
        except Exception as e:
            # Exception type ngoai contract khi chay test -> vi pham contract
            failed += 1
            print(f"    [FAIL] {scorer_name:24s} {test_name:25s} -> "
                  f"unexpected {type(e).__name__}({e}) - exception type ngoai contract")
    return passed, failed


# =============================================================================
# PART 6 - Square != Rectangle classic example
# =============================================================================

class Rectangle:
    """Contract:
    - set_width(w): only width changes
    - set_height(h): only height changes
    - area() == width * height
    """

    def __init__(self, w: float, h: float):
        self._w = w
        self._h = h

    def set_width(self, w: float) -> None:
        self._w = w

    def set_height(self, h: float) -> None:
        self._h = h

    def area(self) -> float:
        return self._w * self._h


class Square(Rectangle):
    """VIOLATION: set_height also changes width to keep square invariant.
    -> set_width(w) followed by set_height(h) gives unexpected area.
    Square IS-A Rectangle taxonomically, but NOT behaviorally."""

    def set_width(self, w: float) -> None:
        self._w = w
        self._h = w  # keep square - violates "only width changes"

    def set_height(self, h: float) -> None:
        self._w = h
        self._h = h


def grow_rectangle(rect: Rectangle) -> float:
    """Caller depending on Rectangle contract."""
    rect.set_width(10)
    rect.set_height(5)
    # Caller assertion based on contract: width=10, height=5 -> area=50
    return rect.area()


# =============================================================================
# PART 7 - DEMOS
# =============================================================================

def demo_1_violators_fail_contract():
    print("=" * 70)
    print("DEMO 1 - Liskov contract test tren GOOD impl + 4 violator")
    print("=" * 70)

    print("\n  GOOD impl:")
    scorers_good: List[Tuple[str, QuizScorer]] = [
        ("StandardScorer", StandardScorer(ANSWER_KEY)),
    ]
    for name, scorer in scorers_good:
        passed, failed = run_contract_tests(name, scorer)
        verdict = "OK" if failed == 0 else f"FAIL ({failed})"
        print(f"    {name:24s} : {passed}/{passed+failed} pass [{verdict}]")

    print("\n  4 VIOLATORS:")
    violators: List[Tuple[str, QuizScorer]] = [
        ("StrictScorer",   StrictScorer(ANSWER_KEY)),
        ("BuggyScorer",    BuggyScorer(ANSWER_KEY)),
        ("MutatingScorer", MutatingScorer(ANSWER_KEY)),
        ("NetworkScorer",  NetworkScorer(ANSWER_KEY)),
    ]
    for name, scorer in violators:
        passed, failed = run_contract_tests(name, scorer)
        verdict = "OK" if failed == 0 else f"VIOLATES ({failed})"
        print(f"    {name:24s} : {passed}/{passed+failed} pass [{verdict}]")
    print()


def demo_2_refactored_pass_contract():
    print("=" * 70)
    print("DEMO 2 - Sau refactor: 4 fixed impl pass contract")
    print("=" * 70)

    fixed: List[Tuple[str, QuizScorer]] = [
        ("FixedStrictScorer",   FixedStrictScorer(ANSWER_KEY)),
        ("FixedBuggyScorer",    FixedBuggyScorer(ANSWER_KEY)),
        ("FixedMutatingScorer", FixedMutatingScorer(ANSWER_KEY)),
        ("FixedNetworkScorer",  FixedNetworkScorer(ANSWER_KEY, simulate_offline=False)),
    ]
    for name, scorer in fixed:
        passed, failed = run_contract_tests(name, scorer)
        verdict = "OK" if failed == 0 else f"FAIL ({failed})"
        print(f"    {name:24s} : {passed}/{passed+failed} pass [{verdict}]")
    print()
    print("  Note: FixedNetworkScorer voi simulate_offline=True van raise ValueError")
    print("        nhung that la van trong contract (ValueError la exception duoc khai bao)")
    print()


def demo_3_ocp_collapse_with_violator():
    print("=" * 70)
    print("DEMO 3 - OCP collapse: caller buoc isinstance khi co violator")
    print("=" * 70)

    def submit_naive(scorer: QuizScorer, answers: Dict[str, str]) -> ScoreResult:
        """Caller polymorphic - khong isinstance check."""
        return scorer.score(answers)

    def submit_defensive(scorer: QuizScorer, answers: Dict[str, str]) -> ScoreResult:
        """Caller phai isinstance check vi co violator -> OCP collapse."""
        if isinstance(scorer, StrictScorer) and not answers:
            return ScoreResult(points=0, total=0)
        if isinstance(scorer, BuggyScorer):
            r = scorer.score(answers)
            return ScoreResult(points=max(0.0, r.points), total=r.total)
        if isinstance(scorer, MutatingScorer):
            answers = dict(answers)  # defensive copy
        if isinstance(scorer, NetworkScorer):
            try:
                return scorer.score(answers)
            except ConnectionError:
                return ScoreResult(points=0, total=4)
        return scorer.score(answers)

    print("  Caller naive (1 dong polymorphic):")
    try:
        submit_naive(StrictScorer(ANSWER_KEY), {})
    except ValueError as e:
        print(f"    -> StrictScorer + empty: ValueError ({e})")
    try:
        r = submit_naive(BuggyScorer(ANSWER_KEY), ANSWERS_PARTIAL)
        print(f"    -> BuggyScorer: points={r.points} (am! leaderboard sai)")
    except Exception as e:
        print(f"    -> BuggyScorer: {type(e).__name__}: {e}")

    answers_to_corrupt = {"q1": "A"}
    try:
        submit_naive(MutatingScorer(ANSWER_KEY), answers_to_corrupt)
        print(f"    -> MutatingScorer: input bi mutate = {answers_to_corrupt}")
    except Exception as e:
        print(f"    -> MutatingScorer: {type(e).__name__}: {e}")

    try:
        submit_naive(NetworkScorer(ANSWER_KEY), ANSWERS_PARTIAL)
    except ConnectionError as e:
        print(f"    -> NetworkScorer: ConnectionError thoat ra ({e})")

    print()
    print("  Caller defensive (4 isinstance check + special handling):")
    print(f"    -> StrictScorer + empty: {submit_defensive(StrictScorer(ANSWER_KEY), {})}")
    print(f"    -> BuggyScorer: {submit_defensive(BuggyScorer(ANSWER_KEY), ANSWERS_PARTIAL)}")
    a = {"q1": "A"}
    submit_defensive(MutatingScorer(ANSWER_KEY), a)
    print(f"    -> MutatingScorer: input giu nguyen = {a}")
    print(f"    -> NetworkScorer: {submit_defensive(NetworkScorer(ANSWER_KEY), ANSWERS_PARTIAL)}")
    print()
    print("  -> OCP da bi collapse: caller phai biet 4 sublcass concrete.")
    print("     Them violator thu 5 -> sua submit_defensive() (vi pham OCP).")
    print()


def demo_4_ocp_restored_with_lsp():
    print("=" * 70)
    print("DEMO 4 - OCP restored sau khi cac subclass tuan thu LSP")
    print("=" * 70)

    def submit(scorer: QuizScorer, answers: Dict[str, str]) -> ScoreResult:
        """Polymorphic 1 dong - khong isinstance vi LSP-compliant."""
        return scorer.score(answers)

    fixed_scorers = [
        ("StandardScorer",       StandardScorer(ANSWER_KEY)),
        ("FixedStrictScorer",    FixedStrictScorer(ANSWER_KEY)),
        ("FixedBuggyScorer",     FixedBuggyScorer(ANSWER_KEY)),
        ("FixedMutatingScorer",  FixedMutatingScorer(ANSWER_KEY)),
        ("FixedNetworkScorer",   FixedNetworkScorer(ANSWER_KEY, simulate_offline=False)),
    ]
    for name, scorer in fixed_scorers:
        result = submit(scorer, ANSWERS_PARTIAL)
        print(f"    submit({name:24s}): points={result.points:.2f}/{result.total:.2f}")

    print()
    print("  Caller la 1 dong, KHONG isinstance, khong special case.")
    print("  Them subclass thu 6, 7, ... -> submit() khong sua. OCP duoc bao toan.")
    print()


def demo_5_square_rectangle():
    print("=" * 70)
    print("DEMO 5 - Square IS-NOT-A Rectangle theo LSP")
    print("=" * 70)

    rect = Rectangle(3, 4)
    sq = Square(3, 3)

    rect_area = grow_rectangle(rect)
    sq_area = grow_rectangle(sq)

    print(f"  grow_rectangle(Rectangle): set_width(10), set_height(5) -> area = {rect_area}")
    print(f"  grow_rectangle(Square):    set_width(10), set_height(5) -> area = {sq_area}")
    print()
    print("  Caller dua vao Rectangle contract: width=10, height=5 -> area=50")
    print(f"  -> Rectangle return {rect_area} OK")
    print(f"  -> Square return {sq_area} (set_height(5) cung dat width=5)")
    print()
    if rect_area != sq_area:
        print("  Square 'is-a' Rectangle theo phan loai ngon ngu, NHUNG vi pham LSP")
        print("  vi behavior cua set_height khac semantically. Caller phai biet truoc")
        print("  ('phai isinstance check') -> OCP collapse.")
    print()


def main():
    print()
    print("#" * 70)
    print("# LESSON 26 - Liskov Substitution Principle (LSP)")
    print("# Subclass phai giu CONTRACT - caller khong can biet la sub nao")
    print("# Hodgkin-Huxley AP universal protocol: pyramidal swap pyramidal -> OK")
    print("#" * 70)
    print()

    demo_1_violators_fail_contract()
    demo_2_refactored_pass_contract()
    demo_3_ocp_collapse_with_violator()
    demo_4_ocp_restored_with_lsp()
    demo_5_square_rectangle()

    print("=" * 70)
    print("Tom tat:")
    print("  - 4 loai vi pham LSP: strengthen pre / weaken post / side-effect / exception")
    print("  - Vi pham LSP -> caller buoc isinstance -> OCP collapse")
    print("  - LSP-compliant -> caller polymorphic 1 dong")
    print("  - Liskov contract test = abstract test chay cho moi subclass o CI")
    print("  - Square != Rectangle: IS-A taxonomy != IS-A behavior")
    print("  - Buoc tiep theo (Lesson 27 ISP): interface to ep client phu thuoc method thua")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
