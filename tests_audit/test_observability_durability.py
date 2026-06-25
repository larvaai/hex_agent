"""Durability, concurrency, metric mapping and inspection CLI tests."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.events import EventBus
from observability import EventLogger, attach_to_bus
from observability import inspect as inspect_cli


@pytest.mark.audit
def test_bus_topic_to_metric_mapping_is_exact_and_non_overlapping():
    bus = EventBus()
    logger = EventLogger("metrics", enabled=False)
    attach_to_bus(logger, bus)
    cases = [
        ("tool.completed", {"tool": "echo"}, {"tool_calls": 1}),
        ("tool.failed", {"tool": "echo"}, {"tool_calls": 1, "tool_failures": 1}),
        ("tool.completed", {"tool": "llm.chat"}, {"tool_calls": 1, "llm_calls": 1}),
        ("tool.failed", {"tool": "llm.chat"}, {"tool_calls": 1, "tool_failures": 1, "llm_calls": 1, "llm_failures": 1}),
        ("graph.step", {}, {"steps": 1}),
        ("graph.parse_error", {}, {"parse_errors": 1}),
        ("graph.finish_blocked", {}, {"finish_gate_blocks": 1}),
        ("delegation.started", {}, {"delegations": 1}),
        ("delegation.progress", {}, {"delegation_progress": 1}),
        ("delegation.finished", {"outcome": "failed"}, {"delegation_failures": 1}),
        ("delegation.finished", {"outcome": "success"}, {}),
        ("unknown.topic", {}, {}),
    ]

    for topic, payload, expected_delta in cases:
        before = dict(logger.metrics)
        bus.publish(topic, payload)
        actual_delta = {key: logger.metrics[key] - before[key] for key in logger.metrics}
        assert {key: value for key, value in actual_delta.items() if value} == expected_delta


@pytest.mark.audit
@pytest.mark.concurrency
def test_event_logger_finish_is_idempotent_under_concurrency():
    logger = EventLogger("finish-once")

    with ThreadPoolExecutor(max_workers=16) as pool:
        summaries = list(pool.map(lambda _: logger.finish("completed"), range(100)))

    events = [json.loads(line) for line in logger.events_path.read_text(encoding="utf-8").splitlines()]
    index = (logger.run_dir.parent / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert all(item["status"] == "completed" for item in summaries)
    assert [item["status"] for item in events].count("run_finished") == 1
    assert len(index) == 1


@pytest.mark.audit
@pytest.mark.concurrency
def test_count_and_emit_are_lossless_under_heavy_concurrency():
    logger = EventLogger("parallel")

    def worker(worker_id):
        for offset in range(100):
            logger.count("tool_calls")
            logger.emit("AuditEvent", worker=worker_id, offset=offset)

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(worker, range(20)))

    events = [json.loads(line) for line in logger.events_path.read_text(encoding="utf-8").splitlines()]
    assert logger.metrics["tool_calls"] == 2000
    assert len(events) == 2001
    assert [item["sequence"] for item in events] == list(range(1, 2002))
    assert len({(item["worker"], item["offset"]) for item in events[1:]}) == 2000


@pytest.mark.audit
def test_inspector_skips_blank_truncated_and_malformed_jsonl_records():
    logger = EventLogger("corrupt")
    logger.emit("GoodEvent", value=1)
    with logger.events_path.open("a", encoding="utf-8") as handle:
        handle.write("\n{truncated\n[]\n")

    events = inspect_cli.read_events("corrupt")

    assert [item["kind"] for item in events] == ["StateEvent", "GoodEvent"]


@pytest.mark.audit
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["list"], 0),
        (["ls"], 0),
        (["summary"], 0),
        (["events"], 0),
        (["events", "latest", "--kind"], 2),
        (["unknown"], 2),
    ],
)
def test_inspection_cli_never_crashes_for_supported_or_malformed_argv(argv, expected, capsys):
    logger = EventLogger("one")
    logger.finish()
    assert inspect_cli.main(argv) == expected
    assert capsys.readouterr().out


@pytest.mark.audit
def test_inspector_kind_and_topic_filters_are_conjunctive():
    logger = EventLogger("filters")
    logger.emit("KernelEvent", topic="one")
    logger.emit("KernelEvent", topic="two")
    logger.emit("OtherEvent", topic="one")

    assert [item["topic"] for item in inspect_cli.read_events("filters", kind="KernelEvent")] == ["one", "two"]
    assert [item["kind"] for item in inspect_cli.read_events("filters", topic="one")] == ["KernelEvent", "OtherEvent"]
    assert inspect_cli.read_events("filters", kind="KernelEvent", topic="two")[0]["topic"] == "two"
