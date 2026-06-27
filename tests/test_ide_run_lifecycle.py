"""L1 backend-integration — AgentRunner lifecycle without the model (runner.py / session.py).

The real run path goes through ``orchestrator.run`` → the LLM; here ``_run`` is stubbed so the
start/cancel claim, the run-start baseline snapshot, and the diff endpoint's locked baseline read are
exercised deterministically with no model and no network.
"""
from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection

import pytest

import ui.ide.files as files
import ui.ide.server as server_mod
from ui.ide.runner import AgentRunner
from ui.ide.session import IdeSession


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    return ws


def _wait_status(session, target, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if session.snapshot_status() == target:
            return True
        time.sleep(0.02)
    return False


# ── cancel during a live claim → 'cancelled', not 'finished' (runner.py:159,196) ──
def test_cancel_sets_status_cancelled_not_finished(workspace, monkeypatch):
    def fake_run(self, run_id, prompt, system_prompt):  # noqa: ANN001
        self._cancel.wait(5)  # block as a real run would until Stop fires
        self._finish_cancelled()

    monkeypatch.setattr(AgentRunner, "_run", fake_run)
    session = IdeSession("t1_demo")
    runner = AgentRunner(session)

    assert runner.start("do work") is not None  # claimed the session
    assert session.snapshot_status() == "running"
    assert runner.cancel() is True  # a live run was there to cancel

    assert _wait_status(session, "cancelled")
    by_type = {e["event_type"]: e["ui_payload"] for e in session.events()}
    assert by_type["chat.error"].get("cancelled") is True
    assert "loop.finished" not in by_type  # a cancel never reports a clean finish


# ── baseline is snapshotted BEFORE the run touches disk (runner.py:99-101) ────────
def test_baseline_captured_before_run(workspace, monkeypatch):
    (workspace / "keep.py").write_text("x = 1\n", encoding="utf-8")

    def fake_run(self, *args):  # noqa: ANN001
        self._cancel.wait(5)

    monkeypatch.setattr(AgentRunner, "_run", fake_run)
    session = IdeSession("t1_demo")
    runner = AgentRunner(session)
    assert runner.start("edit something") is not None

    # baseline froze the pre-run tree: keep.py is in it, a file written *after* start is not
    assert "keep.py" in session.baseline
    files.write_file("workspace", "new.py", "y = 2\n")  # the "agent" writes mid-run
    assert "new.py" not in session.baseline

    baseline, scope = session.diff_baseline()
    diffs = {d["path"]: d for d in files.compute_diffs(baseline, scope)}
    assert diffs["new.py"]["status"] == "added"  # the post-baseline write shows as a diff
    runner.cancel()  # release the stub thread


# ── concurrent /api/files/diff never races the baseline (session.py:135-137) ──────
@pytest.mark.concurrency
@pytest.mark.integration
def test_diff_baseline_atomic_under_concurrent_diff(workspace):
    srv = server_mod.IdeControlServer(("127.0.0.1", 0), token="tok", session_id="t1_demo")
    port = srv.socket.getsockname()[1]
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        files.write_file("workspace", "a.py", "print(1)\n")  # one change vs the session's baseline

        results: list[tuple[int, list[str]]] = []
        lock = threading.Lock()

        def hit():
            status, body = _get(port, "/api/files/diff?session=t1_demo", token="tok")
            with lock:
                results.append((status, sorted(d["path"] for d in body.get("files", []))))

        threads = [threading.Thread(target=hit) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(status == 200 for status, _ in results)
        paths = [p for _, p in results]
        assert all(p == ["a.py"] for p in paths)  # every concurrent reader saw the same baseline
    finally:
        srv.shutdown()
        srv.server_close()


def _get(port, path, token=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"X-Auth-Token": token} if token else {}
    conn.request("GET", path, None, headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, (json.loads(raw) if raw else {})
