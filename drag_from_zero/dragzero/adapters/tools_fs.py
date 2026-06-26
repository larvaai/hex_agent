"""Filesystem-sandboxed tools (a side-effecting adapter).

`FsSandbox` confines every path to a root directory — `..` escapes raise
`SandboxError`. The tools wrap sandbox ops and always return a `ToolResult`
(never raise), so a bad call is an observable `tool_result` event, not a crash.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..registries import ToolRegistry
from ..tools import SandboxError, ToolResult


class FsSandbox:
    def __init__(self, root) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise SandboxError(f"path escapes sandbox: {rel!r}")
        return p

    def read(self, rel: str) -> str:
        return self.resolve(rel).read_text()

    def write(self, rel: str, content: str) -> int:
        p = self.resolve(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return len(content)

    def listdir(self, rel: str = ".") -> list:
        return sorted(x.name for x in self.resolve(rel).iterdir())

    def run_command(self, argv: list, timeout: float = 30.0):
        proc = subprocess.run(argv, cwd=str(self.root), capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr)


class ReadFileTool:
    name = "read_file"

    def run(self, args: dict, sandbox) -> ToolResult:
        try:
            return ToolResult(True, sandbox.read(args["path"]))
        except SandboxError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"{type(e).__name__}: {e}")


class WriteFileTool:
    name = "write_file"

    def run(self, args: dict, sandbox) -> ToolResult:
        try:
            n = sandbox.write(args["path"], args.get("content", ""))
            return ToolResult(True, f"wrote {n} bytes to {args['path']}")
        except SandboxError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"{type(e).__name__}: {e}")


class ListDirTool:
    name = "list_dir"

    def run(self, args: dict, sandbox) -> ToolResult:
        try:
            return ToolResult(True, "\n".join(sandbox.listdir(args.get("path", "."))))
        except SandboxError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"{type(e).__name__}: {e}")


class RunCommandTool:
    """Run a command inside the sandbox root. Powerful — register only when wanted."""

    name = "run_command"

    def run(self, args: dict, sandbox) -> ToolResult:
        argv = args.get("argv")
        if not isinstance(argv, list) or not argv:
            return ToolResult(False, "", "run_command needs a non-empty 'argv' list")
        try:
            rc, out = sandbox.run_command(argv, timeout=args.get("timeout", 30.0))
            return ToolResult(rc == 0, out, "" if rc == 0 else f"exit code {rc}")
        except Exception as e:
            return ToolResult(False, "", f"{type(e).__name__}: {e}")


def build_fs_tools(registry: ToolRegistry = None, include_run_command: bool = False) -> ToolRegistry:
    registry = registry or ToolRegistry()
    for tool in (ReadFileTool(), WriteFileTool(), ListDirTool()):
        registry.register(tool)
    if include_run_command:
        registry.register(RunCommandTool())
    return registry


def default_tool_catalog(include_run_command: bool = False) -> dict:
    """name -> Tool, for topology tool nodes to reference by name."""
    catalog = {t.name: t for t in (ReadFileTool(), WriteFileTool(), ListDirTool())}
    if include_run_command:
        rc = RunCommandTool()
        catalog[rc.name] = rc
    return catalog
