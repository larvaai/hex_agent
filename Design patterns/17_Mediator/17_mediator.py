"""
Lesson 17 — Mediator Pattern
Neuroscience analogy: Thalamus — relay & coordinate cortical areas

Cấu trúc file:
  1. Mediator interface + Colleague base
  2. Ví dụ 1 — Ellumm Learning Session Mediator (LessonViewer, QuizPanel, ...)
  3. Ví dụ 2a — BadSession: KHÔNG có mediator (N×N coupling)
  4. Ví dụ 2b — God Mediator anti-pattern → tách thành sub-mediators (thalamic nuclei)
  5. Ví dụ 3 — Command Bus (CQRS-style) với middleware
  6. Demo "thalamus damage" — mediator dies, hệ thống đứng im
  7. Test runner — `python 17_mediator.py`
"""

from __future__ import annotations

import functools
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar


# ============================================================================
# 1. INTERFACE
# ============================================================================
class Mediator(ABC):
    @abstractmethod
    def notify(self, sender: "Colleague", event: str, payload: Any = None) -> None: ...


class Colleague:
    """Base cho mọi component. Chỉ giữ ref tới mediator, không tới colleague khác."""

    def __init__(self, name: str):
        self.name = name
        self._mediator: Optional[Mediator] = None

    def set_mediator(self, m: Mediator) -> None:
        self._mediator = m

    def _notify(self, event: str, payload: Any = None) -> None:
        if self._mediator is None:
            raise RuntimeError(
                f"Colleague '{self.name}' chưa được register vào mediator"
            )
        self._mediator.notify(self, event, payload)


# ============================================================================
# 2. VÍ DỤ 1 — Ellumm Learning Session
# ============================================================================
class LessonViewer(Colleague):
    def __init__(self):
        super().__init__("LessonViewer")
        self._current: Optional[str] = None
        self._read_pct: float = 0.0

    def open_lesson(self, lesson_id: str) -> None:
        print(f"  [LessonViewer] mở lesson '{lesson_id}'")
        self._current = lesson_id
        self._read_pct = 0.0
        self._notify("lesson_started", {"lesson_id": lesson_id})

    def mark_finished(self) -> None:
        print(f"  [LessonViewer] đánh dấu đọc xong '{self._current}'")
        self._read_pct = 1.0
        self._notify("lesson_finished", {"lesson_id": self._current})

    def highlight(self, text: str) -> None:
        print(f"  [LessonViewer] highlight: {text!r}")


class QuizPanel(Colleague):
    def __init__(self):
        super().__init__("QuizPanel")
        self._locked: bool = True

    def lock(self) -> None:
        self._locked = True
        print(f"  [QuizPanel] LOCKED")

    def unlock(self) -> None:
        self._locked = False
        print(f"  [QuizPanel] unlocked")

    def submit_answer(self, correct: bool) -> None:
        if self._locked:
            print(f"  [QuizPanel] không thể submit, đang locked")
            return
        print(f"  [QuizPanel] submit: {'✓ đúng' if correct else '✗ sai'}")
        self._notify("quiz_answered", {"correct": correct})


class NotesPanel(Colleague):
    def __init__(self):
        super().__init__("NotesPanel")
        self._notes: List[str] = []

    def write(self, text: str) -> None:
        self._notes.append(text)
        print(f"  [NotesPanel] ghi note: {text!r}")
        self._notify("note_written", {"text": text})

    def clear(self) -> None:
        self._notes.clear()
        print(f"  [NotesPanel] cleared")

    def suggest_review(self, hint: str) -> None:
        print(f"  [NotesPanel] gợi ý review: {hint!r}")


class ProgressBar(Colleague):
    def __init__(self):
        super().__init__("ProgressBar")
        self._value: float = 0.0

    def reset(self) -> None:
        self._value = 0.0
        print(f"  [ProgressBar] reset → 0%")

    def add(self, delta: float) -> None:
        self._value = min(1.0, self._value + delta)
        print(f"  [ProgressBar] += {delta:.0%} → {self._value:.0%}")


class AutoSaveStorage:
    """Không phải Colleague — dependency mà mediator dùng để autosave note.
    Đáng chú ý: chỉ mediator biết storage, các Colleague không."""

    def __init__(self):
        self._store: List[str] = []

    def save(self, item: str) -> None:
        self._store.append(item)
        print(f"  [Storage] saved: {item!r}")

    def all(self) -> List[str]:
        return list(self._store)


class SessionMediator(Mediator):
    """ConcreteMediator cho Ellumm session."""

    def __init__(
        self,
        viewer: LessonViewer,
        quiz: QuizPanel,
        notes: NotesPanel,
        progress: ProgressBar,
        storage: AutoSaveStorage,
    ):
        self.viewer = viewer
        self.quiz = quiz
        self.notes = notes
        self.progress = progress
        self.storage = storage
        # Wire ngược: từng colleague biết mediator này
        for c in (viewer, quiz, notes, progress):
            c.set_mediator(self)

    def notify(self, sender: Colleague, event: str, payload: Any = None) -> None:
        # Centralized routing — đọc 1 file là hiểu toàn flow
        match (sender.name, event):
            case ("LessonViewer", "lesson_started"):
                self.progress.reset()
                self.notes.clear()
                self.quiz.lock()
            case ("LessonViewer", "lesson_finished"):
                self.progress.add(0.5)
                self.quiz.unlock()
            case ("QuizPanel", "quiz_answered"):
                if payload and payload.get("correct"):
                    self.progress.add(0.5)
                    self.notes.suggest_review("Ghi note key takeaway")
                else:
                    self.viewer.highlight("Phần liên quan đến câu sai")
            case ("NotesPanel", "note_written"):
                self.storage.save(payload["text"])
            case _:
                print(f"  [Mediator] (unhandled) {sender.name}/{event}")


def demo_session_mediator():
    section("Demo 1 — Ellumm Learning Session với Mediator")

    viewer = LessonViewer()
    quiz = QuizPanel()
    notes = NotesPanel()
    progress = ProgressBar()
    storage = AutoSaveStorage()
    SessionMediator(viewer, quiz, notes, progress, storage)

    print("\n→ User mở lesson:")
    viewer.open_lesson("17_Mediator")

    print("\n→ User cố submit quiz khi chưa đọc xong:")
    quiz.submit_answer(correct=True)

    print("\n→ User đọc xong lesson:")
    viewer.mark_finished()

    print("\n→ User submit quiz đúng:")
    quiz.submit_answer(correct=True)

    print("\n→ User ghi note:")
    notes.write("Mediator ≈ Thalamus relay")

    print(f"\n→ Storage cuối: {storage.all()}")
    print(f"→ Progress cuối: {progress._value:.0%}")


# ============================================================================
# 3. VÍ DỤ 2a — BadSession: KHÔNG có mediator (N×N coupling)
# ============================================================================
class BadLessonViewer:
    """Mỗi component giữ ref tới N-1 component khác. Không scale."""

    def __init__(self):
        self.quiz: Optional["BadQuizPanel"] = None
        self.notes: Optional["BadNotesPanel"] = None
        self.progress: Optional["BadProgressBar"] = None

    def open_lesson(self, lesson_id: str) -> None:
        print(f"  [BadViewer] mở '{lesson_id}'")
        # Logic phối hợp nằm rải rác trong từng component
        self.progress.reset()
        self.notes.clear()
        self.quiz.lock()


class BadQuizPanel:
    def __init__(self):
        self.viewer: Optional[BadLessonViewer] = None
        self.notes: Optional["BadNotesPanel"] = None
        self.progress: Optional["BadProgressBar"] = None
        self._locked = True

    def lock(self):
        self._locked = True
        print("  [BadQuiz] LOCKED")

    def unlock(self):
        self._locked = False
        print("  [BadQuiz] unlocked")

    def submit(self, correct: bool):
        if self._locked:
            return
        if correct:
            self.progress.add(0.5)
            self.notes.suggest_review("...")
        else:
            self.viewer.highlight("...")


class BadNotesPanel:
    def __init__(self):
        self.viewer = None
        self.quiz = None
        self.progress = None
        self._notes: List[str] = []

    def clear(self):
        self._notes.clear()
        print("  [BadNotes] cleared")

    def suggest_review(self, hint: str):
        print(f"  [BadNotes] suggest: {hint}")


class BadProgressBar:
    def __init__(self):
        self.viewer = None
        self.quiz = None
        self.notes = None
        self._v = 0.0

    def reset(self):
        self._v = 0.0
        print("  [BadProgress] reset")

    def add(self, d: float):
        self._v = min(1.0, self._v + d)
        print(f"  [BadProgress] {self._v:.0%}")


def demo_no_mediator():
    section("Demo 2a — KHÔNG mediator: N×N coupling, logic phân tán")
    v, q, n, p = BadLessonViewer(), BadQuizPanel(), BadNotesPanel(), BadProgressBar()
    # Wire chéo — đếm: 4 component, mỗi cái 3 ref → 12 references
    v.quiz, v.notes, v.progress = q, n, p
    q.viewer, q.notes, q.progress = v, n, p
    n.viewer, n.quiz, n.progress = v, q, p
    p.viewer, p.quiz, p.notes = v, q, n
    print("  Đã wire 12 references chéo nhau (4×3).")
    print("  Để thêm BookmarkPanel: phải sửa 4 class cũ (vi phạm Open/Closed).")
    v.open_lesson("17_Mediator")


# ============================================================================
# 4. VÍ DỤ 2b — God Mediator → tách thành sub-mediators
# ============================================================================
class GodMediator(Mediator):
    """Anti-pattern: 1 mediator biết tất cả. Demo ngắn."""

    def __init__(self):
        self._handlers: Dict[tuple, Callable] = {}

    def register(self, key: tuple, handler: Callable) -> None:
        self._handlers[key] = handler

    def notify(self, sender, event, payload=None):
        h = self._handlers.get((sender.name, event))
        if h:
            h(payload)
        else:
            print(f"  [GodMediator] (unhandled) {sender.name}/{event}")


def demo_god_mediator_split():
    section("Demo 2b — God Mediator → tách thành nuclei chuyên biệt")
    print("  Pseudo: Thay vì 1 GodMediator 500 dòng, tách thành:")
    print("    • LessonNucleus    (tương tự LGN — thị giác)")
    print("    • QuizNucleus      (tương tự MGN — thính giác)")
    print("    • NotesNucleus     (tương tự VPL — somatosensory)")
    print("    • SessionThalamus  (meta-mediator điều phối các nuclei)")
    print("  → Mỗi nucleus: trách nhiệm rõ, dưới 100 dòng, test riêng được.")


# ============================================================================
# 5. VÍ DỤ 3 — Command Bus (CQRS-style)
# ============================================================================
TCommand = TypeVar("TCommand")
TResult = TypeVar("TResult")


class Command(ABC):
    """Marker class cho mọi command."""


@dataclass(frozen=True)
class StartLessonCommand(Command):
    user_id: str
    lesson_id: str


@dataclass(frozen=True)
class CompleteQuizCommand(Command):
    user_id: str
    lesson_id: str
    score: float


@dataclass(frozen=True)
class WriteNoteCommand(Command):
    user_id: str
    text: str


class Handler(ABC, Generic[TCommand, TResult]):
    @abstractmethod
    def handle(self, cmd: TCommand) -> TResult: ...


class CommandBus(Mediator):
    """Mediator pattern dạng Command Bus.

    notify() ở đây thoái hoá thành dispatch(): 1 command = 1 handler.
    Có middleware chain (logging, retry, timing).
    """

    def __init__(self):
        self._handlers: Dict[Type[Command], Handler] = {}
        self._middlewares: List[Callable] = []

    def register(self, cmd_type: Type[Command], handler: Handler) -> None:
        self._handlers[cmd_type] = handler

    def use(self, middleware: Callable) -> None:
        """Thêm middleware. Middleware có signature:
            (cmd, next_handler) -> result
        """
        self._middlewares.append(middleware)

    def dispatch(self, cmd: Command) -> Any:
        handler = self._handlers.get(type(cmd))
        if handler is None:
            raise KeyError(f"Không có handler cho {type(cmd).__name__}")

        # Build chain từ trong ra ngoài
        def core(c):
            return handler.handle(c)

        chain = core
        for mw in reversed(self._middlewares):
            chain = self._wrap(mw, chain)
        return chain(cmd)

    @staticmethod
    def _wrap(mw, nxt):
        def wrapped(cmd):
            return mw(cmd, nxt)
        return wrapped

    # Để tương thích interface Mediator:
    def notify(self, sender, event, payload=None):
        raise NotImplementedError("CommandBus dùng dispatch(cmd), không phải notify()")


# ---- Handlers ----
class StartLessonHandler(Handler[StartLessonCommand, str]):
    def handle(self, cmd: StartLessonCommand) -> str:
        return f"Lesson '{cmd.lesson_id}' opened for user {cmd.user_id}"


class CompleteQuizHandler(Handler[CompleteQuizCommand, dict]):
    def handle(self, cmd: CompleteQuizCommand) -> dict:
        passed = cmd.score >= 0.7
        return {"user": cmd.user_id, "lesson": cmd.lesson_id, "passed": passed}


class WriteNoteHandler(Handler[WriteNoteCommand, int]):
    def __init__(self):
        self._notes: List[str] = []

    def handle(self, cmd: WriteNoteCommand) -> int:
        self._notes.append(cmd.text)
        return len(self._notes)


# ---- Middlewares ----
def logging_middleware(cmd, nxt):
    print(f"    [LOG] dispatch {type(cmd).__name__}({cmd})")
    result = nxt(cmd)
    print(f"    [LOG] result = {result!r}")
    return result


def timing_middleware(cmd, nxt):
    t0 = time.perf_counter()
    result = nxt(cmd)
    dt_ms = (time.perf_counter() - t0) * 1000
    print(f"    [TIME] {type(cmd).__name__} took {dt_ms:.2f} ms")
    return result


def retry_middleware(max_retries: int = 3) -> Callable:
    def mw(cmd, nxt):
        for attempt in range(max_retries):
            try:
                return nxt(cmd)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"    [RETRY] attempt {attempt + 1} failed: {e}")
        raise RuntimeError("unreachable")
    return mw


def demo_command_bus():
    section("Demo 3 — Command Bus (CQRS-style) + middleware")

    bus = CommandBus()
    bus.use(logging_middleware)
    bus.use(timing_middleware)
    bus.use(retry_middleware(max_retries=2))

    bus.register(StartLessonCommand, StartLessonHandler())
    bus.register(CompleteQuizCommand, CompleteQuizHandler())
    bus.register(WriteNoteCommand, WriteNoteHandler())

    print("\n  Dispatch StartLessonCommand:")
    r1 = bus.dispatch(StartLessonCommand(user_id="u1", lesson_id="17_Mediator"))
    print(f"  → {r1}")

    print("\n  Dispatch CompleteQuizCommand:")
    r2 = bus.dispatch(CompleteQuizCommand(user_id="u1", lesson_id="17_Mediator", score=0.85))
    print(f"  → {r2}")

    print("\n  Dispatch 3 WriteNoteCommand:")
    for txt in ["thalamus = mediator", "LGN cho thị", "MGN cho thính"]:
        n = bus.dispatch(WriteNoteCommand(user_id="u1", text=txt))
        print(f"  → tổng note = {n}")


# ============================================================================
# 6. DEMO 4 — "Thalamus damage": Mediator chết, hệ thống đứng im
# ============================================================================
class DeadMediator(Mediator):
    def notify(self, sender, event, payload=None):
        raise RuntimeError("Thalamus damage — mediator unresponsive")


def demo_thalamus_damage():
    section("Demo 4 — Thalamus damage: mediator chết → akinetic mutism")
    viewer = LessonViewer()
    viewer.set_mediator(DeadMediator())
    print("  Cortex (LessonViewer) còn nguyên, body còn nguyên,")
    print("  nhưng mediator chết → mọi giao tiếp fail:")
    try:
        viewer.open_lesson("17_Mediator")
    except RuntimeError as e:
        print(f"  ✗ {e}")
    print("  → Bài học architect: Mediator là single point of failure.")
    print("    Production cần: failover mediator, circuit breaker, hoặc graceful degradation.")


# ============================================================================
# 7. RUNNER
# ============================================================================
def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    demo_session_mediator()
    demo_no_mediator()
    demo_god_mediator_split()
    demo_command_bus()
    demo_thalamus_damage()
    print("\n" + "=" * 70)
    print("  Hết demo Lesson 17 — Mediator (Thalamus).")
    print("=" * 70)


if __name__ == "__main__":
    main()
