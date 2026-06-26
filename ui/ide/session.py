"""IdeSession — the live event buffer + diff baseline behind one IDE session. Epic E21 / IDE.

The fake control server replays a fixed fixture and closes the stream. A live IDE needs the
mirror image: one growing event buffer per session that the agent run feeds and the held-open SSE
socket drains. ``IdeSession`` owns that buffer plus the per-session bits the fake kept as loose
fields — the monotonic ``seq`` allocator, the ``Redactor``, the trace, and (new) the file
*baseline* the diff endpoint subtracts from.

It reuses the same ``control/`` pieces the contract is built on (``RuntimeEvent`` envelope,
``EventReplayBuffer`` ring + resync, ``Redactor``, the event registry's visibility), so the wire
the UI reads is byte-identical to the fake's — only now the events are real.

Thread model: the agent runs in a worker thread and calls ``emit``; the SSE handler thread calls
``drain``. A single ``Condition`` serialises both and lets a draining reader sleep until the next
event instead of busy-polling. The contract-honest invariant — stream only the redacted
``ui_payload`` — is preserved because ``emit`` stores the ``Redactor``-applied event.
"""
from __future__ import annotations

import threading
from typing import Any

from control.errors import ControlContractError
from control.event_registry import EventTypeRegistry, load_event_registry
from control.events import Actor, RedactionInfo, RuntimeEvent, TraceContext
from control.redaction import Redactor
from control.replay import EventReplayBuffer


class IdeSession:
    def __init__(
        self,
        session_id: str,
        *,
        event_registry: EventTypeRegistry | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self.session_id = session_id
        self.buffer = EventReplayBuffer()
        self.event_registry = event_registry or load_event_registry()
        self.redactor = redactor or Redactor()
        self._trace = TraceContext.new_root()
        self._seq = 0
        self._cond = threading.Condition()
        # Run lifecycle the server reports out-of-band (the snapshot status comes from the fold).
        self.run_status = "idle"  # idle | running | finished | failed
        self.last_prompt = ""
        # Diff baseline: {relpath: content} captured at run start; the diff endpoint subtracts it.
        self.baseline: dict[str, str] = {}
        self.baseline_scope = "workspace"

    # ── visibility ────────────────────────────────────────────────────────────
    def visibility(self, event_type: str) -> str:
        try:
            return self.event_registry.visibility(event_type)
        except ControlContractError:
            return "ui_safe"

    # ── emit (the one place an event enters the buffer) ─────────────────────────
    def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        actor: Actor | None = None,
        round_no: int | None = None,
    ) -> int:
        """Stamp seq, redact, append, and wake any draining SSE reader. Returns the seq."""
        with self._cond:
            self._seq += 1
            seq = self._seq
            level = self.visibility(event_type)
            event = RuntimeEvent(
                event_type=event_type,
                session_id=self.session_id,
                actor=actor or Actor(type="system", id="orchestrator"),
                trace=self._trace,
                redaction=RedactionInfo(level=level),
                payload=dict(payload),
                seq=seq,
                round_no=round_no,
            )
            final = self.redactor.apply(event, level=level).as_dict()
            self.buffer.append(final)
            self._cond.notify_all()
        return seq

    def next_seq(self) -> int:
        with self._cond:
            self._seq += 1
            return self._seq

    # ── stream drain (atomic check-or-wait, no busy poll) ───────────────────────
    def drain(self, last_seq: int, timeout: float) -> tuple[list[dict[str, Any]], bool]:
        """Return (events with seq>last_seq, needs_resync). Sleeps up to ``timeout`` if nothing new."""
        with self._cond:
            if self.buffer.newest_seq() <= last_seq:
                self._cond.wait(timeout)
            return self.buffer.events_after(last_seq), self.buffer.needs_resync(last_seq)

    def events(self) -> list[dict[str, Any]]:
        with self._cond:
            return self.buffer.events

    def set_status(self, status: str) -> None:
        with self._cond:
            self.run_status = status
            self._cond.notify_all()
