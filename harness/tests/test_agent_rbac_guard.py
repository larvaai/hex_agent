"""Tests for agent_rbac_guard — PreToolUse compliance gate keyed on agent_type.

Mirrors ownership_guard: a thin wrapper whose core() returns None (pass) or a
reason string (block) under run_compliance_hook (fail-closed). It reads the role
straight off the payload (agent_type / subagent_type, NOT resolve_actor, which
collapses parent/sub on the shared session_id), relativizes the write target to
the repo root, and consults the agent_permissions table.

Additive-skip: with no permission table the gate is inert (allow). The top-level
agent (_parent) is unrestricted unless the table declares it.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import hook_runtime  # noqa: E402,F401

HOOK_PATH = _HOOKS / "agent_rbac_guard.py"


def _hr():
    import hook_runtime as hr  # noqa: E402
    return sys.modules.get("hook_runtime", hr)


def _load():
    spec = importlib.util.spec_from_file_location("agent_rbac_guard", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_hook_config(path: Path, enabled: bool = True):
    path.write_text(
        "hooks:\n  agent_rbac_guard:\n    enabled: %s\n"
        % ("true" if enabled else "false"), encoding="utf-8")


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    state = tmp_path / "state"
    logs = tmp_path / "logs"
    for d in (state, logs):
        d.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "harness-hooks.yaml"
    _write_hook_config(cfg, enabled=True)
    perm = tmp_path / "agent-permissions.yaml"  # written per-test
    monkeypatch.setenv("HARNESS_STATE_DIR", str(state))
    monkeypatch.setenv("HARNESS_HOOK_LOG_DIR", str(logs))
    monkeypatch.setenv("HARNESS_HOOK_CONFIG", str(cfg))
    monkeypatch.setenv("HARNESS_AGENT_PERMISSIONS_FILE", str(perm))
    monkeypatch.setenv("HARNESS_USER", "tester")
    _hr()._reset_config_cache()
    yield {"state": state, "cfg": cfg, "perm": perm, "root": tmp_path}
    _hr()._reset_config_cache()


def _perm(env, body):
    env["perm"].write_text(body, encoding="utf-8")


def _payload(env, *, agent_type=None, subagent_type=None, rel="harness/x.py",
            tool="Write"):
    data = {"session_id": "s1", "cwd": str(env["root"]),
            "hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"file_path": str(env["root"] / rel)}}
    if agent_type is not None:
        data["agent_type"] = agent_type
    if subagent_type is not None:
        data["subagent_type"] = subagent_type
    return data


# ---------------------------------------------------------------------------
# core(): pass / block
# ---------------------------------------------------------------------------

def test_no_table_is_inert(_env):
    mod = _load()
    # perm file not written → absent → additive-skip → pass
    assert mod.core(_payload(_env, agent_type="general-purpose")) is None


def test_in_lane_passes(_env):
    _perm(_env, "roles:\n  general-purpose: ['harness/**']\n")
    mod = _load()
    assert mod.core(_payload(_env, agent_type="general-purpose",
                             rel="harness/x.py")) is None


def test_out_of_lane_blocks(_env):
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['plans/**']\n")
    mod = _load()
    reason = mod.core(_payload(_env, agent_type="general-purpose",
                               rel="harness/hooks/x.py"))
    assert reason and "outside" in reason.lower()


def test_parent_unrestricted(_env):
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['plans/**']\n")
    mod = _load()
    # no agent_type → _parent → unrestricted (no _parent entry)
    assert mod.core(_payload(_env, rel="harness/anything.py")) is None


def test_subagent_type_fallback(_env):
    _perm(_env, "default_deny: true\nroles:\n  cook: ['plans/**']\n")
    mod = _load()
    reason = mod.core(_payload(_env, subagent_type="cook", rel="harness/x.py"))
    assert reason and "cook" in reason


def test_non_write_tool_passes(_env):
    _perm(_env, "roles:\n  general-purpose: ['plans/**']\n")
    mod = _load()
    assert mod.core(_payload(_env, agent_type="general-purpose",
                             rel="harness/x.py", tool="Read")) is None


def test_malformed_table_fails_closed(_env):
    _perm(_env, "roles: [not, a, mapping]\n")
    mod = _load()
    reason = mod.core(_payload(_env, agent_type="general-purpose"))
    assert reason  # present-but-malformed → block reason, not silent skip


# ---------------------------------------------------------------------------
# isolation floor: cwd/worktree containment (independent of the glob lane)
# ---------------------------------------------------------------------------

def _escape_payload(env, *, agent_type=None):
    # a target OUTSIDE the cwd/worktree root
    outside = env["root"].parent / ("escape-%s.txt" % env["root"].name)
    data = {"session_id": "s1", "cwd": str(env["root"]),
            "hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": str(outside)}}
    if agent_type is not None:
        data["agent_type"] = agent_type
    return data


def test_containment_blocks_subagent_escape_even_with_broad_lane(_env):
    # a non-_parent role with a permissive '**' lane still cannot write OUTSIDE the
    # cwd/worktree root — the isolation floor catches what the glob would allow
    _perm(_env, "roles:\n  general-purpose: ['**']\n")
    mod = _load()
    reason = mod.core(_escape_payload(_env, agent_type="general-purpose"))
    assert reason and "isolation" in reason.lower()


def test_containment_allows_parent_escape(_env):
    # the top-level agent (_parent) is NOT containment-confined
    _perm(_env, "roles:\n  general-purpose: ['**']\n")
    mod = _load()
    assert mod.core(_escape_payload(_env)) is None


def test_containment_inert_without_table(_env):
    # no table → additive-skip → even an escape passes (gate inert by default)
    mod = _load()
    assert mod.core(_escape_payload(_env, agent_type="general-purpose")) is None


# ---------------------------------------------------------------------------
# CLI: real exit codes via run_compliance_hook
# ---------------------------------------------------------------------------

def _run(payload, env):
    return subprocess.run([sys.executable, str(HOOK_PATH)],
                          input=json.dumps(payload), capture_output=True,
                          text=True, env=env)


def test_cli_blocks_out_of_lane_exit2(_env):
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['plans/**']\n")
    env = dict(os.environ)
    p = _run(_payload(_env, agent_type="general-purpose", rel="harness/x.py"), env)
    assert p.returncode == 2, (p.returncode, p.stderr)
    assert "outside" in p.stderr.lower()


def test_cli_allows_in_lane_exit0(_env):
    _perm(_env, "roles:\n  general-purpose: ['harness/**']\n")
    env = dict(os.environ)
    p = _run(_payload(_env, agent_type="general-purpose", rel="harness/x.py"), env)
    assert p.returncode == 0, (p.returncode, p.stderr)


def test_cli_disabled_is_inert_exit0(_env):
    _write_hook_config(_env["cfg"], enabled=False)
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['plans/**']\n")
    env = dict(os.environ)
    p = _run(_payload(_env, agent_type="general-purpose", rel="harness/x.py"), env)
    assert p.returncode == 0, (p.returncode, p.stderr)


# ---------------------------------------------------------------------------
# present-but-empty attribution: a drifted subagent, NOT the top-level _parent
# ---------------------------------------------------------------------------

def test_empty_agent_type_does_not_collapse_to_parent(_env):
    # agent_type="" is a PRESENT-but-empty attribution → a drifted subagent whose
    # role vanished. It must NOT read as _parent (write-everything); under
    # default_deny it is fail-closed blocked.
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['plans/**']\n")
    mod = _load()
    assert mod.core(_payload(_env, agent_type="", rel="harness/x.py")) is not None


def test_whitespace_agent_type_does_not_collapse_to_parent(_env):
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['plans/**']\n")
    mod = _load()
    assert mod.core(_payload(_env, agent_type="   ", rel="harness/x.py")) is not None


def test_absent_agent_type_remains_parent(_env):
    # truly ABSENT (no key) is the real top-level agent → unrestricted
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['plans/**']\n")
    mod = _load()
    assert mod.core(_payload(_env, rel="harness/anything.py")) is None


# ---------------------------------------------------------------------------
# relative target resolves against the payload cwd, not the hook process cwd
# ---------------------------------------------------------------------------

def _rel_payload(env, *, agent_type, rel):
    return {"session_id": "s1", "cwd": str(env["root"]),
            "hook_event_name": "PreToolUse", "tool_name": "Write",
            "agent_type": agent_type, "tool_input": {"file_path": rel}}


def test_relative_target_contained_under_payload_cwd(_env):
    # a RELATIVE file_path must be resolved under the payload cwd (the worktree),
    # not the hook process cwd — else a legit in-worktree write false-blocks on the
    # isolation floor. In-lane relative write → pass.
    _perm(_env, "default_deny: true\nroles:\n  general-purpose: ['harness/**']\n")
    mod = _load()
    assert mod.core(_rel_payload(_env, agent_type="general-purpose",
                                 rel="harness/x.py")) is None


def test_relative_escape_still_blocks_isolation(_env):
    # '../escape.txt' relative to cwd still escapes the root → isolation block
    _perm(_env, "roles:\n  general-purpose: ['**']\n")
    mod = _load()
    reason = mod.core(_rel_payload(_env, agent_type="general-purpose",
                                   rel="../escape.txt"))
    assert reason and "isolation" in reason.lower()
