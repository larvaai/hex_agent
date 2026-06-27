"""
Lesson 16 — Iterator Pattern
Neuroscience analogy: Saccade — Superior Colliculus + FEF + LIP

Cấu trúc file:
  1. Interface Iterator + Aggregate (canonical Iterator pattern)
  2. Domain model: Fixation, VisualScene
  3. Ví dụ 1 — Vận hành thường: Salience-driven saccade (heap-based)
  4. Ví dụ 2 — Hỏng/thiếu: ConcurrentModification — fail-fast vs snapshot
  5. Ví dụ 3 — Ứng dụng Ellumm: Lazy paginated lesson iterator
  6. Composing iterators: FilterIterator, MapIterator (decorator-style)
  7. Generator variant (Pythonic)
  8. Test runner: chạy `python 16_iterator.py` để xem demo
"""

from __future__ import annotations

import heapq
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Iterable, Iterator, List, Optional, TypeVar

T = TypeVar("T")


# ============================================================================
# 1. INTERFACE — Canonical Iterator pattern
# ============================================================================
class Iter(ABC, Generic[T]):
    """Interface Iterator. Đặt tên `Iter` để khỏi đụng `typing.Iterator`."""

    @abstractmethod
    def has_next(self) -> bool: ...

    @abstractmethod
    def next(self) -> T: ...

    # Cho phép dùng trong `for` của Python — bridge sang iterator protocol
    def __iter__(self) -> Iterator[T]:
        return self

    def __next__(self) -> T:
        if not self.has_next():
            raise StopIteration
        return self.next()


class Aggregate(ABC, Generic[T]):
    """Interface Aggregate."""

    @abstractmethod
    def iterator(self) -> Iter[T]: ...


# ============================================================================
# 2. DOMAIN MODEL — Fixation và VisualScene
# ============================================================================
@dataclass(frozen=True)
class Fixation:
    """Một điểm fixation trên visual scene.

    - x, y: toạ độ (độ thị giác).
    - salience: độ nổi bật (LIP map).
    - goal_score: phù hợp goal hiện tại (FEF map).
    - content: nội dung được nhận diện sau fixation (V4/IT output).
    """

    x: float
    y: float
    salience: float
    goal_score: float = 0.0
    content: str = ""

    def __repr__(self) -> str:
        return f"Fix({self.x:.0f},{self.y:.0f} sal={self.salience:.2f} '{self.content}')"


class VisualScene(Aggregate[Fixation]):
    """Aggregate. Đẻ ra nhiều Iterator khác nhau cho cùng 1 scene."""

    def __init__(self, fixations: List[Fixation]):
        self._fixations: List[Fixation] = list(fixations)
        self._version: int = 0  # tăng mỗi khi modify — dùng cho fail-fast

    def add(self, f: Fixation) -> None:
        self._fixations.append(f)
        self._version += 1

    def remove_at(self, idx: int) -> None:
        self._fixations.pop(idx)
        self._version += 1

    def __len__(self) -> int:
        return len(self._fixations)

    # ---- Default iterator: thứ tự thêm vào ----
    def iterator(self) -> Iter[Fixation]:
        return _SequentialIterator(self)

    # ---- Strategy: bottom-up salience ----
    def iterator_salience(self) -> Iter[Fixation]:
        return SalienceSaccadeIterator(self)

    # ---- Strategy: top-down goal-driven (đã sort theo goal_score giảm dần) ----
    def iterator_goal_driven(self) -> Iter[Fixation]:
        return GoalDrivenSaccadeIterator(self)

    # ---- Strategy: scanpath = weighted(salience, goal) ----
    def iterator_scanpath(
        self, w_salience: float = 0.5, w_goal: float = 0.5
    ) -> Iter[Fixation]:
        return ScanpathIterator(self, w_salience, w_goal)


# ============================================================================
# 3. VÍ DỤ 1 — Vận hành thường: salience-driven (heap O(log N) per next)
# ============================================================================
class _SequentialIterator(Iter[Fixation]):
    """Iterator đơn giản nhất — duyệt theo thứ tự thêm vào, có snapshot."""

    def __init__(self, scene: VisualScene):
        # Snapshot: thay đổi scene sau đó không ảnh hưởng iterator này.
        self._snapshot: List[Fixation] = list(scene._fixations)
        self._cursor: int = 0

    def has_next(self) -> bool:
        return self._cursor < len(self._snapshot)

    def next(self) -> Fixation:
        if not self.has_next():
            raise StopIteration("Đã duyệt hết scene")
        f = self._snapshot[self._cursor]
        self._cursor += 1
        return f


class SalienceSaccadeIterator(Iter[Fixation]):
    """Bottom-up: chọn fixation salience cao nhất trước.
    Dùng max-heap. next() = O(log N). Memory = O(N)."""

    def __init__(self, scene: VisualScene):
        # heapq là min-heap → đảo dấu salience để có max-heap
        self._heap: List[tuple] = [
            (-f.salience, idx, f) for idx, f in enumerate(scene._fixations)
        ]
        heapq.heapify(self._heap)

    def has_next(self) -> bool:
        return len(self._heap) > 0

    def next(self) -> Fixation:
        if not self.has_next():
            raise StopIteration
        _, _, f = heapq.heappop(self._heap)
        return f


class GoalDrivenSaccadeIterator(Iter[Fixation]):
    """Top-down: theo goal_score giảm dần. Snapshot tại lúc tạo."""

    def __init__(self, scene: VisualScene):
        self._sorted: List[Fixation] = sorted(
            scene._fixations, key=lambda f: f.goal_score, reverse=True
        )
        self._cursor: int = 0

    def has_next(self) -> bool:
        return self._cursor < len(self._sorted)

    def next(self) -> Fixation:
        if not self.has_next():
            raise StopIteration
        f = self._sorted[self._cursor]
        self._cursor += 1
        return f


class ScanpathIterator(Iter[Fixation]):
    """Mô phỏng scanpath thực: weighted(salience, goal_score)."""

    def __init__(self, scene: VisualScene, w_salience: float, w_goal: float):
        scored = [
            (-(w_salience * f.salience + w_goal * f.goal_score), idx, f)
            for idx, f in enumerate(scene._fixations)
        ]
        heapq.heapify(scored)
        self._heap = scored

    def has_next(self) -> bool:
        return len(self._heap) > 0

    def next(self) -> Fixation:
        if not self.has_next():
            raise StopIteration
        _, _, f = heapq.heappop(self._heap)
        return f


# ============================================================================
# 4. VÍ DỤ 2 — Hỏng/thiếu: ConcurrentModification
# ============================================================================
class ConcurrentModificationError(RuntimeError):
    """Raise khi scene bị modify giữa lúc iterator đang chạy (fail-fast)."""


class FailFastIterator(Iter[Fixation]):
    """So với SequentialIterator: KHÔNG snapshot, mà giữ tham chiếu trực tiếp.
    Nếu version của scene đổi giữa chừng → raise."""

    def __init__(self, scene: VisualScene):
        self._scene: VisualScene = scene
        self._cursor: int = 0
        self._expected_version: int = scene._version

    def _check_version(self) -> None:
        if self._scene._version != self._expected_version:
            raise ConcurrentModificationError(
                f"Scene đã modify (v{self._expected_version} → v{self._scene._version}) "
                f"sau khi iterator được tạo."
            )

    def has_next(self) -> bool:
        self._check_version()
        return self._cursor < len(self._scene._fixations)

    def next(self) -> Fixation:
        self._check_version()
        if self._cursor >= len(self._scene._fixations):
            raise StopIteration
        f = self._scene._fixations[self._cursor]
        self._cursor += 1
        return f


# ============================================================================
# 5. VÍ DỤ 3 — Ellumm: Lazy paginated lesson iterator
# ============================================================================
@dataclass
class Lesson:
    id: int
    title: str
    pattern: str


@dataclass
class Page:
    lessons: List[Lesson]
    next_cursor: Optional[str]


class FakeEllummAPI:
    """Mock API: trả 3 trang lessons. Lần fetch trang 2 cố tình lỗi 1 lần
    để demo retry logic."""

    def __init__(self):
        self._pages = {
            None: Page(
                lessons=[
                    Lesson(1, "Singleton — Locus Coeruleus", "Singleton"),
                    Lesson(2, "Factory Method — Neural Stem", "Factory Method"),
                ],
                next_cursor="p2",
            ),
            "p2": Page(
                lessons=[
                    Lesson(3, "Adapter — Thalamus", "Adapter"),
                    Lesson(4, "Decorator — Myelin", "Decorator"),
                ],
                next_cursor="p3",
            ),
            "p3": Page(
                lessons=[
                    Lesson(5, "Iterator — Saccade", "Iterator"),
                ],
                next_cursor=None,
            ),
        }
        self._fail_count = {"p2": 1}  # p2 fail 1 lần đầu

    def fetch(self, cursor: Optional[str]) -> Page:
        if cursor in self._fail_count and self._fail_count[cursor] > 0:
            self._fail_count[cursor] -= 1
            raise ConnectionError(f"503 Service Unavailable cho cursor={cursor}")
        return deepcopy(self._pages[cursor])


class LazyLessonIterator(Iter[Lesson]):
    """Lazy: chỉ fetch trang sau khi consume hết trang hiện tại.
    Có retry với exponential backoff (mô phỏng — không thật sleep)."""

    def __init__(self, api: FakeEllummAPI, max_retries: int = 3):
        self._api = api
        self._buffer: List[Lesson] = []
        self._cursor: Optional[str] = None
        self._has_more: bool = True
        self._max_retries = max_retries
        self._closed: bool = False

    def _fetch_with_retry(self, cursor: Optional[str]) -> Page:
        for attempt in range(self._max_retries):
            try:
                return self._api.fetch(cursor)
            except ConnectionError as e:
                if attempt == self._max_retries - 1:
                    raise
                # Trong production: time.sleep(2**attempt). Ở đây chỉ log.
                print(f"  [retry {attempt + 1}] {e} — backoff...")
        raise RuntimeError("unreachable")

    def _refill(self) -> None:
        if self._closed:
            raise RuntimeError("Iterator đã đóng")
        if not self._has_more:
            return
        page = self._fetch_with_retry(self._cursor)
        self._buffer.extend(page.lessons)
        self._cursor = page.next_cursor
        self._has_more = page.next_cursor is not None

    def has_next(self) -> bool:
        if self._buffer:
            return True
        if not self._has_more:
            return False
        self._refill()
        return len(self._buffer) > 0

    def next(self) -> Lesson:
        if not self.has_next():
            raise StopIteration
        return self._buffer.pop(0)

    def close(self) -> None:
        self._closed = True
        self._buffer.clear()

    # Context manager: ensure resource release
    def __enter__(self) -> "LazyLessonIterator":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ============================================================================
# 6. COMPOSING — FilterIterator + MapIterator (Decorator-on-Iterator)
# ============================================================================
class FilterIterator(Iter[T]):
    """Bọc một iterator, chỉ trả phần tử thỏa predicate."""

    def __init__(self, source: Iter[T], predicate: Callable[[T], bool]):
        self._source = source
        self._predicate = predicate
        self._cached: Optional[T] = None  # one-element lookahead

    def _advance(self) -> None:
        while self._cached is None and self._source.has_next():
            item = self._source.next()
            if self._predicate(item):
                self._cached = item

    def has_next(self) -> bool:
        if self._cached is None:
            self._advance()
        return self._cached is not None

    def next(self) -> T:
        if not self.has_next():
            raise StopIteration
        item = self._cached
        self._cached = None
        return item  # type: ignore


U = TypeVar("U")


class MapIterator(Iter[U], Generic[T, U]):
    """Bọc iterator, transform phần tử qua fn."""

    def __init__(self, source: Iter[T], fn: Callable[[T], U]):
        self._source = source
        self._fn = fn

    def has_next(self) -> bool:
        return self._source.has_next()

    def next(self) -> U:
        return self._fn(self._source.next())


# ============================================================================
# 7. GENERATOR VARIANT — Pythonic, ngắn hơn nhiều
# ============================================================================
def saccade_salience_gen(scene: VisualScene):
    """Cùng logic SalienceSaccadeIterator nhưng viết bằng generator."""
    for f in sorted(scene._fixations, key=lambda f: f.salience, reverse=True):
        yield f


# ============================================================================
# 8. TEST / DEMO RUNNER
# ============================================================================
def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_basic():
    section("Demo 1 — Salience-driven saccade (bottom-up attention)")
    scene = VisualScene([
        Fixation(10, 10, salience=0.2, goal_score=0.9, content="dog"),
        Fixation(50, 30, salience=0.9, goal_score=0.1, content="fire"),
        Fixation(80, 70, salience=0.5, goal_score=0.6, content="text"),
        Fixation(20, 80, salience=0.7, goal_score=0.3, content="face"),
    ])

    print("\nThứ tự quét theo SALIENCE (bottom-up):")
    it = scene.iterator_salience()
    while it.has_next():
        print("  →", it.next())

    print("\nThứ tự quét theo GOAL (top-down — đang tìm 'dog'):")
    it = scene.iterator_goal_driven()
    while it.has_next():
        print("  →", it.next())

    print("\nThứ tự SCANPATH (weighted 30% salience + 70% goal):")
    it = scene.iterator_scanpath(w_salience=0.3, w_goal=0.7)
    while it.has_next():
        print("  →", it.next())


def demo_concurrent_mod():
    section("Demo 2 — ConcurrentModification: snapshot vs fail-fast")
    scene = VisualScene([
        Fixation(0, 0, 0.5, content="A"),
        Fixation(1, 1, 0.5, content="B"),
        Fixation(2, 2, 0.5, content="C"),
    ])

    print("\n[2a] Snapshot iterator — modify scene KHÔNG ảnh hưởng:")
    it = scene.iterator()  # _SequentialIterator dùng snapshot
    print("  bước 1 →", it.next())
    scene.add(Fixation(99, 99, 1.0, content="ADDED"))
    print("  scene sau khi add:", len(scene), "fixations")
    print("  iterator tiếp tục như cũ:")
    while it.has_next():
        print("    →", it.next())

    print("\n[2b] Fail-fast iterator — modify scene → raise:")
    scene2 = VisualScene([
        Fixation(0, 0, 0.5, content="X"),
        Fixation(1, 1, 0.5, content="Y"),
    ])
    it2 = FailFastIterator(scene2)
    print("  bước 1 →", it2.next())
    scene2.add(Fixation(2, 2, 0.5, content="LATE"))
    try:
        it2.next()
    except ConcurrentModificationError as e:
        print(f"  ✓ Caught ConcurrentModificationError:\n    {e}")


def demo_lazy_paginated():
    section("Demo 3 — Ellumm: Lazy paginated iterator + retry + context mgr")
    api = FakeEllummAPI()
    print("\nDuyệt toàn bộ lessons (3 trang, p2 lỗi 1 lần đầu):")
    with LazyLessonIterator(api, max_retries=3) as it:
        while it.has_next():
            lesson = it.next()
            print(f"  → [{lesson.id}] {lesson.title}")
    print("Iterator tự đóng khi ra khỏi `with`.")


def demo_compose():
    section("Demo 4 — Compose: Filter + Map trên iterator có sẵn")
    scene = VisualScene([
        Fixation(0, 0, salience=0.2, content="low1"),
        Fixation(1, 1, salience=0.8, content="HIGH1"),
        Fixation(2, 2, salience=0.3, content="low2"),
        Fixation(3, 3, salience=0.95, content="HIGH2"),
    ])

    base = scene.iterator_salience()
    high_only = FilterIterator(base, predicate=lambda f: f.salience > 0.5)
    contents = MapIterator(high_only, fn=lambda f: f.content.upper())

    print("\nChỉ fixation salience > 0.5, lấy content uppercase:")
    for c in contents:  # nhờ __iter__/__next__ bridge
        print("  →", c)


def demo_generator():
    section("Demo 5 — Generator variant (Pythonic equivalent)")
    scene = VisualScene([
        Fixation(0, 0, salience=0.4, content="α"),
        Fixation(1, 1, salience=0.9, content="β"),
        Fixation(2, 2, salience=0.6, content="γ"),
    ])
    print("\nDuyệt qua generator — code ngắn hơn class iterator:")
    for f in saccade_salience_gen(scene):
        print("  →", f)


def demo_independent_cursors():
    section("Demo 6 — Hai iterator độc lập trên cùng scene")
    scene = VisualScene([
        Fixation(i, i, salience=i / 10) for i in range(5)
    ])
    it_a = scene.iterator_salience()
    it_b = scene.iterator_salience()
    print("\nA tiến 2 bước, B tiến 1 bước, sau đó A và B tiếp:")
    print("  A:", it_a.next(), "|", it_a.next())
    print("  B:", it_b.next())
    print("  A:", it_a.next())
    print("  B:", it_b.next(), "|", it_b.next())
    print("→ B không bị ảnh hưởng bởi A. Mỗi iterator có cursor riêng.")


def main():
    demo_basic()
    demo_concurrent_mod()
    demo_lazy_paginated()
    demo_compose()
    demo_generator()
    demo_independent_cursors()
    print("\n" + "=" * 70)
    print("  Hết demo Lesson 16 — Iterator (Saccade).")
    print("=" * 70)


if __name__ == "__main__":
    main()
