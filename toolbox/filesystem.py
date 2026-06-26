"""Workspace-sandboxed filesystem tools: fs_read, fs_write, fs_list + surgical editors. Epic E06.

Beyond whole-file ``fs_write`` this module adds *patch* primitives — ``fs_str_replace``
(count-guarded), ``fs_insert`` (before a 1-based line), ``fs_write_lines`` (from a JSON
list) — so an edit can be scoped instead of clobbering the file. These are exactly the
patch tools ``safety.policy`` steers toward in repair mode.
"""
from __future__ import annotations

from typing import Any

from core.schemas import ToolRequest
from safety.sandbox import SandboxError, resolve_in_workspace


class FsRead:
    name = "fs_read"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        try:
            path = resolve_in_workspace(str(request.args.get("path", "")))
        except SandboxError as exc:
            return {"ok": False, "error": str(exc)}
        if not path.is_file():
            return {"ok": False, "error": f"Not a file: {path}"}
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": f"File is not valid UTF-8 text: {path}"}
        return {"ok": True, "path": str(path), "content": content}


class FsWrite:
    name = "fs_write"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        try:
            path = resolve_in_workspace(str(request.args.get("path", "")))
        except SandboxError as exc:
            return {"ok": False, "error": str(exc)}
        content = str(request.args.get("content", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": len(encoded)}


class FsList:
    name = "fs_list"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        try:
            path = resolve_in_workspace(str(request.args.get("path", ".")))
        except SandboxError as exc:
            return {"ok": False, "error": str(exc)}
        if not path.exists():
            return {"ok": True, "entries": []}
        if path.is_file():
            return {"ok": True, "entries": [path.name]}
        return {"ok": True, "entries": sorted(p.name for p in path.iterdir())}


def _resolve_existing_file(raw: Any) -> tuple[Any, str | None]:
    """Resolve a workspace path that must be an existing file. Returns (path, error)."""
    try:
        path = resolve_in_workspace(str(raw or ""))
    except (SandboxError, ValueError) as exc:
        # ValueError covers Path.resolve() rejecting an embedded NUL byte before any file op.
        return None, str(exc)
    if not path.exists():
        return None, f"File does not exist: {path}"
    if not path.is_file():
        return None, f"Not a file: {path}"
    return path, None


class FsStrReplace:
    """Replace exact text, refusing when the occurrence count does not match expectations."""

    name = "fs_str_replace"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        old_text = str(request.args.get("old_text", ""))
        if not old_text:
            return {"ok": False, "error": "old_text is required"}
        new_text = str(request.args.get("new_text", ""))
        try:
            expected = max(1, int(request.args.get("expected_replacements", 1)))
        except (TypeError, ValueError):
            expected = 1
        path, error = _resolve_existing_file(request.args.get("path"))
        if error:
            return {"ok": False, "error": error}
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": f"File is not valid UTF-8 text: {path}"}
        found = text.count(old_text)
        if found != expected:
            return {
                "ok": False,
                "error": "Replacement count mismatch; refusing edit to avoid an ambiguous or broad change.",
                "found_replacements": found,
                "expected_replacements": expected,
            }
        updated = text.replace(old_text, new_text, expected)
        path.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": str(path), "replacements": expected, "bytes": len(updated.encode("utf-8"))}


class FsInsert:
    """Insert text before a 1-based line; use line == total_lines + 1 to append."""

    name = "fs_insert"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        path, error = _resolve_existing_file(request.args.get("path"))
        if error:
            return {"ok": False, "error": error}
        try:
            line = int(request.args.get("line", 0))
        except (TypeError, ValueError):
            return {"ok": False, "error": "line must be an integer"}
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": f"File is not valid UTF-8 text: {path}"}
        lines = text.splitlines(keepends=True)
        if line < 1 or line > len(lines) + 1:
            return {"ok": False, "error": "line is outside valid insert range", "valid_range": [1, len(lines) + 1]}
        content = str(request.args.get("content", ""))
        if content and not content.endswith("\n"):
            content += "\n"
        lines.insert(line - 1, content)
        updated = "".join(lines)
        path.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": str(path), "line": line, "bytes": len(updated.encode("utf-8"))}


class FsWriteLines:
    """Create/overwrite a file from a JSON list of lines (avoids fragile multiline payloads)."""

    name = "fs_write_lines"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        raw_lines = request.args.get("lines")
        if not isinstance(raw_lines, list):
            return {"ok": False, "error": "lines must be a list of strings"}
        try:
            path = resolve_in_workspace(str(request.args.get("path", "")))
        except (SandboxError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        overwrite = bool(request.args.get("overwrite", False))
        if path.exists() and not overwrite:
            return {"ok": False, "error": "File exists and overwrite is false."}
        normalized: list[str] = []
        for item in raw_lines:
            if not isinstance(item, str):
                return {"ok": False, "error": "Every item in lines must be a string."}
            normalized.extend(item.splitlines() or [""])
        content = "\n".join(normalized)
        if bool(request.args.get("trailing_newline", True)):
            content += "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(path), "lines_written": len(normalized), "bytes": len(content.encode("utf-8"))}
