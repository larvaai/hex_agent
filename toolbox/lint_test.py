"""Structured validation tools — compile / ruff / pytest, no arbitrary shell. Epic E06.

These run a *fixed*, allowlisted argv (``sys.executable -m py_compile|ruff|pytest``) inside
the workspace, never a shell string, so they validate without opening a command-injection
surface. Their ``ok`` is the signal ``discipline.finish_gate`` keys on before letting a run
finish with code changes. ``ruff`` is optional and degrades to ``dependency_failure``.
"""
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core.schemas import ToolRequest
from safety.sandbox import SandboxError, resolve_in_workspace, workspace_dir

MAX_FILES = 1000
MAX_TIMEOUT_SECONDS = 120
EXCLUDED_DIRS = {".git", ".venv", "__pycache__", "node_modules", "var", "qdrant_storage"}


def _clamp_timeout(value: Any, default: int) -> int:
    try:
        return max(1, min(int(value), MAX_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return default


def _is_excluded(path: Path) -> bool:
    try:
        parts = set(path.resolve().relative_to(workspace_dir()).parts)
    except ValueError:
        return True
    return bool(parts & EXCLUDED_DIRS)


def _python_files(root: Path, max_files: int) -> tuple[list[Path], bool]:
    if root.is_file():
        return ([root] if root.suffix.lower() == ".py" else []), False
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if len(files) >= max_files:
            return files, True
        if path.is_file() and not _is_excluded(path):
            files.append(path)
    return files, False


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join([str(workspace_dir()), env.get("PYTHONPATH", "")])
    return env


def _run(command: list[str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(workspace_dir()),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_env(),
        )
    except FileNotFoundError:
        return {"ok": False, "dependency_failure": True, "error": f"Command not found: {command[0]}", "returncode": None}
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": f"Command timed out after {timeout} seconds.",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def _ruff_available() -> bool:
    return _run([sys.executable, "-m", "ruff", "--version"], timeout=20).get("ok", False)


class LintCompile:
    name = "lint_compile"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        try:
            root = resolve_in_workspace(str(request.args.get("path", ".")))
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        files, truncated = _python_files(root, MAX_FILES)
        failures: list[dict[str, Any]] = []
        for file_path in files:
            try:
                py_compile.compile(str(file_path), doraise=True)
            except py_compile.PyCompileError as exc:
                failures.append({"file": str(file_path), "error": str(exc)})
        return {
            "ok": not failures,
            "checked_files": len(files),
            "truncated": truncated,
            "failures": failures[:100],
            "validation": True,
        }


class RuffCheck:
    name = "ruff_check"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        try:
            target = resolve_in_workspace(str(request.args.get("path", ".")))
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        if not _ruff_available():
            return {"ok": False, "dependency_failure": True, "error": "ruff is not available"}
        timeout = _clamp_timeout(request.args.get("timeout", 30), 30)
        result = _run([sys.executable, "-m", "ruff", "check", str(target)], timeout=timeout)
        result["validation"] = True
        return result


class PytestRun:
    name = "pytest_run"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        try:
            target = resolve_in_workspace(str(request.args.get("path", ".")))
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        if not target.exists():
            return {"ok": False, "error": f"Path does not exist: {target}"}
        timeout = _clamp_timeout(request.args.get("timeout", 60), 60)
        result = _run([sys.executable, "-m", "pytest", str(target), "-q", "-p", "no:cacheprovider"], timeout=timeout)
        result["validation"] = True
        return result


LINT_TEST_TOOLS = (LintCompile, RuffCheck, PytestRun)
