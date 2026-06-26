"""EventLog append/seq/subscribe/filters + Event frozen-dataclass invariants."""
import dataclasses

import pytest

from dragzero.events import Event, EventLog, EventType


def test_append_stamps_monotonic_seq_from_zero_and_returns_stamped():
    log = EventLog()
    a = log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    b = log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    assert a.seq == 0
    assert b.seq == 1
    # the returned object is the stamped one, not the caller's
    assert a.type is EventType.TASK_STARTED
    assert a.task_id == "t1"


def test_append_returns_stamped_not_input_object():
    log = EventLog()
    incoming = Event(EventType.TASK_STARTED, task_id="t1")
    assert incoming.seq == -1  # default sentinel before stamping
    stamped = log.append(incoming)
    assert stamped.seq == 0
    assert incoming.seq == -1  # frozen input untouched


def test_subscribe_fires_on_every_append_with_stamped_event():
    log = EventLog()
    seen: list[Event] = []
    log.subscribe(seen.append)
    log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    assert [e.seq for e in seen] == [0, 1]
    assert [e.type for e in seen] == [EventType.TASK_STARTED, EventType.TASK_COMPLETED]


def test_subscribe_after_appends_only_sees_future_events():
    log = EventLog()
    log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    seen: list[Event] = []
    log.subscribe(seen.append)
    log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    assert [e.seq for e in seen] == [1]


def test_of_type_filters():
    log = EventLog()
    log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    log.append(Event(EventType.TOOL_CALLED, task_id="t1"))
    log.append(Event(EventType.TASK_STARTED, task_id="t2"))
    started = log.of_type(EventType.TASK_STARTED)
    assert [e.task_id for e in started] == ["t1", "t2"]
    assert log.of_type(EventType.HOOK_BLOCKED) == []


def test_types_returns_type_sequence_in_order():
    log = EventLog()
    log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    log.append(Event(EventType.TOOL_CALLED, task_id="t1"))
    log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    assert log.types() == [
        EventType.TASK_STARTED,
        EventType.TOOL_CALLED,
        EventType.TASK_COMPLETED,
    ]


def test_len_and_iter():
    log = EventLog()
    assert len(log) == 0
    log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    assert len(log) == 2
    assert [e.seq for e in log] == [0, 1]


def test_events_returns_a_copy():
    log = EventLog()
    log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    snapshot = log.events()
    snapshot.append(Event(EventType.TASK_FAILED, task_id="t1"))
    snapshot.clear()
    # mutating the returned list must not touch the log
    assert len(log) == 1
    assert len(log.events()) == 1


def test_event_is_frozen_dataclass():
    e = Event(EventType.TASK_STARTED, task_id="t1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.seq = 99  # type: ignore[misc]


def test_event_defaults():
    e = Event(EventType.TASK_STARTED, task_id="t1")
    assert e.seq == -1
    assert e.agent_id is None
    assert e.payload == {}
