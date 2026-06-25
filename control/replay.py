"""EventReplayBuffer — the bounded event store the fake SSE layer streams + resyncs from. Epic E21 (S21.16).

A ring buffer (D4: 2048 events/session) over the canonical event dicts. It does three jobs the
real transport must also do, so building the UI against it is honest:

* **dedup by ``event_id``** — reality injects at-least-once delivery (same event_id, sometimes a
  re-stamped seq, red-team F9/F15); the buffer keeps each event_id once.
* **Last-Event-ID catch-up** — ``events_after(seq)`` returns only later events, ordered by seq, so
  a reconnecting client never re-sees what it already has (S21.16).
* **out-of-ring resync signal** — ``needs_resync(seq)`` is true when the client's last seq fell off
  the ring; the server then tells it to re-fetch the snapshot instead of silently losing events (F7).

Kept separate from the HTTP layer so it is pure and unit-testable.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


class EventReplayBuffer:
    def __init__(self, maxlen: int = 2048) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._ids: set[str] = set()

    def append(self, event: dict[str, Any]) -> bool:
        """Add one event dict. A duplicate ``event_id`` is dropped (returns False)."""
        eid = str(event.get("event_id", ""))
        if eid and eid in self._ids:
            return False
        # The deque is about to evict its oldest member — forget that id so it can return later.
        if self._events.maxlen is not None and len(self._events) == self._events.maxlen and self._events:
            self._ids.discard(str(self._events[0].get("event_id", "")))
        self._events.append(event)
        if eid:
            self._ids.add(eid)
        return True

    def load_jsonl(self, path: str | Path) -> int:
        """Load events from a JSONL fixture (one event dict per line). Returns the count added."""
        added = 0
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                if self.append(json.loads(line)):
                    added += 1
        return added

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def oldest_seq(self) -> int:
        return min((int(e.get("seq", 0)) for e in self._events), default=0)

    def newest_seq(self) -> int:
        return max((int(e.get("seq", 0)) for e in self._events), default=0)

    def needs_resync(self, last_seq: int) -> bool:
        """True when the client's last-seen seq is older than anything still in the ring — the
        events between were evicted, so a plain catch-up would silently skip them (F7)."""
        if last_seq <= 0:
            return False
        return self.oldest_seq() > last_seq + 1

    def events_after(self, last_seq: int) -> list[dict[str, Any]]:
        """Events with ``seq > last_seq``, ordered by seq, each event_id at most once."""
        ordered = sorted(self._events, key=lambda e: int(e.get("seq", 0)))
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for e in ordered:
            if int(e.get("seq", 0)) <= last_seq:
                continue
            eid = str(e.get("event_id", ""))
            if eid and eid in seen:
                continue
            seen.add(eid)
            out.append(e)
        return out
