import json

import pytest

import ui.server as server


def test_workspace_tree_and_file_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "workspace_dir", lambda: tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "hello.py").write_text("print('hello')\n", encoding="utf-8")

    snapshot = server.tree_snapshot("workspace")
    assert snapshot["entries"] == 3
    assert snapshot["tree"]["children"][0]["name"] == "src"

    preview = server.read_file_snapshot("workspace", "src/hello.py")
    assert preview["content"] == "print('hello')\n"
    assert preview["language"] == "py"


def test_file_preview_blocks_escape_and_sensitive_file(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "workspace_dir", lambda: tmp_path)
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")

    with pytest.raises(ValueError):
        server.read_file_snapshot("workspace", "../outside.txt")
    with pytest.raises(PermissionError):
        server.read_file_snapshot("workspace", ".env")


def test_normalize_messages_includes_summary_outcome():
    checkpoint = {"messages": [{"role": "user", "content": "hello"}]}
    summary = {"outcome": {"result": "done"}}

    messages = server._normalize_messages(checkpoint, summary)

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "done"
    assert messages[-1]["final"] is True


def test_final_error_is_failed_and_not_duplicated():
    final = json.dumps({"action": "final", "finish_reason": "error", "message": "model unavailable"})
    checkpoint = {"messages": [{"role": "assistant", "content": final}]}
    summary = {"outcome": {"result": "model unavailable"}}

    assert server._effective_status(checkpoint, "completed") == "failed"
    assert len(server._normalize_messages(checkpoint, summary)) == 1


def test_run_job_tracks_system_prompt():
    job = server.RunJob(run_id="r1", prompt="hello", system_prompt="be concise")

    assert job.system_prompt == "be concise"


def test_event_reader_ignores_partial_json(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"kind": "StateEvent"}) + "\n{partial", encoding="utf-8")

    assert server._read_events(path) == [{"kind": "StateEvent"}]
