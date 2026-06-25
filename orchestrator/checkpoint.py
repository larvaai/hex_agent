"""LangGraph SQLite persistence plus a JSON run-state projection for the local UI."""
from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from langgraph.checkpoint.sqlite import SqliteSaver

from core.schemas import TaskEnvelope
from graph.state import AgentState, decode_session_state
from observability.event_log import runs_dir


# Serializes the rename step: on Windows, concurrent os.replace() calls targeting the
# same destination race and raise PermissionError ("Access is denied").
_REPLACE_LOCK = threading.Lock()


def checkpoint_path(run_id: str) -> Path:
    """Compatibility projection path. It is not used to resume a graph."""
    return runs_dir() / run_id / "checkpoint.json"


def checkpoint_db_path(run_id: str) -> Path:
    """One SQLite database per run avoids cross-run locking and is easy to archive."""
    return runs_dir() / run_id / "langgraph.sqlite"


@contextmanager
def open_checkpointer(run_id: str) -> Iterator[SqliteSaver]:
    path = checkpoint_db_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver


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
    """Stable UI/read-model schema retained for compatibility with existing callers."""

    run_id: str
    task: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    step: int = 0
    status: str = "running"
    backend: str = "legacy-json"
    schema_version: int = 2

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "messages": self.messages,
            "budget": self.budget,
            "state": _encode_state(self.state),
            "step": self.step,
            "status": self.status,
            "backend": self.backend,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Checkpoint":
        run_id = data.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("Checkpoint JSON requires a non-empty string 'run_id'.")
        return cls(
            run_id=run_id,
            task=data.get("task", ""),
            messages=data.get("messages", []),
            budget=data.get("budget", {}),
            state=_decode_state(data.get("state", {})),
            step=data.get("step", 0),
            status=data.get("status", "running"),
            backend=data.get("backend", "legacy-json"),
            schema_version=data.get("schema_version", 1),
        )

    @classmethod
    def from_graph_state(cls, state: AgentState) -> "Checkpoint":
        budget = dict(state.get("budget") or {})
        return cls(
            run_id=str(state.get("run_id", "")),
            task=str(state.get("task", "")),
            messages=list(state.get("messages") or []),
            budget=budget,
            state=decode_session_state(
                state.get("session_state") or state.get("kernel_state") or {}
            ),
            step=int(budget.get("steps", 0)),
            status=str(state.get("status") or "running"),
            backend="langgraph",
        )


def save_checkpoint(checkpoint: Checkpoint, *, enabled: bool = True) -> None:
    """Atomically update the UI projection; LangGraph SQLite remains authoritative."""
    if not enabled:
        return
    path = checkpoint_path(checkpoint.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp name per write: concurrent writers to the same run must not share a
    # temp file (a shared name races os.replace and raises a sharing violation on Windows).
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(checkpoint.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    with _REPLACE_LOCK:
        os.replace(tmp, path)


def save_graph_projection(state: AgentState, *, enabled: bool = True) -> None:
    save_checkpoint(Checkpoint.from_graph_state(state), enabled=enabled)


def load_checkpoint(run_id: str) -> Checkpoint | None:
    """Read the UI projection. Resume intentionally does not call this function."""
    path = checkpoint_path(run_id)
    if not path.exists():
        return None
    return Checkpoint.from_json(json.loads(path.read_text(encoding="utf-8")))
