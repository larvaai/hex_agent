"""inspect.py enrichment — status/tool/text filters + summarize helpers. Epic E04."""
from __future__ import annotations

import json

from observability import inspect as insp


def _seed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    run_dir = tmp_path / "runs" / "20260626_000000_test"
    run_dir.mkdir(parents=True)
    events = [
        {"sequence": 1, "kind": "StateEvent", "status": "run_started"},
        {"sequence": 2, "kind": "KernelEvent", "topic": "tool.completed", "tool": "fs_read", "ok": True},
        {"sequence": 3, "kind": "KernelEvent", "topic": "tool.failed", "tool": "fs_write", "ok": False, "error": "boom"},
        {"sequence": 4, "kind": "LLMCallEvent", "topic": "tool.completed", "tool": "llm.chat", "ok": True},
        {"sequence": 5, "kind": "StateEvent", "status": "run_finished"},
    ]
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps({"run_id": "20260626_000000_test", "status": "completed", "metrics": {"steps": 3, "tool_calls": 3}}),
        encoding="utf-8",
    )
    return run_dir


def test_filter_by_status(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    events = insp.read_events("latest", status="run_finished")
    assert [e["sequence"] for e in events] == [5]


def test_filter_by_tool(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    events = insp.read_events("latest", tool="fs_write")
    assert len(events) == 1 and events[0]["ok"] is False


def test_filter_by_text_is_case_insensitive(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    events = insp.read_events("latest", text="BOOM")
    assert len(events) == 1 and events[0]["sequence"] == 3


def test_filters_and_together(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    events = insp.read_events("latest", kind="KernelEvent", topic="tool.completed")
    assert [e["tool"] for e in events] == ["fs_read"]


def test_summarize_event_is_compact(tmp_path, monkeypatch):
    line = insp.summarize_event({"sequence": 3, "kind": "KernelEvent", "topic": "tool.failed", "tool": "fs_write", "ok": False, "error": "boom"})
    assert "#3" in line and "fs_write" in line and "ERR" in line and "boom" in line


def test_summarize_metrics_columns(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    out = insp.summarize_metrics(insp.read_summary("latest"))
    assert "steps" in out and "tool_calls" in out and "completed" in out


def test_main_events_summarize_and_legacy_kind(tmp_path, monkeypatch, capsys):
    _seed_run(tmp_path, monkeypatch)
    # legacy --kind still works
    assert insp.main(["events", "latest", "--kind", "StateEvent"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 2  # two StateEvents
    # new --summarize + --tool
    assert insp.main(["events", "latest", "--tool", "fs_read", "--summarize"]) == 0
    out = capsys.readouterr().out
    assert "fs_read" in out and "#2" in out
