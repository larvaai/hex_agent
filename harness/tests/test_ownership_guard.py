"""test_ownership_guard.py — PreToolUse(Bash) per-actor commit gate.

ownership_guard runs on a `git commit` Bash command: it loads the work
manifest (HARNESS_WORK_OWNERSHIP_FILE), reads the staged files, and refuses a
commit whose staged files fall in ANOTHER declared owner's lane (reconcile_actor
poaching check). Only declared owners are policed; a missing manifest skips.

The contract is the real process: exit 2 = block, exit 0 = pass/advisory. A
temp git repo gives a real `git diff --cached`.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
_GUARD = _HOOKS / "ownership_guard.py"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@local")
    _git(repo, "config", "user.name", "t")
    return repo


def _stage(repo, rel, body="x\n"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    _git(repo, "add", rel)


def _manifest(tmp_path, units):
    p = tmp_path / "work-ownership.yaml"
    p.write_text(yaml.safe_dump({"units": units}), encoding="utf-8")
    return p


def _policy(tmp_path, *, preset="balanced", ownership_guard=None):
    lines = ['schema_version: "1.0"', 'preset: "%s"' % preset]
    if ownership_guard is not None:
        lines += ["overrides:", '  ownership_guard: "%s"' % ownership_guard]
    else:
        lines.append("overrides: {}")
    p = tmp_path / "guard-policy.yaml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


_UNITS = [
    {"id": "auth", "owner": "user:alice", "globs": ["harness/scripts/auth_*.py"]},
    {"id": "ui", "owner": "user:bob", "globs": ["harness/ui/*.py"]},
]


def _run(repo, tmp_path, *, actor, manifest=None, command="git commit -m x",
         policy=None):
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("HARNESS_HOOK_CONFIG", None)
    for ci in ("CI", "GITHUB_ACTIONS", "GITLAB_CI"):
        env.pop(ci, None)
    env["HARNESS_USER"] = actor
    env["HARNESS_STATE_DIR"] = str(tmp_path / "state")
    env["HARNESS_HOOK_LOG_DIR"] = str(tmp_path / "logs")
    env["HARNESS_GUARD_POLICY"] = str(policy or _policy(tmp_path))
    if manifest is not None:
        env["HARNESS_WORK_OWNERSHIP_FILE"] = str(manifest)
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": command},
                          "session_id": "s1"})
    return subprocess.run([sys.executable, str(_GUARD)], input=payload,
                          capture_output=True, text=True, env=env, cwd=repo)


def test_poaching_commit_blocks(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, "harness/ui/panel.py")          # bob's lane
    m = _manifest(tmp_path, _UNITS)
    out = _run(repo, tmp_path, actor="alice", manifest=m)
    assert out.returncode == 2, out.stderr
    assert "panel.py" in out.stderr


def test_own_lane_commit_passes(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, "harness/scripts/auth_login.py")  # alice's lane
    m = _manifest(tmp_path, _UNITS)
    out = _run(repo, tmp_path, actor="alice", manifest=m)
    assert out.returncode == 0, out.stderr


def test_ungoverned_actor_passes(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, "harness/ui/panel.py")
    m = _manifest(tmp_path, _UNITS)
    out = _run(repo, tmp_path, actor="carol", manifest=m)  # owns nothing
    assert out.returncode == 0, out.stderr


def test_missing_manifest_skips(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, "harness/ui/panel.py")
    # No HARNESS_WORK_OWNERSHIP_FILE → additive skip, never blocks.
    out = _run(repo, tmp_path, actor="alice", manifest=None)
    assert out.returncode == 0, out.stderr


def test_non_commit_command_skips(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, "harness/ui/panel.py")
    m = _manifest(tmp_path, _UNITS)
    out = _run(repo, tmp_path, actor="alice", manifest=m, command="git status")
    assert out.returncode == 0, out.stderr


def test_warn_downgrades_to_advisory(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, "harness/ui/panel.py")
    m = _manifest(tmp_path, _UNITS)
    out = _run(repo, tmp_path, actor="alice", manifest=m,
               policy=_policy(tmp_path, ownership_guard="warn"))
    assert out.returncode == 0, out.stderr
    assert "panel.py" in out.stderr  # advisory still names the file


def test_block_emits_trace_with_actor(tmp_path):
    repo = _repo(tmp_path)
    _stage(repo, "harness/ui/panel.py")
    m = _manifest(tmp_path, _UNITS)
    out = _run(repo, tmp_path, actor="alice", manifest=m)
    assert out.returncode == 2
    trace = tmp_path / "state" / "trace"
    text = "".join(p.read_text(encoding="utf-8")
                   for p in sorted(trace.glob("trace-*.jsonl"))) if trace.is_dir() else ""
    assert "ownership_guard" in text
    line = [json.loads(l) for l in text.splitlines()
            if "ownership_block" in l]
    assert line and line[0]["actor"]
