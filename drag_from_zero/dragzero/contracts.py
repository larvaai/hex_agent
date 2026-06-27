"""Structured contracts. Delegation is a first-class artifact, not a hidden call."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DelegationMode(str, Enum):
    SOLO = "solo"
    DELEGATE = "delegate"
    DECOMPOSE = "decompose"  # split into done_when-gated children (Gap 2)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    DELEGATED = "delegated"
    DONE = "done"
    FAILED = "failed"
    HALTED = "halted"
    BLOCKED = "blocked"


@dataclass
class PlanStep:
    id: str
    description: str
    status: str = "pending"

    @classmethod
    def from_dict(cls, d: dict) -> "PlanStep":
        return cls(id=d["id"], description=d["description"], status=d.get("status", "pending"))

    def to_dict(self) -> dict:
        return {"id": self.id, "description": self.description, "status": self.status}


@dataclass
class PlanSpec:
    steps: list = field(default_factory=list)
    next: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "PlanSpec":
        return cls(steps=[PlanStep.from_dict(s) for s in d.get("steps", [])], next=d.get("next"))

    def to_dict(self) -> dict:
        return {"steps": [s.to_dict() for s in self.steps], "next": self.next}


@dataclass
class ToolCall:
    tool: str
    args: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ToolCall":
        return cls(tool=d.get("tool", ""), args=d.get("args") if isinstance(d.get("args"), dict) else {})

    def to_dict(self) -> dict:
        return {"tool": self.tool, "args": self.args}


@dataclass
class TriageResult:
    """The entry worker's classification of raw input (Slice D1). The worker PROPOSES;
    CODE adjudicates the done_when downstream. `kind` defaults to the safe 'answer' branch
    so a garbled reply never crashes the orchestrator or fabricates a task."""

    kind: str = "answer"                 # "answer" | "task"
    text: Optional[str] = None           # answer branch
    goal: Optional[str] = None           # task branch
    done_when: list = field(default_factory=list)
    reasoning: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "TriageResult":
        if not isinstance(d, dict):
            return cls()
        kind = d.get("kind") if d.get("kind") in ("answer", "task") else "answer"
        return cls(
            kind=kind,
            text=d.get("text"),
            goal=d.get("goal"),
            done_when=list(d.get("done_when") or []),
            reasoning=d.get("reasoning", ""),
        )


@dataclass
class DelegationDecision:
    mode: DelegationMode
    target: Optional[str] = None
    subtask: Optional[str] = None
    reasoning: str = ""
    children: list = field(default_factory=list)  # decompose mode: [{id, goal, done_when, depends_on}]

    @classmethod
    def from_dict(cls, d: dict) -> "DelegationDecision":
        return cls(
            mode=DelegationMode(d["mode"]),
            target=d.get("target"),
            subtask=d.get("subtask"),
            reasoning=d.get("reasoning", ""),
            children=list(d.get("children") or []),
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "target": self.target,
            "subtask": self.subtask,
            "reasoning": self.reasoning,
            "children": self.children,
        }
