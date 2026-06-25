"""Realtime Control Plane — contracts. Epic E21 (Phase A · S-CONTRACT).

A thin layer ABOVE the frozen kernel (like ``supervisor``): the infra-independent
contracts every part of the control plane shares — RuntimeEvent envelope, RuntimeCommand,
RuntimeCheckpoint, Permission, Redactor — plus the event/command type registries. No I/O
here; transport/storage (SQLite/JSONL/EventBus now, Kafka/Redis/Postgres behind ports
later) arrives in Phase B/C. See docs/spec/active/E21-realtime-control-plane/.
"""
from __future__ import annotations

from control.checkpoint import (
    CHECKPOINT_STATUSES,
    RESOLVED_STATUSES,
    RISK_LEVELS,
    RuntimeCheckpoint,
)
from control.command_registry import (
    APPLY_AT,
    CommandTypeRegistry,
    CommandTypeSpec,
    load_command_registry,
    parse_command_registry,
)
from control.commands import ISSUER_TYPES, IssuedBy, RuntimeCommand, parse_command
from control.emitter import BusEventSink, EventEmitter, bus_emitter
from control.errors import ControlContractError
from control.event_registry import (
    EventTypeRegistry,
    EventTypeSpec,
    load_event_registry,
    parse_event_registry,
)
from control.events import (
    ACTOR_TYPES,
    VISIBILITY_LEVELS,
    Actor,
    RedactionInfo,
    RuntimeEvent,
    SessionSeq,
    TraceContext,
    utc_now,
)
from control.permission import EFFECTIVE_FROM, Permission
from control.ports import EventSinkPort
from control.redaction import REDACTED, SECRET_KEYS, Redactor

__all__ = [
    # errors
    "ControlContractError",
    # event envelope
    "RuntimeEvent",
    "Actor",
    "TraceContext",
    "RedactionInfo",
    "SessionSeq",
    "ACTOR_TYPES",
    "VISIBILITY_LEVELS",
    "utc_now",
    # event registry
    "EventTypeRegistry",
    "EventTypeSpec",
    "load_event_registry",
    "parse_event_registry",
    # command
    "RuntimeCommand",
    "IssuedBy",
    "parse_command",
    "ISSUER_TYPES",
    # command registry
    "CommandTypeRegistry",
    "CommandTypeSpec",
    "load_command_registry",
    "parse_command_registry",
    "APPLY_AT",
    # checkpoint
    "RuntimeCheckpoint",
    "CHECKPOINT_STATUSES",
    "RESOLVED_STATUSES",
    "RISK_LEVELS",
    # permission
    "Permission",
    "EFFECTIVE_FROM",
    # redaction
    "Redactor",
    "SECRET_KEYS",
    "REDACTED",
    # emitter + ports (B1)
    "EventEmitter",
    "BusEventSink",
    "bus_emitter",
    "EventSinkPort",
]
