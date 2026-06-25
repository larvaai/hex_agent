"""EventLogger — JSONL event log + summary.json + metrics; subscribes to the EventBus. Epic E04."""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.events import EventBus

PROJECT_DIR = Path(__file__).resolve().parent.parent
_INDEX_LOCK = threading.RLock()

_METRICS = (
    "steps",
    "llm_calls",
    "llm_failures",
    "tool_calls",
    "tool_failures",
    "parse_errors",
    "policy_blocks",
    "finish_gate_blocks",
    "condensed",
    "delegations",
    "delegation_progress",
    "delegation_failures",
)


def runs_dir() -> Path:
    return Path(os.getenv("AGENT_RUNS_DIR", str(PROJECT_DIR / "var" / "agent_runs")))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLogger:
    def __init__(self, run_id: str | None = None, *, enabled: bool | None = None) -> None:
        self.enabled = (os.getenv("AGENT_EVENT_LOG", "1") != "0") if enabled is None else enabled
        self._lock = threading.RLock()
        if run_id is not None and (
            os.path.isabs(run_id) or ".." in run_id or "/" in run_id or "\\" in run_id
        ):
            # run_id becomes a directory name under runs_dir(); a path-like value would escape it.
            raise ValueError(f"run_id must be a single path segment, not path-like: {run_id!r}")
        self.run_id = run_id or (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
        self.seq = 0
        self._finished = False
        self.metrics: dict[str, int] = {k: 0 for k in _METRICS}
        self.run_dir = runs_dir() / self.run_id
        self.events_path = self.run_dir / "events.jsonl"
        if self.enabled:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        self.emit("StateEvent", status="run_started")

    def emit(self, kind: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            self.seq += 1
            event = {
                "sequence": self.seq,
                "timestamp": _now(),
                "run_id": self.run_id,
                "kind": kind,
                **fields,
            }
            if self.enabled:
                with self.events_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            return event

    def count(self, metric: str, n: int = 1) -> None:
        with self._lock:
            if metric in self.metrics:
                self.metrics[metric] += n

    def finish(self, status: str = "completed", **extra: Any) -> dict[str, Any]:
        with self._lock:
            first = not self._finished
            self._finished = True
            summary = {"run_id": self.run_id, "status": status, "metrics": dict(self.metrics), **extra}
        # Side effects (terminal event, summary, index entry) run exactly once; later
        # calls still return the summary so callers stay simple.
        if not first:
            return summary
        self.emit("StateEvent", status="run_finished", result_status=status)
        if self.enabled:
            (self.run_dir / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            with _INDEX_LOCK:
                with (runs_dir() / "index.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps({"run_id": self.run_id, "status": status}, ensure_ascii=False) + "\n"
                    )
        return summary


def attach_to_bus(logger: EventLogger, bus: EventBus) -> None:
    """Mirror kernel events into the event log and update metrics."""

    def sink(topic: str, payload: dict[str, Any]) -> None:
        tool = payload.get("tool", "")
        is_llm = isinstance(tool, str) and tool.startswith("llm.")
        # LLM calls recorded under a distinct kind so events.jsonl is filterable;
        # transport stays uniform (tool.*) so the chokepoint need not special-case LLM.
        logger.emit("LLMCallEvent" if is_llm else "KernelEvent", topic=topic, **payload)
        if topic == "tool.completed":
            logger.count("tool_calls")
            if is_llm:
                logger.count("llm_calls")
        elif topic == "tool.failed":
            logger.count("tool_calls")
            logger.count("tool_failures")
            if is_llm:
                logger.count("llm_calls")
                logger.count("llm_failures")
        elif topic == "graph.step":
            logger.count("steps")
        elif topic == "graph.parse_error":
            logger.count("parse_errors")
        elif topic == "graph.finish_blocked":
            logger.count("finish_gate_blocks")
        elif topic == "delegation.started":
            logger.count("delegations")
        elif topic == "delegation.progress":
            logger.count("delegation_progress")
        elif topic == "delegation.finished" and payload.get("outcome") != "success":
            logger.count("delegation_failures")

    bus.subscribe(sink)
