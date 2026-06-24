"""Checkpoint save/load round-trip, incl. TaskEnvelope in state. Epic E07."""
from core.schemas import TaskEnvelope
from orchestrator.checkpoint import Checkpoint, checkpoint_path, load_checkpoint, save_checkpoint


def test_checkpoint_roundtrip_with_task(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    task = TaskEnvelope(user_request="hi")
    cp = Checkpoint(
        run_id="rr", task="hi",
        messages=[{"role": "user", "content": "hi"}],
        budget={"max_steps": 30, "max_parse_errors": 3, "max_same_tool_calls": 3,
                "steps": 2, "parse_errors": 1, "_tool_calls": {"echo:{}": 1}},
        state={"current_task": task, "code_changed": True},
        step=2, status="running",
    )
    save_checkpoint(cp)
    assert checkpoint_path("rr").exists()
    loaded = load_checkpoint("rr")
    assert loaded.status == "running" and loaded.step == 2
    assert loaded.budget["steps"] == 2 and loaded.budget["parse_errors"] == 1
    assert loaded.state["code_changed"] is True
    assert isinstance(loaded.state["current_task"], TaskEnvelope)
    assert loaded.state["current_task"].task_id == task.task_id


def test_load_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    assert load_checkpoint("nope") is None


def test_disabled_checkpoint_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    save_checkpoint(Checkpoint(run_id="off", task="x"), enabled=False)
    assert load_checkpoint("off") is None
