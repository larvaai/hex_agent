"""
Lesson 18 — Memento Pattern
Neuroscience analogy: Hippocampus — episodic snapshot (encoding/consolidation/retrieval)

Cấu trúc file:
  1. Memento canonical: LessonEditor + History + EditorMemento
  2. Demo 1 — undo/redo flow
  3. Demo 2 — 3 failure modes (tampering, shallow-copy, OOM)
  4. Demo 3 — Memento vs Command vs Persistent: cùng API, 3 trade-off
  5. Demo 4 — H.M. lesion: disable save() nhưng history cũ còn restore được
  6. Test runner — `python 18_memento.py`
"""

from __future__ import annotations

import copy
import sys
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Deque, List, Optional, Tuple


# ============================================================================
# 1. CANONICAL MEMENTO — LessonEditor
# ============================================================================
@dataclass(frozen=True)
class EditorState:
    """Memento — immutable snapshot. Frozen + chỉ chứa immutable fields."""
    title: str
    body: str
    cursor: int
    # Note: tuple chứ không list để cũng immutable
    tags: Tuple[str, ...] = ()


class LessonEditor:
    """Originator. Tự save() và restore(); caretaker không đụng vào internal."""

    def __init__(self, title: str = "", body: str = "", cursor: int = 0):
        self._state = EditorState(title=title, body=body, cursor=cursor, tags=())

    # ---- Business operations ----
    def set_title(self, t: str) -> None:
        self._state = replace(self._state, title=t)

    def type_text(self, text: str) -> None:
        s = self._state
        new_body = s.body[: s.cursor] + text + s.body[s.cursor :]
        self._state = replace(s, body=new_body, cursor=s.cursor + len(text))

    def move_cursor(self, pos: int) -> None:
        self._state = replace(self._state, cursor=max(0, min(pos, len(self._state.body))))

    def add_tag(self, tag: str) -> None:
        self._state = replace(self._state, tags=self._state.tags + (tag,))

    # ---- Memento API ----
    def save(self) -> EditorState:
        # State đã immutable — không cần deepcopy.
        return self._state

    def restore(self, m: EditorState) -> None:
        if not isinstance(m, EditorState):
            raise TypeError("Memento sai type — không phải của LessonEditor")
        self._state = m

    # ---- Display ----
    def __repr__(self) -> str:
        s = self._state
        body_preview = (s.body[:30] + "…") if len(s.body) > 30 else s.body
        return f"Editor(title={s.title!r}, body={body_preview!r}, cur={s.cursor}, tags={s.tags})"


class History:
    """Caretaker. Chỉ giữ memento, không inspect."""

    def __init__(self, max_size: int = 100):
        self._undo: Deque[EditorState] = deque(maxlen=max_size)
        self._redo: List[EditorState] = []
        self.max_size = max_size

    def push(self, m: EditorState) -> None:
        self._undo.append(m)
        self._redo.clear()  # mỗi action mới xoá redo

    def undo(self, current: EditorState) -> Optional[EditorState]:
        if not self._undo:
            return None
        self._redo.append(current)
        return self._undo.pop()

    def redo(self, current: EditorState) -> Optional[EditorState]:
        if not self._redo:
            return None
        self._undo.append(current)
        return self._redo.pop()

    def __len__(self) -> int:
        return len(self._undo)


# ============================================================================
# 2. DEMO 1 — Undo / Redo flow
# ============================================================================
def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def edit_with_history(editor: LessonEditor, history: History, action: Callable[[], None]):
    """Helper: snapshot trước, apply, để có thể undo."""
    history.push(editor.save())
    action()


def demo_undo_redo():
    section("Demo 1 — LessonEditor: undo/redo")
    ed = LessonEditor()
    h = History(max_size=10)

    print(f"\n  init: {ed}")
    edit_with_history(ed, h, lambda: ed.set_title("Memento"))
    print(f"  set_title: {ed}")
    edit_with_history(ed, h, lambda: ed.type_text("Hippocampus = "))
    print(f"  type:      {ed}")
    edit_with_history(ed, h, lambda: ed.type_text("episodic snapshot"))
    print(f"  type:      {ed}")
    edit_with_history(ed, h, lambda: ed.add_tag("neuro"))
    print(f"  add_tag:   {ed}")

    print(f"\n  history size: {len(h)}")

    print("\n  undo 2 lần:")
    for _ in range(2):
        m = h.undo(ed.save())
        if m:
            ed.restore(m)
            print(f"    → {ed}")

    print("\n  redo 1 lần:")
    m = h.redo(ed.save())
    if m:
        ed.restore(m)
        print(f"    → {ed}")

    print("\n  edit mới sau undo (xoá redo stack):")
    edit_with_history(ed, h, lambda: ed.type_text(" — branch"))
    print(f"    → {ed}")
    print(f"    redo còn: {len(h._redo)} (đã clear)")


# ============================================================================
# 3. DEMO 2 — 3 failure modes
# ============================================================================
def demo_failure_modes():
    section("Demo 2 — Failure modes của Memento")

    # ----- 2a — Tampering: caretaker peek + cố sửa memento -----
    print("\n[2a] Tampering: caretaker cố sửa memento (frozen → fail)")
    ed = LessonEditor()
    ed.set_title("Original")
    m = ed.save()
    try:
        # Frozen dataclass raise FrozenInstanceError
        m.title = "TAMPERED"
    except Exception as e:
        print(f"  ✓ {type(e).__name__}: {e}")
    print(f"  state vẫn nguyên: {ed}")

    # ----- 2b — Shallow snapshot: dùng list mutable internally (sai) -----
    print("\n[2b] Shallow snapshot trap — minh hoạ tại sao state phải immutable")

    class BadEditor:
        def __init__(self):
            self.body: List[str] = []

        def save(self):
            return self.body  # SAI — return tham chiếu!

        def restore(self, snap):
            self.body = snap

    be = BadEditor()
    be.body.extend(["a", "b"])
    snap = be.save()
    be.body.append("c")  # snapshot bị "leak" vì cùng list
    print(f"  body sau khi append: {be.body}")
    print(f"  snapshot (đáng lẽ ['a','b']): {snap}")
    print(f"  ✗ Snapshot đã bị nhiễm. Sửa = deepcopy() hoặc tuple.")

    # ----- 2c — OOM / unbounded history -----
    print("\n[2c] Unbounded history → OOM. Bounded với deque(maxlen=N) là fix:")
    ed = LessonEditor()
    h = History(max_size=5)
    for i in range(20):
        edit_with_history(ed, h, lambda: ed.type_text("x"))
    print(f"  Sau 20 edit, history giữ tối đa: {len(h)} (max_size=5)")
    print(f"  → Phần đầu bị evict (FIFO ring buffer).")


# ============================================================================
# 4. DEMO 3 — Memento vs Command vs Persistent (3 cách undo)
# ============================================================================
class MementoTextEditor:
    """Cách 1: Memento — full snapshot mỗi lần."""

    def __init__(self):
        self._buf = ""
        self._stack: List[str] = []

    def insert(self, s: str) -> None:
        self._stack.append(self._buf)
        self._buf = self._buf + s

    def undo(self) -> None:
        if self._stack:
            self._buf = self._stack.pop()

    @property
    def buffer(self) -> str:
        return self._buf

    def memory_used_bytes(self) -> int:
        # Xấp xỉ: tổng size mỗi snapshot string
        return sys.getsizeof(self._buf) + sum(sys.getsizeof(s) for s in self._stack)


@dataclass
class InsertCommand:
    text: str
    pos: int

    def apply(self, editor: "CommandTextEditor") -> None:
        editor._buf = editor._buf[: self.pos] + self.text + editor._buf[self.pos :]

    def inverse(self) -> "DeleteCommand":
        return DeleteCommand(start=self.pos, end=self.pos + len(self.text))


@dataclass
class DeleteCommand:
    start: int
    end: int
    deleted: str = ""

    def apply(self, editor: "CommandTextEditor") -> None:
        self.deleted = editor._buf[self.start : self.end]
        editor._buf = editor._buf[: self.start] + editor._buf[self.end :]

    def inverse(self) -> "InsertCommand":
        return InsertCommand(text=self.deleted, pos=self.start)


class CommandTextEditor:
    """Cách 2: Command — lưu inverse op."""

    def __init__(self):
        self._buf = ""
        self._undo_stack: List[Any] = []

    def insert(self, s: str) -> None:
        cmd = InsertCommand(text=s, pos=len(self._buf))
        cmd.apply(self)
        self._undo_stack.append(cmd.inverse())

    def undo(self) -> None:
        if self._undo_stack:
            inv = self._undo_stack.pop()
            inv.apply(self)

    @property
    def buffer(self) -> str:
        return self._buf

    def memory_used_bytes(self) -> int:
        # Xấp xỉ: tổng size object inverse (chỉ giữ slice)
        return sys.getsizeof(self._buf) + sum(
            sys.getsizeof(c) + sys.getsizeof(getattr(c, "deleted", ""))
            for c in self._undo_stack
        )


@dataclass(frozen=True)
class PersistentEditorState:
    buf: str = ""


class PersistentTextEditor:
    """Cách 3: Persistent — state immutable, history = list of state.
    Vì state immutable, không cần copy khi push (str trong Python share content)."""

    def __init__(self):
        self._state = PersistentEditorState()
        self._history: List[PersistentEditorState] = [self._state]

    def insert(self, s: str) -> None:
        self._state = PersistentEditorState(buf=self._state.buf + s)
        self._history.append(self._state)

    def undo(self) -> None:
        if len(self._history) > 1:
            self._history.pop()
            self._state = self._history[-1]

    @property
    def buffer(self) -> str:
        return self._state.buf

    def memory_used_bytes(self) -> int:
        # Lưu ý: với str trong Python, không có structural sharing thật;
        # đây chỉ minh hoạ ý tưởng. Với pyrsistent.PVector thì tiết kiệm thực sự.
        return sum(sys.getsizeof(s.buf) for s in self._history)


def demo_three_undo_strategies():
    section("Demo 3 — Memento vs Command vs Persistent: 3 cách undo")
    OPS = ["Hello", " ", "Memento", " pattern", " for", " undo"]
    EDITORS = {
        "Memento":    MementoTextEditor(),
        "Command":    CommandTextEditor(),
        "Persistent": PersistentTextEditor(),
    }

    print("\n  Apply 6 op insert giống nhau cho 3 editor:")
    for name, ed in EDITORS.items():
        for op in OPS:
            ed.insert(op)
        print(f"    {name:10s} buffer = {ed.buffer!r}")
        print(f"    {name:10s} memory ≈ {ed.memory_used_bytes()} bytes")

    print("\n  Undo 3 lần trên cả 3:")
    for name, ed in EDITORS.items():
        for _ in range(3):
            ed.undo()
        print(f"    {name:10s} buffer sau undo = {ed.buffer!r}")

    print("\n  → Trade-off thực tế:")
    print("    Memento:     đắt memory (full string mỗi snapshot), undo O(1).")
    print("    Command:     rẻ memory (chỉ slice), undo O(op) — đắt nếu undo nhiều bước.")
    print("    Persistent:  state immutable, mỗi version là 1 entry. Cần PVector để share thật sự.")


# ============================================================================
# 5. DEMO 4 — H.M. lesion: disable save() nhưng history cũ vẫn restore
# ============================================================================
class HMLesionedEditor(LessonEditor):
    """Mô phỏng anterograde amnesia: không save() được nữa.
    Trí nhớ cũ (memento đã có) vẫn restore."""

    def save(self) -> EditorState:
        raise RuntimeError(
            "Hippocampus damage (H.M. analog): cannot encode new memento"
        )


def demo_hm_lesion():
    section("Demo 4 — H.M. lesion: anterograde amnesia analog")
    ed = LessonEditor()
    h = History(max_size=10)

    # Tích luỹ memento "trước phẫu thuật"
    edit_with_history(ed, h, lambda: ed.type_text("pre-op memory 1"))
    edit_with_history(ed, h, lambda: ed.type_text(" + 2"))
    print(f"\n  Pre-op state: {ed}")
    print(f"  History (consolidated): {len(h)} memento")

    # "Phẫu thuật" — replace editor (giữ state hiện tại) bằng phiên bản lesioned
    lesioned = HMLesionedEditor()
    lesioned._state = ed._state  # state hiện tại còn

    print(f"\n  Sau lesion: {lesioned}")
    print("  Thử save() (encoding mới):")
    try:
        lesioned.save()
    except RuntimeError as e:
        print(f"    ✗ {e}")

    print("\n  Restore từ history cũ (trí nhớ pre-op còn nguyên):")
    m = h.undo(lesioned._state)  # giả sử có method query không cần save
    if m:
        lesioned.restore(m)
        print(f"    → {lesioned}")
    print("\n  Bài học: Originator có thể hỏng, Caretaker vẫn restore được.")
    print("  Đó là lý do thiết kế Memento KHÔNG nên phụ thuộc Originator còn sống —")
    print("  pickle được, có version migration, có thể load offline.")


# ============================================================================
# 6. RUNNER
# ============================================================================
def main():
    demo_undo_redo()
    demo_failure_modes()
    demo_three_undo_strategies()
    demo_hm_lesion()
    print("\n" + "=" * 70)
    print("  Hết demo Lesson 18 — Memento (Hippocampus).")
    print("=" * 70)


if __name__ == "__main__":
    main()
