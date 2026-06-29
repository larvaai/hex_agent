"""test_session_init.py — SessionStart hook: resolve actor once, cache it in
state/sessions/<sid>.json, emit a session_start trace event. Telemetry-class:
must always continue, even on failure.
"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS))


def _env(tmp_path, **extra):
    env = dict(os.environ)
    env["HARNESS_STATE_DIR"] = str(tmp_path / "state")
    env["HARNESS_HOOK_LOG_DIR"] = str(tmp_path / "logs")
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("CI", None)
    env.pop("GITLAB_CI", None)
    env.pop("GITHUB_ACTIONS", None)
    env.pop("HARNESS_AGENT", None)
    env.update(extra)
    return env


def _run(tmp_path, stdin_obj, **env_extra):
    return subprocess.run(
        [sys.executable, str(_HOOKS / "session_init.py")],
        input=json.dumps(stdin_obj), capture_output=True, text=True,
        env=_env(tmp_path, **env_extra),
    )


def _session_files(tmp_path):
    d = tmp_path / "state" / "sessions"
    return sorted(d.glob("*.json")) if d.exists() else []


def _trace_events(tmp_path):
    d = tmp_path / "state" / "trace"
    out = []
    if d.exists():
        for f in d.glob("trace-*.jsonl"):
            out.extend(json.loads(l) for l in f.read_text().splitlines() if l.strip())
    return out


class TestSessionInit:
    def test_writes_session_file_with_actor(self, tmp_path):
        proc = _run(tmp_path, {"session_id": "s-abc"}, HARNESS_USER="alice")
        assert proc.returncode == 0
        assert '"continue"' in proc.stdout
        files = _session_files(tmp_path)
        assert len(files) == 1 and files[0].name == "s-abc.json"
        data = json.loads(files[0].read_text())
        assert data["actor"] == "user:alice"
        assert data["ts"]

    def test_emits_session_start_trace(self, tmp_path):
        _run(tmp_path, {"session_id": "s-abc"}, HARNESS_USER="alice")
        events = _trace_events(tmp_path)
        assert any(e["event"] == "session_start" and e["actor"] == "user:alice"
                   for e in events)

    def test_ci_actor(self, tmp_path):
        _run(tmp_path, {"session_id": "s-ci"}, CI="true", HARNESS_USER="x")
        data = json.loads(_session_files(tmp_path)[0].read_text())
        assert data["actor"] == "ci"

    def test_no_session_id_still_continues(self, tmp_path):
        proc = _run(tmp_path, {}, HARNESS_USER="alice")
        assert proc.returncode == 0
        assert '"continue"' in proc.stdout

    def test_env_override_seen_traces_names_only(self, tmp_path):
        # Posture visibility: HARNESS_* overrides set at session start are
        # listed BY NAME in an audit event (trace, never telemetry — the
        # 8MB rotation would erase the evidence). Values stay out: a value
        # can carry paths/secrets, the audit question is only WHICH knobs.
        _run(tmp_path, {"session_id": "s-ov"}, HARNESS_USER="alice",
             HARNESS_STAGE_POLICY="/tmp/elsewhere.yaml",
             HARNESS_OWNERSHIP_FILE="/tmp/own.yaml")
        events = [e for e in _trace_events(tmp_path)
                  if e["event"] == "env_override_seen"]
        assert len(events) == 1
        note = events[0]["note"]
        assert "HARNESS_STAGE_POLICY" in note
        assert "HARNESS_OWNERSHIP_FILE" in note
        assert "/tmp/elsewhere.yaml" not in note  # names only, never values

    def test_no_override_no_event(self, tmp_path):
        # Plumbing vars the test itself needs (state dir, log dir, user)
        # are expected baseline, not posture overrides.
        _run(tmp_path, {"session_id": "s-clean"}, HARNESS_USER="alice")
        events = [e for e in _trace_events(tmp_path)
                  if e["event"] == "env_override_seen"]
        assert events == []

    def test_other_hook_resolves_same_actor_via_cache(self, tmp_path):
        # The point of the cache: a later hook in the same session resolves
        # the SAME actor through the session file, not a fresh env reading.
        _run(tmp_path, {"session_id": "s-x"}, HARNESS_USER="alice")
        probe = (
            "import sys; "
            f"sys.path.insert(0, {str(_HOOKS)!r}); "
            "import hook_runtime; "
            "print(hook_runtime.resolve_actor(session_id='s-x'))"
        )
        # Env now says bob, but the cached session actor (alice) wins.
        proc = subprocess.run([sys.executable, "-c", probe],
                              capture_output=True, text=True,
                              env=_env(tmp_path, HARNESS_USER="bob"))
        assert proc.stdout.strip() == "user:alice"
