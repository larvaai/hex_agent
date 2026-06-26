"""Workspace/project file operations for the live IDE backend.

The legacy console (``ui/server.py``) could only *read* files. The IDE needs the full set —
read, write, create, rename, delete, plus a per-session *diff* of what the agent changed — so the
user can both watch the agent edit and edit alongside it.

Every path crosses one jail (``_resolve``) that mirrors ``safety.sandbox``: it rejects Windows
foreign syntax up front (a path that escapes on *some* OS, even if inert here), resolves under the
chosen root, and refuses anything that lands outside it. The same sensitive-name / binary / size /
ignored-dir guards the read path already used apply to writes too — being able to edit is not a
licence to exfiltrate a private key or clobber ``.git``.

Diffs are computed against a *baseline* the runner snapshots at run start (``snapshot_baseline``);
``compute_diffs`` folds baseline-vs-current into unified diffs with the stdlib ``difflib`` — no new
dependency. Baselines are workspace-scoped: the agent's sandbox is ``var/workspace``, and snapshotting
the whole repo would be both huge and pointless.
"""
from __future__ import annotations

import difflib
import re
import shutil
from pathlib import Path
from typing import Any

from safety.sandbox import PROJECT_DIR, workspace_dir

# Kept in sync with the legacy console so both explorers hide the same noise.
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
SENSITIVE_NAMES = {
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "id_ecdsa",
    "id_dsa",
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pgpass",
    ".htpasswd",
}
SENSITIVE_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}
# Any name starting with one of these is sensitive (catches .env.local, .env.development, …).
SENSITIVE_PREFIXES = (".env",)

MAX_FILE_BYTES = 2 * 1024 * 1024  # editor preview/edit ceiling (bigger than the read-only console)
MAX_TREE_ENTRIES = 4_000
MAX_BASELINE_FILES = 2_000  # cap the diff baseline so a pathological workspace can't blow memory

_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")


class FileOpError(Exception):
    """Raised for any rejected file operation; the server maps it to a 4xx with this message."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def root_for_scope(scope: str) -> Path:
    """The jail root for a scope. ``workspace`` is the agent's sandbox; ``project`` is the repo."""
    if scope == "workspace":
        root = workspace_dir()
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()
    if scope == "project":
        return PROJECT_DIR.resolve()
    raise FileOpError("scope must be 'workspace' or 'project'")


def _is_hidden_project_path(relative: Path) -> bool:
    """Project-scope paths we never expose: ignored dirs and the agent's own run artifacts."""
    parts = relative.parts
    if any(part in IGNORED_DIRS for part in parts):
        return True
    return len(parts) >= 2 and parts[0] == "var" and parts[1] == "agent_runs"


def _resolve(scope: str, raw_path: str) -> tuple[Path, Path]:
    """Resolve ``raw_path`` under the scope root and return (absolute, relative). Fail closed.

    Mirrors ``safety.sandbox.resolve_in_workspace`` but for an arbitrary root, so the project
    explorer gets the identical traversal protection the workspace already had.
    """
    if "\\" in raw_path:
        raise FileOpError(f"Path is outside root (Windows backslash separator): {raw_path}")
    if _DRIVE_LETTER.match(raw_path):
        raise FileOpError(f"Path is outside root (Windows drive-letter prefix): {raw_path}")
    root = root_for_scope(scope)
    try:
        candidate = (root / raw_path).resolve()
    except (ValueError, OSError) as exc:  # embedded NUL etc.
        raise FileOpError(f"Invalid path: {raw_path}") from exc
    if candidate != root and not candidate.is_relative_to(root):
        raise FileOpError(f"Path is outside root: {raw_path}")
    relative = candidate.relative_to(root)
    if scope == "project" and _is_hidden_project_path(relative):
        raise FileOpError("this path is hidden from the project explorer", status=403)
    return candidate, relative


def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in SENSITIVE_NAMES
        or path.suffix.lower() in SENSITIVE_SUFFIXES
        or name.startswith(SENSITIVE_PREFIXES)
    )


# ── tree ────────────────────────────────────────────────────────────────────────
def _tree_node(path: Path, root: Path, scope: str, counter: list[int]) -> dict[str, Any] | None:
    if counter[0] >= MAX_TREE_ENTRIES:
        return None
    try:
        relative = path.relative_to(root)
        stat = path.lstat()
    except (OSError, ValueError):
        return None
    if scope == "project" and relative != Path(".") and _is_hidden_project_path(relative):
        return None
    counter[0] += 1
    relative_text = "" if relative == Path(".") else relative.as_posix()
    node: dict[str, Any] = {
        "name": root.name if not relative_text else path.name,
        "path": relative_text,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }
    if path.is_symlink():
        node["type"] = "symlink"
        return node
    if path.is_dir():
        node["type"] = "directory"
        children: list[dict[str, Any]] = []
        try:
            entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            entries = []
        for child in entries:
            child_node = _tree_node(child, root, scope, counter)
            if child_node is not None:
                children.append(child_node)
        node["children"] = children
    else:
        node["type"] = "file"
    return node


def tree_snapshot(scope: str) -> dict[str, Any]:
    root = root_for_scope(scope)
    counter = [0]
    tree = _tree_node(root, root, scope, counter)
    return {
        "scope": scope,
        "root": str(root),
        "tree": tree,
        "entries": counter[0],
        "truncated": counter[0] >= MAX_TREE_ENTRIES,
    }


# ── read ────────────────────────────────────────────────────────────────────────
def _decode(raw: bytes) -> str:
    if b"\x00" in raw[:4096]:
        raise FileOpError("binary file editing is disabled")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileOpError("file is not UTF-8 text") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_file(scope: str, raw_path: str) -> dict[str, Any]:
    path, relative = _resolve(scope, raw_path)
    if not path.is_file():
        raise FileOpError("file not found", status=404)
    if _is_sensitive(path):
        raise FileOpError("sensitive file access is disabled", status=403)
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise FileOpError(f"file exceeds edit limit ({MAX_FILE_BYTES} bytes)")
    content = _decode(path.read_bytes())
    return {
        "scope": scope,
        "path": relative.as_posix(),
        "name": path.name,
        "size": size,
        "content": content,
        "language": _language_for(path.name),
    }


# ── write / create / rename / delete ─────────────────────────────────────────────
def write_file(scope: str, raw_path: str, content: str) -> dict[str, Any]:
    path, relative = _resolve(scope, raw_path)
    if _is_sensitive(path):
        raise FileOpError("sensitive file writes are disabled", status=403)
    if path.is_dir():
        raise FileOpError("path is a directory")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise FileOpError(f"content exceeds edit limit ({MAX_FILE_BYTES} bytes)")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Normalise to LF (the read path strips CR), so a round-trip never injects CRLF noise.
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(normalized, encoding="utf-8")
    return {"ok": True, "scope": scope, "path": relative.as_posix(), "bytes": len(normalized.encode("utf-8"))}


def create_path(scope: str, raw_path: str, kind: str) -> dict[str, Any]:
    if kind not in ("file", "dir"):
        raise FileOpError("kind must be 'file' or 'dir'")
    path, relative = _resolve(scope, raw_path)
    if path.exists():
        raise FileOpError("path already exists", status=409)
    if _is_sensitive(path):
        raise FileOpError("sensitive file creation is disabled", status=403)
    if kind == "dir":
        path.mkdir(parents=True, exist_ok=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return {"ok": True, "scope": scope, "path": relative.as_posix(), "kind": kind}


def rename_path(scope: str, raw_path: str, to: str) -> dict[str, Any]:
    src, _ = _resolve(scope, raw_path)
    dst, dst_rel = _resolve(scope, to)
    if not src.exists():
        raise FileOpError("source does not exist", status=404)
    if dst.exists():
        raise FileOpError("destination already exists", status=409)
    if _is_sensitive(src) or _is_sensitive(dst):
        raise FileOpError("sensitive file rename is disabled", status=403)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return {"ok": True, "scope": scope, "path": dst_rel.as_posix()}


def delete_path(scope: str, raw_path: str) -> dict[str, Any]:
    path, relative = _resolve(scope, raw_path)
    if relative == Path("."):
        raise FileOpError("refusing to delete the root")
    if not path.exists():
        raise FileOpError("path does not exist", status=404)
    if _is_sensitive(path):
        raise FileOpError("sensitive file deletion is disabled", status=403)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    return {"ok": True, "scope": scope, "path": relative.as_posix()}


# ── diff baseline ─────────────────────────────────────────────────────────────────
def snapshot_baseline(scope: str = "workspace") -> dict[str, str]:
    """Capture {relpath: content} for every editable text file under the scope root.

    Called at run start so ``compute_diffs`` can show exactly what the agent changed. Binary,
    oversized, sensitive, and ignored-dir files are skipped — they are not things we diff.
    """
    root = root_for_scope(scope)
    baseline: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if len(baseline) >= MAX_BASELINE_FILES:
            break
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts) or _is_sensitive(path):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            baseline[relative.as_posix()] = _decode(path.read_bytes())
        except (OSError, FileOpError):
            continue
    return baseline


def _current_text(scope: str, relative: str) -> str | None:
    try:
        path, _ = _resolve(scope, relative)
    except FileOpError:
        return None
    if not path.is_file() or path.is_symlink():
        return None
    try:
        return _decode(path.read_bytes())
    except (OSError, FileOpError):
        return None


def compute_diffs(baseline: dict[str, str], scope: str = "workspace") -> list[dict[str, Any]]:
    """Unified diffs of baseline-vs-current for every path that changed (added/modified/deleted)."""
    root = root_for_scope(scope)
    current: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if len(current) >= MAX_BASELINE_FILES:
            break
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts) or _is_sensitive(path):
            continue
        text = _current_text(scope, relative.as_posix())
        if text is not None:
            current[relative.as_posix()] = text

    diffs: list[dict[str, Any]] = []
    for rel in sorted(set(baseline) | set(current)):
        before = baseline.get(rel)
        after = current.get(rel)
        if before == after:
            continue
        status = "added" if before is None else "deleted" if after is None else "modified"
        before_lines = (before or "").splitlines(keepends=True)
        after_lines = (after or "").splitlines(keepends=True)
        unified = "".join(
            difflib.unified_diff(before_lines, after_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}")
        )
        additions = sum(1 for line in unified.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in unified.splitlines() if line.startswith("-") and not line.startswith("---"))
        diffs.append(
            {"path": rel, "status": status, "additions": additions, "deletions": deletions, "diff": unified}
        )
    return diffs


# ── language hint (drives the CodeMirror mode in the UI) ──────────────────────────
_LANG_BY_SUFFIX = {
    "py": "python",
    "pyi": "python",
    "js": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "jsx": "javascript",
    "ts": "javascript",
    "tsx": "javascript",
    "json": "json",
    "md": "markdown",
    "markdown": "markdown",
}


def _language_for(name: str) -> str:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _LANG_BY_SUFFIX.get(suffix, "text")
