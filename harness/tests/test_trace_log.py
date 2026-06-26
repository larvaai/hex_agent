"""test_trace_log.py — the audit trace store (append-only, daily files,
NO rotation — trace is the audit ledger, only telemetry counters
rotate). Schema learned from CK hook-logger (written new, not copied).
"""
import importlib
import json
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS))


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HARNESS_HOOK_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("HARNESS_USER", "tester")
    monkeypatch.delenv("HARNESS_AGENT", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITLAB_CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    for m in ("trace_log", "hook_runtime"):
        sys.modules.pop(m, None)
    import trace_log
    importlib.reload(trace_log)
    return trace_log


def _trace_files(tmp_path):
    d = tmp_path / "state" / "trace"
    return sorted(d.glob("trace-*.jsonl")) if d.exists() else []


def _records(tmp_path):
    out = []
    for f in _trace_files(tmp_path):
        out.extend(json.loads(l) for l in f.read_text().splitlines() if l.strip())
    return out


class TestAppendEvent:
    def test_basic_record_schema(self, tmp_path, monkeypatch):
        tl = _fresh(monkeypatch, tmp_path)
        tl.append_event(hook="gate_stage", event="gate_block",
                        tool="Bash", target="git push",
                        status="blocked", exit_code=2,
                        note="missing verification")
        recs = _records(tmp_path)
        assert len(recs) == 1
        r = recs[0]
        # schema: ts/actor/session/hook/event + optional tool/target/status/...
        assert r["event"] == "gate_block"
        assert r["hook"] == "gate_stage"
        assert r["actor"] == "user:tester"
        assert r["ts"]  # ISO ts present
        assert r["tool"] == "Bash"
        assert r["status"] == "blocked"
        assert r["exit"] == 2
        assert r["note"] == "missing verification"

    def test_daily_file_naming(self, tmp_path, monkeypatch):
        tl = _fresh(monkeypatch, tmp_path)
        tl.append_event(hook="h", event="session_start")
        files = _trace_files(tmp_path)
        assert len(files) == 1
        import re
        assert re.fullmatch(r"trace-\d{8}\.jsonl", files[0].name)

    def test_append_only_two_events_two_lines(self, tmp_path, monkeypatch):
        tl = _fresh(monkeypatch, tmp_path)
        tl.append_event(hook="h", event="e1")
        tl.append_event(hook="h", event="e2")
        assert [r["event"] for r in _records(tmp_path)] == ["e1", "e2"]

    def test_no_rotation_ever(self, tmp_path, monkeypatch):
        # audit trace must NOT truncate-rotate, however big.
        tl = _fresh(monkeypatch, tmp_path)
        tl.append_event(hook="h", event="seed")
        f = _trace_files(tmp_path)[0]
        # Inflate the file way past any plausible rotation cap.
        with open(f, "a", encoding="utf-8") as fh:
            fh.write("x" * (9 * 1024 * 1024) + "\n")
        size_before = f.stat().st_size
        tl.append_event(hook="h", event="after-big")
        assert f.stat().st_size > size_before          # still appending
        assert not (f.parent / (f.name + ".1")).exists()  # no rotation artifact

    def test_payload_hash_when_tool_input_given(self, tmp_path, monkeypatch):
        tl = _fresh(monkeypatch, tmp_path)
        tl.append_event(hook="g", event="gate_pass",
                        tool_input={"command": "git push"})
        r = _records(tmp_path)[0]
        assert len(r["payload_hash"]) == 12
        # deterministic: same input → same hash
        tl.append_event(hook="g", event="gate_pass",
                        tool_input={"command": "git push"})
        assert _records(tmp_path)[1]["payload_hash"] == r["payload_hash"]

    def test_unserializable_payload_still_records_audit_line(self, tmp_path, monkeypatch):
        # A non-JSON-serializable tool_input must drop ONLY the payload_hash field,
        # never the whole audit record — losing the audit line on a hashing failure
        # would silently erase the very event the ledger exists to witness.
        tl = _fresh(monkeypatch, tmp_path)

        class _Unhashable:  # json.dumps cannot serialize a bare object
            pass

        tl.append_event(hook="gate_stage", event="gate_block", tool="Bash",
                        status="blocked", tool_input={"obj": _Unhashable()})
        recs = _records(tmp_path)
        assert len(recs) == 1                    # audit line survives
        assert recs[0]["event"] == "gate_block"
        assert recs[0]["status"] == "blocked"
        assert "payload_hash" not in recs[0]     # only the hash field is dropped

    def test_fail_open_when_dir_unwritable(self, tmp_path, monkeypatch):
        tl = _fresh(monkeypatch, tmp_path)
        blocker = tmp_path / "blocked"
        blocker.write_text("file-not-dir")
        monkeypatch.setenv("HARNESS_STATE_DIR", str(blocker / "state"))
        tl.append_event(hook="h", event="e")  # must not raise

    def test_actor_override_param(self, tmp_path, monkeypatch):
        tl = _fresh(monkeypatch, tmp_path)
        tl.append_event(hook="h", event="e", actor="ci")
        assert _records(tmp_path)[0]["actor"] == "ci"

    def test_session_recorded(self, tmp_path, monkeypatch):
        tl = _fresh(monkeypatch, tmp_path)
        tl.append_event(hook="h", event="e", session="s42")
        assert _records(tmp_path)[0]["session"] == "s42"


def test_ts_and_filename_derive_from_one_instant(tmp_path, monkeypatch):
    """ts and the daily filename must come from a SINGLE now() — two separate
    now() calls can straddle UTC midnight, filing a record under a date that
    disagrees with its own ts (audit-ledger integrity)."""
    from datetime import datetime, timezone
    tl = _fresh(monkeypatch, tmp_path)
    t1 = datetime(2026, 6, 20, 23, 59, 59, 900000, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 21, 0, 0, 0, 0, tzinfo=timezone.utc)  # next day

    class _Seq:
        seq = [t1, t2]
        i = [0]

        @classmethod
        def now(cls, tz=None):
            v = cls.seq[min(cls.i[0], len(cls.seq) - 1)]
            cls.i[0] += 1
            return v

    monkeypatch.setattr(tl, "datetime", _Seq)
    tl.append_event(hook="h", event="e")

    files = _trace_files(tmp_path)
    recs = _records(tmp_path)
    assert len(files) == 1 and len(recs) == 1
    ts_date = recs[0]["ts"][:10].replace("-", "")
    fname_date = files[0].name[len("trace-"):len("trace-") + 8]
    assert ts_date == fname_date, \
        "ts %s vs filename %s — two now() calls split at midnight" % (ts_date, fname_date)
