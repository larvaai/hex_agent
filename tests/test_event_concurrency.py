"""Shared event infrastructure remains consistent under concurrent sessions."""
import json
from concurrent.futures import ThreadPoolExecutor

from core.events import EventBus
from observability import EventLogger, attach_to_bus


def test_subscribers_receive_detached_payloads():
    bus = EventBus()
    observed = []

    def mutate(topic, payload):
        payload["nested"]["value"] = "changed"

    bus.subscribe(mutate)
    bus.subscribe(lambda topic, payload: observed.append(payload))
    original = {"nested": {"value": "original"}}
    bus.publish("x", original)
    assert original["nested"]["value"] == "original"
    assert observed[0]["nested"]["value"] == "original"


def test_logger_sequence_and_jsonl_are_safe_under_concurrency(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    bus = EventBus()
    logger = EventLogger(run_id="parallel")
    attach_to_bus(logger, bus)

    def publish(worker):
        for offset in range(25):
            bus.publish("session.progress", {"worker": worker, "offset": offset})

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(publish, range(10)))

    lines = logger.events_path.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    sequences = [event["sequence"] for event in events]
    assert len(events) == 251  # initial run_started + 250 concurrent events
    assert sequences == list(range(1, 252))
