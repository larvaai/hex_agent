"""Workspace-sandboxed filesystem tools: fs_read, fs_write, fs_list. Epic E06."""
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
        return {"ok": True, "path": str(path), "content": path.read_text(encoding="utf-8")}


class FsWrite:
    name = "fs_write"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        try:
            path = resolve_in_workspace(str(request.args.get("path", "")))
        except SandboxError as exc:
            return {"ok": False, "error": str(exc)}
        content = str(request.args.get("content", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": len(content)}


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
