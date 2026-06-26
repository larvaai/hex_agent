"""Rigor for the structured-validation toolbox: fixed-argv exec, no-shell injection surface,
timeout kill, dependency degradation, and the sandbox jail on all three tools.

Subject: toolbox/lint_test.py — LintCompile (lint_compile), RuffCheck (ruff_check),
PytestRun (pytest_run). These run a FIXED allowlisted argv (``sys.executable -m
py_compile|ruff|pytest``), never a shell string, inside the workspace. This file pins the
error/edge branches the happy-path tests (tests/test_lint_test.py) leave uncovered —
``_clamp_timeout`` non-int/clamp (29-30), ``_is_excluded`` outside-workspace ValueError
(36-37), ``_python_files`` single-file root + max_files truncation (43, 47), ``_run``
FileNotFoundError + TimeoutExpired (74-77), and the SandboxError / dependency-failure /
missing-path branches on each tool (128-129, 131, 144-145, 147) — plus the security
invariants the assignment calls for: there is NO shell, so shell metacharacters in a path are
treated literally and never executed; a runaway command is really killed at the timeout; and a
path escaping the workspace is refused by every tool. Real robustness gaps are pinned with a
strict-less xfail citing file:line, never papered over by a loosened assertion.

These tests spawn real subprocesses; timeouts are kept tiny (1-3s) and inputs minimal so the
suite stays fast and deterministic.
"""
from __future__ import annotations

import os
import sys
import time

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.schemas import ToolRequest
from safety.sandbox import SandboxError, resolve_in_workspace, workspace_dir
from toolbox import lint_test
from toolbox.lint_test import (
    MAX_FILES,
    MAX_TIMEOUT_SECONDS,
    LintCompile,
    PytestRun,
    RuffCheck,
    _clamp_timeout,
    _env,
    _is_excluded,
    _python_files,
    _run,
)


def _req(name: str, **args) -> ToolRequest:
    return ToolRequest(name=name, args=args)


# --------------------------------------------------------------------------------------
# _clamp_timeout — lines 29-30 (TypeError/ValueError -> default) and the [1, 120] clamp
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 60),        # TypeError on int(None) -> default
        ("x", 60),         # ValueError on int('x') -> default
        ([], 60),          # TypeError on int([]) -> default
        ({"a": 1}, 60),    # TypeError -> default
        (0, 1),            # clamped up to floor 1
        (-5, 1),           # negative clamped up to 1
        (1, 1),            # boundary low
        (60, 60),          # mid, unchanged
        (120, 120),        # boundary high (== MAX)
        (121, 120),        # just over -> clamped to MAX
        (10_000, 120),     # huge -> clamped to MAX
        (3.9, 3),          # float is int-able -> truncated, NOT the default
        ("7", 7),          # numeric string is int-able -> 7, NOT the default
        (True, 1),         # bool is an int subclass -> int(True)=1, clamps to 1
    ],
)
def test_clamp_timeout_branches_and_clamp(value, expected):
    assert _clamp_timeout(value, default=60) == expected


@pytest.mark.audit
def test_clamp_timeout_default_is_returned_verbatim_for_garbage():
    """The *default* argument is what comes back on TypeError/ValueError — not a hardcoded 60."""
    assert _clamp_timeout(object(), default=42) == 42
    assert _clamp_timeout("not-a-number", default=99) == 99


@pytest.mark.audit
@pytest.mark.property
@given(value=st.integers(min_value=-10**9, max_value=10**9))
def test_property_clamp_timeout_int_always_in_range(value):
    """For ANY int input, the result is always within [1, MAX_TIMEOUT_SECONDS] and never raises."""
    out = _clamp_timeout(value, default=60)
    assert 1 <= out <= MAX_TIMEOUT_SECONDS
    assert isinstance(out, int)


@pytest.mark.audit
@pytest.mark.property
@given(value=st.one_of(st.none(), st.text(), st.lists(st.integers()), st.dictionaries(st.text(), st.integers())))
def test_property_clamp_timeout_noninty_returns_default(value):
    """Any non-int-coercible input returns the default unchanged and never raises."""
    assert _clamp_timeout(value, default=55) == 55


# --------------------------------------------------------------------------------------
# _is_excluded — line 36-37 (path outside workspace -> ValueError -> excluded == True)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_is_excluded_treats_path_outside_workspace_as_excluded(tmp_path, monkeypatch):
    """lint_test.py:36-37 — a path whose resolved form is NOT under the workspace makes
    relative_to() raise ValueError, which is caught and reported as excluded (fail-closed)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    # An absolute path that lives entirely outside the workspace.
    outside = tmp_path / "outside" / "stranger.py"
    assert _is_excluded(outside) is True


@pytest.mark.audit
def test_is_excluded_passes_ordinary_workspace_file(tmp_path, monkeypatch):
    """A plain .py directly under the workspace is NOT excluded (the True branch must be specific)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    keeper = ws / "keeper.py"
    keeper.write_text("x = 1\n", encoding="utf-8")
    assert _is_excluded(keeper) is False


@pytest.mark.audit
@pytest.mark.parametrize("excluded_dir", sorted(lint_test.EXCLUDED_DIRS))
def test_is_excluded_filters_each_excluded_dir(tmp_path, monkeypatch, excluded_dir):
    """A file living under any EXCLUDED_DIRS component is excluded."""
    ws = tmp_path / "ws"
    (ws / excluded_dir).mkdir(parents=True)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    buried = ws / excluded_dir / "mod.py"
    buried.write_text("x = 1\n", encoding="utf-8")
    assert _is_excluded(buried) is True


# --------------------------------------------------------------------------------------
# _python_files — line 43 (single-file root) and line 47 (max_files truncation)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_python_files_single_py_file_root(tmp_path, monkeypatch):
    """lint_test.py:43 — when root is a single .py FILE it is returned as the sole entry."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    f = ws / "solo.py"
    f.write_text("x = 1\n", encoding="utf-8")
    files, truncated = _python_files(f, MAX_FILES)
    assert files == [f]
    assert truncated is False


@pytest.mark.audit
def test_python_files_single_non_py_file_root_is_empty(tmp_path, monkeypatch):
    """lint_test.py:43 — a single NON-.py file root yields an empty list (suffix check)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    f = ws / "data.txt"
    f.write_text("not python", encoding="utf-8")
    files, truncated = _python_files(f, MAX_FILES)
    assert files == []
    assert truncated is False


@pytest.mark.audit
def test_python_files_single_py_file_root_uppercase_suffix(tmp_path, monkeypatch):
    """The suffix check is case-insensitive (.PY counts) — root.suffix.lower() == '.py'."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    f = ws / "Caps.PY"
    f.write_text("x = 1\n", encoding="utf-8")
    files, _ = _python_files(f, MAX_FILES)
    assert files == [f]


@pytest.mark.audit
def test_python_files_truncates_at_max_files(tmp_path, monkeypatch):
    """lint_test.py:46-47 — once max_files entries are gathered the walk stops and truncated=True."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    for i in range(5):
        (ws / f"m{i}.py").write_text("x = 1\n", encoding="utf-8")
    files, truncated = _python_files(ws, max_files=2)
    assert truncated is True
    assert len(files) == 2  # stopped early, did not gather all five


@pytest.mark.audit
def test_python_files_no_truncation_when_under_limit(tmp_path, monkeypatch):
    """A tree under the cap returns every .py and truncated=False."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    for i in range(3):
        (ws / f"m{i}.py").write_text("x = 1\n", encoding="utf-8")
    files, truncated = _python_files(ws, max_files=1000)
    assert truncated is False
    assert len(files) == 3


@pytest.mark.audit
@pytest.mark.security
def test_python_files_skips_symlinked_file_resolving_outside_workspace(tmp_path, monkeypatch):
    """A symlink inside the workspace pointing at an outside .py is dropped by _is_excluded's
    ValueError branch (36-37): rglob discovers it, resolve() lands outside, relative_to raises."""
    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    (outside / "evil.py").write_text("x = 1\n", encoding="utf-8")
    (ws / "good.py").write_text("y = 2\n", encoding="utf-8")
    try:
        (ws / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - host without symlink perms
        pytest.skip(f"host does not permit symlink creation: {exc}")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    files, _ = _python_files(ws, MAX_FILES)
    names = {f.name for f in files}
    # The in-jail file is kept; the symlinked outside file is excluded.
    assert "good.py" in names
    assert all("outside" not in str(f.resolve()) for f in files)


# --------------------------------------------------------------------------------------
# _env — PYTHONPATH includes the workspace; PYTHONIOENCODING is utf-8 (no os.environ mutation)
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_env_sets_ioencoding_and_prepends_workspace_to_pythonpath(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    env = _env()
    assert env["PYTHONIOENCODING"] == "utf-8"
    entries = env["PYTHONPATH"].split(os.pathsep)
    assert str(workspace_dir()) in entries
    assert entries[0] == str(workspace_dir())  # prepended, takes precedence


@pytest.mark.audit
def test_env_does_not_mutate_process_environment(tmp_path, monkeypatch):
    """_env() returns a COPY; the real os.environ is untouched (only the child sees the changes)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    before_ioenc = os.environ.get("PYTHONIOENCODING")
    before_pp = os.environ.get("PYTHONPATH")
    _env()
    assert os.environ.get("PYTHONIOENCODING") == before_ioenc
    assert os.environ.get("PYTHONPATH") == before_pp


# --------------------------------------------------------------------------------------
# _run — line 74-75 FileNotFoundError -> dependency_failure; line 76-77 TimeoutExpired
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_run_missing_binary_is_dependency_failure(tmp_path, monkeypatch):
    """lint_test.py:74-75 — a bogus argv[0] surfaces a clean dependency_failure, never a traceback."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    result = _run(["definitely_no_such_binary_zxq_999", "--version"], timeout=2)
    assert result["ok"] is False
    assert result["dependency_failure"] is True
    assert result["returncode"] is None
    assert "Command not found" in result["error"]
    assert "definitely_no_such_binary_zxq_999" in result["error"]


@pytest.mark.audit
@pytest.mark.security
def test_run_kills_and_reports_command_that_outlives_timeout(tmp_path, monkeypatch):
    """lint_test.py:76-84 — a 5s sleep with timeout=1 is really killed: ok=False, a timeout
    message, returncode None, duration present, and we return well before the sleep finishes."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    start = time.monotonic()
    result = _run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)
    elapsed = time.monotonic() - start
    assert result["ok"] is False
    assert result["returncode"] is None
    assert result["error"] == "Command timed out after 1 seconds."
    assert "duration_seconds" in result and result["duration_seconds"] >= 0
    # stdout/stderr keys are present (empty on a killed child), proving the except branch ran.
    assert result["stdout"] == "" and result["stderr"] == ""
    assert elapsed < 4.5  # the 5s sleep was cut short, not awaited


@pytest.mark.audit
def test_run_success_envelope_has_returncode_and_duration(tmp_path, monkeypatch):
    """The happy path (85-91): a trivial command returns ok=True, returncode 0, captured stdout."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    result = _run([sys.executable, "-c", "print('hello-run')"], timeout=10)
    assert result["ok"] is True
    assert result["returncode"] == 0
    assert "hello-run" in result["stdout"]
    assert result["duration_seconds"] >= 0


# --------------------------------------------------------------------------------------
# LintCompile (lint_compile) — good tree, bad file, exclusions, truncation, sandbox
# --------------------------------------------------------------------------------------


@pytest.mark.audit
def test_lint_compile_clean_tree_is_ok(tmp_path, monkeypatch):
    """A tree of valid modules compiles: ok=True, checked_files>0, validation flag set."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    (ws / "a.py").write_text("x = 1\n", encoding="utf-8")
    (ws / "b.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    result = LintCompile().execute(_req("lint_compile", path="."))
    assert result["ok"] is True
    assert result["checked_files"] >= 2
    assert result["truncated"] is False
    assert result["failures"] == []
    assert result["validation"] is True


@pytest.mark.audit
def test_lint_compile_syntactically_bad_file_is_failure(tmp_path, monkeypatch):
    """A module with a syntax error -> ok=False and the offending file appears in failures."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    bad = ws / "broken.py"
    bad.write_text("def oops(:\n    pass\n", encoding="utf-8")  # invalid syntax
    result = LintCompile().execute(_req("lint_compile", path="broken.py"))
    assert result["ok"] is False
    assert result["validation"] is True
    failure_files = {f["file"] for f in result["failures"]}
    assert str(bad.resolve()) in failure_files
    assert any("error" in f for f in result["failures"])


@pytest.mark.audit
def test_lint_compile_skips_excluded_dirs(tmp_path, monkeypatch):
    """A broken module buried under an EXCLUDED_DIRS folder is skipped -> overall ok=True."""
    ws = tmp_path / "ws"
    (ws / "__pycache__").mkdir(parents=True)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    (ws / "good.py").write_text("x = 1\n", encoding="utf-8")
    (ws / "__pycache__" / "junk.py").write_text("def broken(:\n", encoding="utf-8")
    result = LintCompile().execute(_req("lint_compile", path="."))
    assert result["ok"] is True
    # Only the in-tree good.py is compiled; the excluded broken module is not counted.
    assert result["checked_files"] == 1


@pytest.mark.audit
def test_lint_compile_truncation_flag_via_max_files(tmp_path, monkeypatch):
    """When the .py count exceeds MAX_FILES the result reports truncated=True. We drive this
    deterministically through _python_files' max_files parameter rather than creating 1000 files."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    for i in range(4):
        (ws / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")
    files, truncated = _python_files(ws, max_files=2)
    assert truncated is True and len(files) == 2


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    "bad_path",
    ["../escape", "/etc/passwd", "..\\windows_escape", "C:/Windows/System32", "nested/../../escape"],
)
def test_lint_compile_rejects_escape_paths(tmp_path, monkeypatch, bad_path):
    """lint_test.py:104-105 — a path escaping the workspace yields a clean failure, no walk."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    result = LintCompile().execute(_req("lint_compile", path=bad_path))
    assert result["ok"] is False
    assert "outside workspace" in result["error"]
    assert "checked_files" not in result  # bailed before walking


# --------------------------------------------------------------------------------------
# SECURITY CRUX — argv runs WITHOUT a shell: metacharacters in a path are literal, never run
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_lint_compile_shell_metacharacter_path_is_literal_no_side_effect(tmp_path, monkeypatch):
    """A workspace file whose NAME contains shell metacharacters ('; touch pwned') is passed to
    py_compile as a literal path. No shell interprets it, so no side-effect file is ever created."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    sentinel = ws / "pwned"
    # A real .py file whose basename embeds shell metacharacters.
    evil_name = "evil; touch pwned && echo $(touch pwned2) `touch pwned3`.py"
    evil = ws / evil_name
    evil.write_text("x = 1\n", encoding="utf-8")
    result = LintCompile().execute(_req("lint_compile", path=evil_name))
    assert result["ok"] is True  # the literal file compiles fine
    assert result["checked_files"] == 1
    # The decisive proof: NONE of the injected side-effect files exist.
    assert not sentinel.exists()
    assert not (ws / "pwned2").exists()
    assert not (ws / "pwned3").exists()


@pytest.mark.audit
@pytest.mark.security
def test_pytest_run_shell_metacharacter_path_is_literal_no_side_effect(tmp_path, monkeypatch):
    """pytest_run on a path with shell metacharacters does not spawn a shell: the path is delivered
    verbatim to `python -m pytest`, no injected command runs, no side-effect file appears."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    sentinel = ws / "INJECTED"
    evil_name = "spec; touch INJECTED.py"
    (ws / evil_name).write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = PytestRun().execute(_req("pytest_run", path=evil_name, timeout=15))
    # Regardless of pytest's own verdict, the injection NEVER executed.
    assert not sentinel.exists()
    assert "returncode" in result  # the subprocess ran (literal path), not a shell


# --------------------------------------------------------------------------------------
# RuffCheck (ruff_check) — sandbox (128-129), dependency_failure (131), available path
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    "bad_path",
    ["../escape", "/etc/passwd", "..\\win", "C:/Windows", "a/../../escape"],
)
def test_ruff_check_rejects_escape_paths(tmp_path, monkeypatch, bad_path):
    """lint_test.py:128-129 — a path outside the jail fails closed before ruff is consulted."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    result = RuffCheck().execute(_req("ruff_check", path=bad_path))
    assert result["ok"] is False
    assert "outside workspace" in result["error"]
    assert "dependency_failure" not in result  # never reached the availability probe


@pytest.mark.audit
def test_ruff_check_unavailable_is_dependency_failure(tmp_path, monkeypatch):
    """lint_test.py:130-131 — when ruff is absent the tool degrades to dependency_failure, ok=False."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(lint_test, "_ruff_available", lambda: False)
    result = RuffCheck().execute(_req("ruff_check", path="."))
    assert result == {"ok": False, "dependency_failure": True, "error": "ruff is not available"}


@pytest.mark.audit
def test_ruff_check_available_runs_and_sets_validation(tmp_path, monkeypatch):
    """When ruff IS installed (this env has 0.15.x) a clean file passes: ok=True, validation=True.
    Skips gracefully if the host lacks ruff so the suite never silently weakens."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    if not lint_test._ruff_available():
        pytest.skip("ruff not installed on this host")
    clean = ws / "clean.py"
    clean.write_text("x = 1\n", encoding="utf-8")
    result = RuffCheck().execute(_req("ruff_check", path="clean.py", timeout=20))
    assert result["validation"] is True
    assert result["ok"] is True
    assert result["returncode"] == 0


@pytest.mark.audit
def test_ruff_check_flags_a_lint_violation(tmp_path, monkeypatch):
    """A file with an obvious ruff violation (unused import) is reported as a non-zero failure."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    if not lint_test._ruff_available():
        pytest.skip("ruff not installed on this host")
    dirty = ws / "dirty.py"
    dirty.write_text("import os\n", encoding="utf-8")  # F401 unused import
    result = RuffCheck().execute(_req("ruff_check", path="dirty.py", timeout=20))
    assert result["validation"] is True
    assert result["ok"] is False
    assert result["returncode"] not in (0, None)


# --------------------------------------------------------------------------------------
# PytestRun (pytest_run) — sandbox (144-145), missing path (147), pass/fail subprocess
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    "bad_path",
    ["../escape", "/etc/passwd", "..\\win", "C:/Windows", "x/../../escape"],
)
def test_pytest_run_rejects_escape_paths(tmp_path, monkeypatch, bad_path):
    """lint_test.py:144-145 — a path outside the workspace fails closed before any subprocess."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    result = PytestRun().execute(_req("pytest_run", path=bad_path))
    assert result["ok"] is False
    assert "outside workspace" in result["error"]
    assert "returncode" not in result  # never spawned


@pytest.mark.audit
def test_pytest_run_nonexistent_path_is_error(tmp_path, monkeypatch):
    """lint_test.py:146-147 — a path inside the jail that does not exist short-circuits to error."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    result = PytestRun().execute(_req("pytest_run", path="ghost_dir/ghost_test.py"))
    assert result["ok"] is False
    assert result["error"].startswith("Path does not exist:")
    assert "returncode" not in result  # never spawned a subprocess


@pytest.mark.audit
def test_pytest_run_passing_test_file_is_ok(tmp_path, monkeypatch):
    """A tiny passing test file -> ok=True, returncode 0, validation flag set."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    t = ws / "test_pass.py"
    t.write_text("def test_truth():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    result = PytestRun().execute(_req("pytest_run", path="test_pass.py", timeout=30))
    assert result["validation"] is True
    assert result["ok"] is True
    assert result["returncode"] == 0


@pytest.mark.audit
def test_pytest_run_failing_test_file_is_failure(tmp_path, monkeypatch):
    """A failing test file -> ok=False with a non-zero returncode (the subprocess really ran)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    t = ws / "test_fail.py"
    t.write_text("def test_lie():\n    assert 1 == 2\n", encoding="utf-8")
    result = PytestRun().execute(_req("pytest_run", path="test_fail.py", timeout=30))
    assert result["validation"] is True
    assert result["ok"] is False
    assert result["returncode"] not in (0, None)


@pytest.mark.audit
def test_pytest_run_default_path_is_workspace_root(tmp_path, monkeypatch):
    """No path arg defaults to '.' -> the workspace root (which exists), so it does not error out
    on the missing-path branch; it actually runs pytest there."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    (ws / "test_solo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = PytestRun().execute(_req("pytest_run", timeout=30))
    assert result["validation"] is True
    assert "returncode" in result  # the root existed -> subprocess ran, not the error branch


# --------------------------------------------------------------------------------------
# Cross-tool sandbox property: every tool turns a jail escape into a clean failure envelope
# --------------------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.property
@given(
    prefix=st.sampled_from(["../", "../../", "..\\", "/", "C:/", "C:\\"]),
    tail=st.text(alphabet="abc/_", min_size=1, max_size=10),
)
def test_property_all_tools_block_escape_prefixes(tmp_path, monkeypatch, prefix, tail):
    """No traversal/absolute/windows prefix is ever accepted by any of the three tools."""
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    bad = prefix + tail
    for tool, name in [(LintCompile(), "lint_compile"), (RuffCheck(), "ruff_check"), (PytestRun(), "pytest_run")]:
        result = tool.execute(_req(name, path=bad))
        assert result["ok"] is False
        assert "outside workspace" in result["error"]


@pytest.mark.audit
@pytest.mark.security
def test_resolve_in_workspace_is_the_single_chokepoint(tmp_path, monkeypatch):
    """Sanity anchor: the escape rejection the tools rely on comes from resolve_in_workspace
    raising SandboxError — the tools simply translate it into their failure envelope."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    with pytest.raises(SandboxError):
        resolve_in_workspace("../escape")
