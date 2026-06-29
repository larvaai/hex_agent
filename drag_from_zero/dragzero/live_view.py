"""Minimal live view — renders the read-model tree to text.

The eventual React Flow UI is just another consumer of the same projection; this
CLI renderer proves the projection is sufficient on its own.
"""
from __future__ import annotations

from typing import Optional

from .contracts import TaskStatus
from .read_model import TaskNode, reduce

GLYPH = {
    TaskStatus.PENDING.value: "○",
    TaskStatus.RUNNING.value: "◐",
    TaskStatus.WAITING.value: "⌛",
    TaskStatus.DELEGATED.value: "◇",
    TaskStatus.DONE.value: "●",
    TaskStatus.FAILED.value: "✗",
    TaskStatus.HALTED.value: "⏸",
    TaskStatus.BLOCKED.value: "⛔",
}

_TERMINAL = {TaskStatus.DONE.value, TaskStatus.FAILED.value}


def render_tree(root: Optional[TaskNode]) -> str:
    if root is None:
        return "(empty)"
    lines: list[str] = []

    def walk(node: TaskNode, prefix: str, is_last: bool, is_root: bool) -> None:
        glyph = GLYPH.get(node.status, "·")
        connector = "" if is_root else ("└─ " if is_last else "├─ ")
        head = f"{prefix}{connector}{glyph} {node.description} [{node.status}]"
        if node.agent_id:
            head += f"  @{node.agent_id}"
        if node.next_step and node.status not in _TERMINAL:
            head += f"  → next: {node.next_step}"
        if node.blocked_on and node.status == TaskStatus.WAITING.value:
            head += f"  ⌛ for: {node.blocked_on}"
        if node.tools:
            head += "  ⚙ " + " ".join(f"{t['tool']}{'✓' if t['ok'] else '✗'}" for t in node.tools)
        lines.append(head)
        child_prefix = prefix + ("   " if is_root else ("    " if is_last else "│   "))
        for i, child in enumerate(node.children):
            walk(child, child_prefix, i == len(node.children) - 1, False)

    walk(root, "", True, True)
    return "\n".join(lines)


def render_log(events) -> str:
    return "\n".join(
        f"#{e.seq:02d} {e.type.value:<18} {e.task_id or '-':<4} {e.payload}" for e in events
    )


def render(events) -> str:
    root, _ = reduce(events if isinstance(events, list) else list(events))
    return render_tree(root)
