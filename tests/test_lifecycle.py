"""Seam 3 — complete_task / fail_task close the task lifecycle symmetrically. Epic E05."""
from core.bootstrap import build_kernel

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}


def test_complete_task_clears_and_emits():
    k = build_kernel(ECHO)
    seen = []
    k.events.subscribe(lambda t, p: seen.append((t, p)))
    task = k.accept_task("x")
    out = k.complete_task("answer")
    assert out["status"] == "completed"
    assert out["task_id"] == task.task_id
    assert out["result"] == "answer"
    assert k.state.get("current_task") is None
    assert k.state.get("last_result")["result"] == "answer"
    assert any(t == "task.completed" and p["task_id"] == task.task_id for t, p in seen)


def test_fail_task_emits_failed():
    k = build_kernel(ECHO)
    seen = []
    k.events.subscribe(lambda t, p: seen.append((t, p)))
    k.accept_task("x")
    out = k.fail_task("nope", code=1)
    assert out["status"] == "failed"
    assert out["result"]["reason"] == "nope" and out["result"]["code"] == 1
    assert any(t == "task.failed" for t, _ in seen)
