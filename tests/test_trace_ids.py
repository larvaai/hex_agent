"""Part B — run_id ⊇ task_id ⊇ request_id is threadable from kernel events. Epic E01/E04."""
from core.bootstrap import build_kernel

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}


def test_task_accepted_event_has_task_id():
    k = build_kernel(ECHO)
    seen = []
    k.events.subscribe(lambda t, p: seen.append((t, p)))
    task = k.accept_task("x")
    accepted = [p for t, p in seen if t == "task.accepted"]
    assert accepted and accepted[0]["task_id"] == task.task_id


def test_tool_events_carry_task_id():
    k = build_kernel(ECHO)
    seen = []
    k.events.subscribe(lambda t, p: seen.append((t, p)))
    task = k.accept_task("trace test")
    k.execute_tool("echo", {"a": 1})
    tool_events = [(t, p) for (t, p) in seen if t.startswith("tool.")]
    assert tool_events
    for _, p in tool_events:
        assert p.get("task_id") == task.task_id
    assert all("request_id" in p for _, p in tool_events)


def test_envelope_metadata_has_task_and_request_id():
    k = build_kernel(ECHO)
    task = k.accept_task("trace test")
    env = k.execute_tool("echo", {"a": 1})
    assert env["metadata"]["task_id"] == task.task_id
    assert "request_id" in env["metadata"]


def test_task_id_none_without_accept_is_safe():
    k = build_kernel(ECHO)
    env = k.execute_tool("echo", {"a": 1})
    assert env["metadata"]["task_id"] is None
