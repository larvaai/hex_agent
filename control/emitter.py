"""EventEmitter — the one validated, redacted, sequenced publish path. Epic E21 (B1).

Replaces ad-hoc ``bus.publish(topic, dict)``. Every control-plane event goes through
``emit``/``emit_event``:

1. the ``event_type`` is checked against the registry (unknown → ControlContractError);
2. ``seq`` is stamped monotonically per session (if not already set);
3. the Redactor fills ``ui_payload`` at the type's visibility, so no sink ever receives
   raw secrets it shouldn't;
4. the finalized event is forwarded to each ``EventSinkPort``.

``BusEventSink`` adapts the in-process ``EventBus`` so existing subscribers (the
``EventLogger`` JSONL writer) persist the envelope unchanged. Swapping in Kafka later is a
new sink, not a caller change.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from control.event_registry import EventTypeRegistry, load_event_registry
from control.events import Actor, RedactionInfo, RuntimeEvent, SessionSeq, TraceContext
from control.ports import EventSinkPort
from control.redaction import Redactor
from core.events import EventBus


class BusEventSink:
    """Adapts the in-process EventBus to EventSinkPort: publishes the envelope dict under
    ``topic=event_type`` so existing bus subscribers (e.g. EventLogger) persist it."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, event.as_dict())


class EventEmitter:
    def __init__(
        self,
        sinks: Iterable[EventSinkPort],
        *,
        registry: EventTypeRegistry | None = None,
        redactor: Redactor | None = None,
        seq: SessionSeq | None = None,
    ) -> None:
        self._sinks = list(sinks)
        self._registry = registry or load_event_registry()
        self._redactor = redactor or Redactor()
        self._seq = seq or SessionSeq()

    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        """Validate, stamp seq, redact, then fan out to sinks. Returns the finalized event.
        An unknown event_type raises before anything is published (registry is the gate)."""
        spec = self._registry.get(event.event_type)  # ControlContractError if unknown
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        final = self._redactor.apply(staged, level=spec.visibility)
        for sink in self._sinks:
            sink.emit(final)
        return final

    def emit(
        self,
        event_type: str,
        *,
        session_id: str,
        actor: Actor,
        trace: TraceContext,
        payload: dict | None = None,
        round_no: int | None = None,
        task_id: str | None = None,
        workflow_id: str | None = None,
        source: str = "runtime",
    ) -> RuntimeEvent:
        """Convenience builder. ``redaction`` is a placeholder here — ``emit_event`` fills the
        real level/fields from the registry + Redactor."""
        event = RuntimeEvent(
            event_type=event_type,
            session_id=session_id,
            actor=actor,
            trace=trace,
            redaction=RedactionInfo(),
            payload=dict(payload or {}),
            round_no=round_no,
            task_id=task_id,
            workflow_id=workflow_id,
            source=source,
        )
        return self.emit_event(event)


def bus_emitter(bus: EventBus, **kwargs) -> EventEmitter:
    """An EventEmitter wired to publish onto the given in-process EventBus (v1 default)."""
    return EventEmitter([BusEventSink(bus)], **kwargs)
