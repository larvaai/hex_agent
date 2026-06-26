"""Shared tool-catalog builder for agent system prompts.

The registry knows tool *names* but carries no schema, so a local model that isn't told the exact
name + args invents ``write_file`` / ``bash`` and the call fails ("Capability outside session scope").
This spells out the args for the tools an agent actually reaches for, built from the LIVE registry so
the names are always correct.

Both the IDE root prompt (``ui/ide/runner.py``) and every delegated child agent
(``adapters/agents/langgraph_agent.py``) compose this — a delegated agent that ran with the bare
DEFAULT/COMPAT prompt got no catalog and invented tool names. Keep this the single source of truth.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.kernel import AgentKernel

# Arg hints for the tools an agent actually reaches for. Paths are workspace-relative.
TOOL_HINTS: dict[str, str] = {
    "fs_write": '{"path":"<rel>","content":"<text>"} — create or overwrite a file',
    "fs_read": '{"path":"<rel>"} — read a file',
    "fs_str_replace": '{"path":"<rel>","old_text":"<exact>","new_text":"<new>","expected_replacements":1} — surgical edit',
    "fs_insert": '{"path":"<rel>","line":<1-based>,"content":"<text>"} — insert before a line',
    "fs_write_lines": '{"path":"<rel>","lines":["..."],"overwrite":true} — write a file from a list of lines',
    "fs_list": '{"path":"<rel>"} — list a directory',
    "terminal_run": '{"argv":["cmd","arg"],"timeout":10} — run a command in the workspace',
}


def tool_guide(kernel: "AgentKernel") -> str:
    """Build a system-prompt tool catalog from the *live* registry so the names are always correct."""
    names = [
        t["name"]
        for t in kernel.registry.list_tools()
        if not str(t["name"]).startswith("llm.") and t["name"] not in {"echo", "null_tool"}
    ]
    detailed = [f"- {n}  {TOOL_HINTS[n]}" for n in names if n in TOOL_HINTS]
    others = [n for n in names if n not in TOOL_HINTS]
    lines = ["Available tools — call by EXACT name (do NOT invent names like 'write_file'):", *detailed]
    if others:
        lines.append("- other tools: " + ", ".join(sorted(others)))
    lines.append("Paths are relative to the workspace root. To edit a file, use fs_write/fs_str_replace.")
    return "\n".join(lines)
