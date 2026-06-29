"""Tool port — the contract the orchestrator runs tools through.

Concrete, side-effecting tools (filesystem, commands) live in ``adapters/``; the
orchestrator depends only on these abstractions, never on a real filesystem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SandboxError(Exception):
    """A tool tried to act outside the sandbox boundary."""


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: str = ""


class Tool(Protocol):
    name: str

    def run(self, args: dict, sandbox) -> ToolResult:
        ...
