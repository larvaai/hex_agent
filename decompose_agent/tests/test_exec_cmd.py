"""Whitelisted no-shell command runner (#4): the safety boundary is the whitelist + no shell +
hard timeout. (Network isolation is intentionally NOT claimed — see exec_cmd module docstring.)"""
from __future__ import annotations

import sys

from decompose_agent import exec_cmd as E


def test_unwhitelisted_cmd_id_is_rejected(tmp_path):
    r = E.run_cmd("not_registered", {}, tmp_path)
    assert not r.ok and "not whitelisted" in r.reason and r.code is None


def test_whitelisted_cmd_runs_and_returns_exit_code(tmp_path):
    E.register_cmd("py_exit", [sys.executable, "-c", "import sys; sys.exit(int('{n}'))"])
    assert E.run_cmd("py_exit", {"n": 0}, tmp_path).code == 0
    assert E.run_cmd("py_exit", {"n": 7}, tmp_path).code == 7


def test_timeout_is_enforced(tmp_path):
    E.register_cmd("py_sleep", [sys.executable, "-c", "import time; time.sleep(5)"])
    r = E.run_cmd("py_sleep", {}, tmp_path, timeout=0.4)
    assert not r.ok and "timeout" in r.reason


def test_no_shell_means_no_injection(tmp_path):
    # a param full of shell metachars is just a literal argv element (shell=False) — nothing chains
    E.register_cmd("py_echo", [sys.executable, "-c", "print('{msg}')"])
    r = E.run_cmd("py_echo", {"msg": "hi && touch PWNED ; rm -rf /"}, tmp_path)
    assert r.ok and "hi && touch PWNED ; rm -rf /" in r.stdout  # printed literally, not executed
    assert not (tmp_path / "PWNED").exists()


def test_register_rejects_empty_template():
    import pytest
    with pytest.raises(ValueError):
        E.register_cmd("bad", [])


# ── review-hardening (#4): the runner is fail-closed regardless of upstream ───

def test_extra_non_placeholder_param_is_rejected(tmp_path):
    E.register_cmd("py_p", [sys.executable, "-c", "print('{path}')"])
    r = E.run_cmd("py_p", {"path": "ok", "evil": "x"}, tmp_path)  # 'evil' isn't a placeholder
    assert not r.ok and "not a placeholder" in r.reason


def test_path_escape_param_is_rejected(tmp_path):
    E.register_cmd("py_cat", [sys.executable, "-c", "print(open('{path}').read())"])
    for bad in ["../../../etc/passwd", "/etc/passwd", "~/secret"]:
        r = E.run_cmd("py_cat", {"path": bad}, tmp_path)
        assert not r.ok and "unsafe" in r.reason


def test_absurd_timeout_is_clamped_not_hung(tmp_path):
    E.register_cmd("py_quick", [sys.executable, "-c", "pass"])
    assert E.run_cmd("py_quick", {}, tmp_path, timeout=10 ** 9).code == 0  # clamped to MAX_TIMEOUT, runs fine
