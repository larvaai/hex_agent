"""Workspace path-jail — resolve a path and ensure it stays inside the workspace. Epic E06."""
from __future__ import annotations

import os
import re
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

# A Windows drive-letter prefix: one letter, a colon, at the very start.
# Matches "C:/...", "C:\\...", and the drive-relative "c:foo". POSIX treats
# such a string as a *relative* path (is_absolute() is False), so the jail must
# catch it lexically before that misjudgement lets it slip inside the workspace.
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")


class SandboxError(ValueError):
    pass


def workspace_dir() -> Path:
    return Path(os.getenv("AGENT_WORKSPACE_DIR", str(PROJECT_DIR / "var" / "workspace"))).resolve()


def _reject_foreign_path_syntax(raw_path: str) -> None:
    """Fail closed on path syntax that escapes the jail on *some* OS, even if inert here.

    A path-jail must not trust how the host OS happens to read a string. On POSIX a
    backslash is a literal filename char and "C:/..." is relative, so "..\\escape" and
    "C:/Windows/..." both resolve *inside* the workspace and the resolved-path check
    below never fires. But the identical string is a traversal ("..\\escape") or an
    absolute path ("C:\\...") on Windows. If such a value ever crosses into a
    Windows-aware context — a config read there, a UNC handler, a subprocess — it
    breaks out. So we reject the most permissive interpretation up front. This mirrors
    the same lexical guard EventLogger already applies to run_id (observability/event_log.py).

    The error message keeps the "outside workspace" wording so callers and tests can
    treat every jail rejection uniformly.
    """
    if "\\" in raw_path:
        raise SandboxError(f"Path is outside workspace (Windows backslash separator): {raw_path}")
    if _DRIVE_LETTER.match(raw_path):
        raise SandboxError(f"Path is outside workspace (Windows drive-letter prefix): {raw_path}")


def resolve_in_workspace(raw_path: str) -> Path:
    """Resolve a (possibly relative) path under the workspace; raise if it escapes."""
    workspace = workspace_dir()
    _reject_foreign_path_syntax(raw_path)
    path = Path(raw_path)
    if not path.is_absolute():
        path = workspace / path
    resolved = path.resolve()
    if resolved != workspace and not resolved.is_relative_to(workspace):
        raise SandboxError(f"Path is outside workspace: {raw_path}")
    return resolved
