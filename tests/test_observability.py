from observability import EventLogger
from observability import inspect as insp


def test_run_writes_events_and_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    logger = EventLogger(run_id="testrun")
    logger.emit("ActionEvent", action="tool", tool="echo")
    logger.count("tool_calls")
    summary = logger.finish("completed")

    assert (tmp_path / "testrun" / "events.jsonl").exists()
    assert (tmp_path / "testrun" / "summary.json").exists()
    assert summary["metrics"]["tool_calls"] == 1

    assert "testrun" in insp.list_runs()
    assert insp.read_summary("testrun")["status"] == "completed"
    events = insp.read_events("testrun", kind="ActionEvent")
    assert len(events) == 1 and events[0]["tool"] == "echo"


def test_disabled_logging_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    logger = EventLogger(run_id="off", enabled=False)
    logger.emit("StateEvent", status="x")
    logger.finish("completed")
    assert not (tmp_path / "off").exists()
