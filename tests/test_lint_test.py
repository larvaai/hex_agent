"""Validation tools: lint_compile / ruff_check / pytest_run (offline subprocess). Epic E06."""
from __future__ import annotations

from core.schemas import ToolRequest
from toolbox.lint_test import LintCompile, PytestRun, RuffCheck


def _run(tool, **args):
    return tool().execute(ToolRequest(name=tool.name, args=args))


def test_lint_compile_passes_clean_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
    out = _run(LintCompile, path=".")
    assert out["ok"] is True and out["checked_files"] >= 1 and out["failures"] == []


def test_lint_compile_reports_syntax_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    out = _run(LintCompile, path=".")
    assert out["ok"] is False and len(out["failures"]) == 1


def test_pytest_run_on_passing_test(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    out = _run(PytestRun, path="test_ok.py")
    assert out["ok"] is True


def test_pytest_run_on_failing_test(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    out = _run(PytestRun, path="test_bad.py")
    assert out["ok"] is False and out["returncode"] != 0


def test_ruff_check_runs_or_degrades(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "m.py").write_text("import os\n", encoding="utf-8")
    out = _run(RuffCheck, path=".")
    # ruff ships in dev extras; either it ran (ok bool present) or it degraded cleanly.
    assert "ok" in out
    if not out["ok"]:
        assert out.get("dependency_failure") or out.get("returncode") is not None


def test_lint_compile_path_escape_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    out = _run(LintCompile, path="../../etc")
    assert out["ok"] is False and "outside workspace" in out["error"]
