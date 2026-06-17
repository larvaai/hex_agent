"""Workspace path-jail — resolve a path and ensure it stays inside the workspace. Epic E06."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


class SandboxError(ValueError):
    pass


def workspace_dir() -> Path:
    return Path(os.getenv("AGENT_WORKSPACE_DIR", str(PROJECT_DIR / "var" / "workspace"))).resolve()


def resolve_in_workspace(raw_path: str) -> Path:
    """Resolve a (possibly relative) path under the workspace; raise if it escapes."""
    workspace = workspace_dir()
    path = Path(raw_path)
    if not path.is_absolute():
        path = workspace / path
    resolved = path.resolve()
    if resolved != workspace and not resolved.is_relative_to(workspace):
        raise SandboxError(f"Path is outside workspace: {raw_path}")
    return resolved
