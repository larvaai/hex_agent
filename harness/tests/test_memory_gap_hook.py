"""Tests for the opt-in tier-1 memory-gap hook (`hooks/memory_gap_hook.py`).

The hook is a thin NUDGE-class wrapper around the `memory_gap` detector. Unlike
the source (which blocks turn-end), this one NEVER blocks: it surfaces the gap
as an advisory and records an observation in the audit trace, then allows. Two
properties matter most here:

  - tier-0b (visible no-op): if the detector chain is broken, the hook must NOT
    silently allow — it emits a `memory_gap_degraded` audit event first. A hook
    that looks alive while never firing is the failure mode this closes.
  - nudge posture: default OFF (config-gated), and even when ON it only warns +
    records, never blocks; a disabled hook is fully inert.

No-op guard: a `PostToolUse` write sets an EPHEMERAL session-keyed touched-flag
in $TMPDIR; the `Stop` hook runs the detector ONLY when that flag is set.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import hook_runtime  # noqa: E402,F401 — ensure the module is importable on the path

HOOK_PATH = _HOOKS / "memory_gap_hook.py"


def _hook_runtime():
    """The LIVE hook_runtime module. test_hook_runtime.py reloads it (swapping the
    sys.modules object), so the config-cache reset must target whatever object the
    hook itself imports now — never a stale top-level binding."""
    import hook_runtime as hr  # noqa: E402
    return sys.modules.get("hook_runtime", hr)

from conftest import make_proj  # noqa: E402

_proj = make_proj


def _load_hook():
    spec = importlib.util.spec_from_file_location("memory_gap_hook", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_config(path: Path, enabled: bool = True):
    path.write_text(
        "hooks:\n"
        "  memory_gap_hook:\n"
        "    enabled: %s\n" % ("true" if enabled else "false"),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    """Isolate the touched-flag dir ($TMPDIR), the audit-trace dir
    (HARNESS_STATE_DIR), and the crash-log dir; enable the hook by default
    (nudge is OFF otherwise). Per-test config override is via `_reconfig`."""
    state = tmp_path / "state"
    tdir = tmp_path / "tmp"
    logs = tmp_path / "logs"
    for d in (state, tdir, logs):
        d.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "harness-hooks.yaml"
    _write_config(cfg, enabled=True)
    monkeypatch.setenv("HARNESS_STATE_DIR", str(state))
    monkeypatch.setenv("TMPDIR", str(tdir))
    monkeypatch.setenv("HARNESS_HOOK_LOG_DIR", str(logs))
    monkeypatch.setenv("HARNESS_HOOK_CONFIG", str(cfg))
    monkeypatch.setenv("HARNESS_USER", "tester")
    _hook_runtime()._reset_config_cache()
    yield {"state": state, "tmp": tdir, "cfg": cfg}
    _hook_runtime()._reset_config_cache()


def _reconfig(cfg: Path, enabled: bool):
    _write_config(cfg, enabled=enabled)
    _hook_runtime()._reset_config_cache()


def _stop_payload(proj: Path, session_id="sess-1"):
    return {"session_id": session_id, "cwd": str(proj), "hook_event_name": "Stop"}


def _post_payload(proj: Path, file_path: str, session_id="sess-1"):
    return {
        "session_id": session_id,
        "cwd": str(proj),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path},
    }


def _trace_events(state: Path):
    tdir = state / "trace"
    out = []
    if tdir.is_dir():
        for f in sorted(tdir.glob("trace-*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
    return out


def _events_of(state: Path, name: str):
    return [e for e in _trace_events(state) if e.get("event") == name]


# ---------------------------------------------------------------------------
# no-op guard
# ---------------------------------------------------------------------------

def test_noop_when_flag_unset(_env, tmp_path):
    """docs/product exists but nothing was written this session → no flag → the
    Stop hook allows without running the detector (no observation event)."""
    mod = _load_hook()
    proj = _proj(tmp_path)
    rc = mod.handle_stop(_stop_payload(proj), str(proj))
    assert rc == 0
    assert _events_of(_env["state"], "memory_gap_observation") == []


def test_post_tool_use_sets_flag(_env, tmp_path):
    mod = _load_hook()
    proj = _proj(tmp_path)
    rc = mod.handle_post_tool_use(
        _post_payload(proj, str(proj / "src" / "app.py"), session_id="sx"), str(proj))
    assert rc == 0
    assert mod.touched_flag_set("sx")


# ---------------------------------------------------------------------------
# nudge: surface advisory + record observation, never block
# ---------------------------------------------------------------------------

def test_fence_breach_surfaced_and_recorded(_env, tmp_path, capsys):
    mod = _load_hook()
    proj = _proj(tmp_path)
    (proj / "src").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "app.py").write_text("print('x')\n", encoding="utf-8")
    mod.set_touched_flag("sess-1")

    rc = mod.handle_stop(_stop_payload(proj), str(proj))
    assert rc == 0  # nudge NEVER blocks
    err = capsys.readouterr().err
    assert "src/app.py" in err
    obs = _events_of(_env["state"], "memory_gap_observation")
    assert obs, "an observation must be recorded in the audit trace"


def test_clean_spec_records_nothing(_env, tmp_path, capsys):
    mod = _load_hook()
    proj = _proj(tmp_path)  # committed, clean working tree
    mod.set_touched_flag("sess-1")
    rc = mod.handle_stop(_stop_payload(proj), str(proj))
    assert rc == 0
    assert capsys.readouterr().err.strip() == ""
    assert _events_of(_env["state"], "memory_gap_observation") == []


# ---------------------------------------------------------------------------
# tier-0b: a broken detector chain degrades VISIBLY, not silently
# ---------------------------------------------------------------------------

def test_degraded_trace_when_detector_missing(_env, tmp_path, monkeypatch):
    """If the detector cannot be imported, the hook emits a `memory_gap_degraded`
    audit event and allows — it must never silently look alive while never firing."""
    mod = _load_hook()
    proj = _proj(tmp_path)
    mod.set_touched_flag("sess-1")

    def _boom():
        raise ImportError("memory_gap hidden for the test")
    monkeypatch.setattr(mod, "_import_memory_gap", _boom)

    rc = mod.handle_stop(_stop_payload(proj), str(proj))
    assert rc == 0
    degraded = _events_of(_env["state"], "memory_gap_degraded")
    assert degraded, "a missing detector must surface a memory_gap_degraded event"
    # And no false observation was recorded (the detector never ran).
    assert _events_of(_env["state"], "memory_gap_observation") == []


# ---------------------------------------------------------------------------
# nudge default OFF: a disabled hook is fully inert
# ---------------------------------------------------------------------------

def test_disabled_hook_is_inert(_env, tmp_path, capsys):
    mod = _load_hook()
    proj = _proj(tmp_path)
    (proj / "src").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "app.py").write_text("print('x')\n", encoding="utf-8")
    mod.set_touched_flag("sess-1")
    _reconfig(_env["cfg"], enabled=False)

    rc = mod.handle_stop(_stop_payload(proj), str(proj))
    assert rc == 0
    assert capsys.readouterr().err.strip() == ""
    assert _events_of(_env["state"], "memory_gap_observation") == []


def test_hook_writes_nothing_into_the_project(_env, tmp_path):
    """The hook's only side effects are the ephemeral flag ($TMPDIR) and the audit
    trace (HARNESS_STATE_DIR) — never a file inside the scanned project."""
    mod = _load_hook()
    proj = _proj(tmp_path)
    (proj / "src").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "app.py").write_text("print('x')\n", encoding="utf-8")
    mod.set_touched_flag("sess-1")

    before = {p.relative_to(proj) for p in proj.rglob("*")}
    mod.handle_stop(_stop_payload(proj), str(proj))
    after = {p.relative_to(proj) for p in proj.rglob("*")}
    assert before == after, "the hook must not write into the project tree"


# ---------------------------------------------------------------------------
# CLI shape — invokable standalone in both modes (how the host calls it)
# ---------------------------------------------------------------------------

def _run(mode, payload, env):
    args = [sys.executable, str(HOOK_PATH)]
    if mode == "post":
        args.append("--post-tool-use")
    return subprocess.run(args, input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


def test_cli_post_then_stop_records_observation(_env, tmp_path):
    import os
    proj = _proj(tmp_path)
    (proj / "src").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "app.py").write_text("print('x')\n", encoding="utf-8")

    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(proj)

    rc_post = _run("post", _post_payload(proj, str(proj / "src" / "app.py")), env)
    assert rc_post.returncode == 0, rc_post.stderr

    rc_stop = _run("stop", _stop_payload(proj), env)
    assert rc_stop.returncode == 0, rc_stop.stderr
    assert _events_of(_env["state"], "memory_gap_observation"), rc_stop.stderr


def test_cli_stop_noop_exit_zero(_env, tmp_path):
    import os
    proj = _proj(tmp_path)
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    rc = _run("stop", _stop_payload(proj), env)
    assert rc.returncode == 0, rc.stderr
