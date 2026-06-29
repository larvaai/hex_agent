"""Disk-is-the-only-truth — an append-only JSONL ledger of events (design doc theme 5).

The in-memory EventLog is a cache; the ledger on disk is the truth. Every appended event is
flushed as one JSON line, seq-stamped, so a crash loses at most the tail line. The reader is
corruption-tolerant: a truncated or non-dict last line (a half-written crash record) is dropped,
not fatal — `reduce` over the survivors still yields a coherent tree, and resume = re-read + fold.

No RLock, no metric table (the doc explicitly drops them): one process, one cursor, one writer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .events import Event, EventType


def event_to_dict(e: Event) -> dict:
    return {"seq": e.seq, "type": e.type.value, "task_id": e.task_id, "agent_id": e.agent_id, "payload": e.payload}


def event_from_dict(d: dict) -> Event:
    return Event(
        type=EventType(d["type"]),
        seq=int(d.get("seq", -1)),
        task_id=d.get("task_id"),
        agent_id=d.get("agent_id"),
        payload=d.get("payload") or {},
    )


class Ledger:
    """Append-only JSONL writer + corruption-tolerant reader. `path` is created on first write."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: Event) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event_to_dict(event), ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())  # the line is durable before append() returns

    def read(self) -> list[Event]:
        """Fold the ledger back into Events. A truncated/non-dict tail line is dropped (crash
        half-write), never raised — every clean prefix line survives."""
        if not self.path.exists():
            return []
        out: list[Event] = []
        for raw in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                break  # a torn line can only be the tail; everything after is suspect too
            if not isinstance(d, dict) or "type" not in d:
                break
            try:
                out.append(event_from_dict(d))
            except (KeyError, ValueError):
                break
        return out
