"""Run checkpoints: persist loop state to var/agent_runs/<run_id>/checkpoint.json so a run can resume. Epic E07."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.schemas import TaskEnvelope
from observability.event_log import runs_dir


def checkpoint_path(run_id: str) -> Path:
    return runs_dir() / run_id / "checkpoint.json"


def _encode_state(state: dict[str, Any]) -> dict[str, Any]:
    out = dict(state)
    task = out.get("current_task")
    if isinstance(task, TaskEnvelope):
        out["current_task"] = {"__task__": task.as_dict()}
    return out


def _decode_state(state: dict[str, Any]) -> dict[str, Any]:
    out = dict(state)
    task = out.get("current_task")
    if isinstance(task, dict) and "__task__" in task:
        out["current_task"] = TaskEnvelope.from_dict(task["__task__"])
    return out


@dataclass
class Checkpoint:
    run_id: str
    task: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    step: int = 0
    status: str = "running"

    def to_json(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "task": self.task, "messages": self.messages,
                "budget": self.budget, "state": _encode_state(self.state),
                "step": self.step, "status": self.status}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Checkpoint":
        return cls(run_id=d["run_id"], task=d.get("task", ""), messages=d.get("messages", []),
                   budget=d.get("budget", {}), state=_decode_state(d.get("state", {})),
                   step=d.get("step", 0), status=d.get("status", "running"))


def save_checkpoint(cp: Checkpoint, *, enabled: bool = True) -> None:
    if not enabled:
        return
    path = checkpoint_path(cp.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cp.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a crash mid-write never corrupts the checkpoint


def load_checkpoint(run_id: str) -> Checkpoint | None:
    path = checkpoint_path(run_id)
    if not path.exists():
        return None
    return Checkpoint.from_json(json.loads(path.read_text(encoding="utf-8")))
