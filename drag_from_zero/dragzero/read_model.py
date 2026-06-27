"""Execution Tree (Đồ thị 2) — a pure projection (read-model) folded from events.

`reduce` is a fold over the event log. It holds no state of its own: feed it the
same events and you get the same tree. The live view renders this, not a
parallel source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .contracts import TaskStatus
from .events import Event, EventType


@dataclass
class TaskNode:
    id: str
    description: str
    parent_id: Optional[str]
    status: str = TaskStatus.PENDING.value
    agent_id: Optional[str] = None
    next_step: Optional[str] = None
    blocked_on: Optional[str] = None
    tools: list = field(default_factory=list)
    children: list = field(default_factory=list)
    done_when: list = field(default_factory=list)  # Gap 2: carried from the spawning/root event


@dataclass
class TaskBox:
    """A materialized task box (Slice D1) — the inbox read-model's unit. status: 'materialized'
    (done_when present + adjudicated), 'unverified' (no criteria yet), or 'rejected' (forged)."""

    goal: Optional[str]
    done_when: list = field(default_factory=list)
    status: str = "materialized"
    reason: Optional[str] = None  # rejected branch only


def reduce_inbox(events: list[Event]) -> dict:
    """Fold the 4 triage events into the inbox view {answers, task_boxes}. Pure, like `reduce`:
    same events → same view. The execution tree (`reduce`) is untouched — this is a sibling
    projection over a disjoint event set."""
    answers: list = []
    boxes: list = []
    for e in events:
        if e.type == EventType.ANSWER_PRODUCED:
            answers.append(e.payload.get("text", ""))
        elif e.type == EventType.TASK_BOX_CREATED:
            dw = list(e.payload.get("done_when") or [])
            boxes.append(TaskBox(e.payload.get("goal"), dw,
                                 status="materialized" if dw else "unverified"))
        elif e.type == EventType.TASK_BOX_REJECTED:
            boxes.append(TaskBox(e.payload.get("goal"), status="rejected", reason=e.payload.get("reason")))
    return {"answers": answers, "task_boxes": boxes}


def reduce(events: list[Event]) -> tuple[Optional[TaskNode], dict]:
    nodes: dict = {}
    root_id: Optional[str] = None

    for e in events:
        t = e.type
        if t == EventType.ROOT_TASK_CREATED:
            node = TaskNode(e.task_id, e.payload.get("description", ""), None, done_when=list(e.payload.get("done_when") or []))
            nodes[e.task_id] = node
            root_id = e.task_id
        elif t == EventType.SUBTASK_SPAWNED:
            parent = e.payload.get("parent")
            node = TaskNode(e.task_id, e.payload.get("subtask", ""), parent, agent_id=e.agent_id,
                            done_when=list(e.payload.get("done_when") or []))
            nodes[e.task_id] = node
            if parent in nodes:
                nodes[parent].children.append(node)
        elif t == EventType.TASK_WAITING:
            if e.task_id in nodes:
                nodes[e.task_id].status = TaskStatus.WAITING.value
                nodes[e.task_id].blocked_on = e.payload.get("target")
        elif t == EventType.TOOL_RESULT:
            if e.task_id in nodes:
                nodes[e.task_id].tools.append({"tool": e.payload.get("tool"), "ok": e.payload.get("ok")})
        elif t == EventType.TOOL_DENIED:
            if e.task_id in nodes:
                nodes[e.task_id].tools.append({"tool": e.payload.get("tool"), "ok": False, "denied": True})
        elif t == EventType.TASK_STARTED:
            if e.task_id in nodes:
                nodes[e.task_id].status = TaskStatus.RUNNING.value
                nodes[e.task_id].agent_id = e.agent_id
        elif t == EventType.PLAN_PRODUCED:
            if e.task_id in nodes:
                nodes[e.task_id].next_step = e.payload.get("plan", {}).get("next")
        elif t == EventType.DELEGATION_DECIDED:
            if e.task_id in nodes and e.payload.get("decision", {}).get("mode") in ("delegate", "decompose"):
                nodes[e.task_id].status = TaskStatus.DELEGATED.value
        elif t == EventType.DECOMPOSITION_ACCEPTED:  # a decomposed parent is DELEGATED until compose
            if e.task_id in nodes:
                nodes[e.task_id].status = TaskStatus.DELEGATED.value
        elif t == EventType.TASK_COMPLETED:
            if e.task_id in nodes:
                nodes[e.task_id].status = TaskStatus.DONE.value
        elif t == EventType.TASK_FAILED:
            if e.task_id in nodes:
                nodes[e.task_id].status = TaskStatus.FAILED.value
        elif t == EventType.HOOK_BLOCKED:
            if e.task_id in nodes:
                nodes[e.task_id].status = TaskStatus.BLOCKED.value
        elif t == EventType.BUDGET_EXCEEDED:
            if e.task_id in nodes:
                nodes[e.task_id].status = TaskStatus.HALTED.value

    return (nodes.get(root_id) if root_id else None), nodes
