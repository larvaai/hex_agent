"""Safety chokepoint — policy check + SafeToolPort wrapper applied to every toolbox tool. Epic E06."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.schemas import ToolRequest
from safety.sandbox import workspace_dir

SHELL_EXES = {"bash", "sh", "zsh", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh"}
SHELL_TOKENS = ("|", "&", ";", ">", "<", "`", "$(", "&&", "||")
DESTRUCTIVE_EXES = {"rm", "del", "rmdir", "format", "mkfs", "dd"}
GIT_MUTATIONS = {"add", "commit", "reset", "checkout", "rebase", "push", "merge", "branch", "stash"}
# Absolute path tokens: Windows drive paths (C:\ or C:/) and POSIX /-rooted paths.
_ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]+[^\s'\"]+|/[^\s'\"]+")


def _argv_escapes_workspace(argv: list) -> bool:
    """True if any *argument* references an absolute path outside the workspace.

    argv[0] (the program — e.g. the python interpreter, legitimately outside the jail)
    is exempt; every later element is scanned so inline code such as ``python -c
    "open('/etc/passwd')"`` cannot read or exfiltrate files outside the workspace.
    """
    workspace = workspace_dir()
    for part in argv[1:]:
        for candidate in _ABS_PATH_RE.findall(str(part)):
            normalized = candidate.replace("\\\\", "\\")  # collapse repr-doubled separators
            try:
                resolved = Path(normalized).resolve()
            except (OSError, ValueError):
                continue
            if resolved != workspace and not resolved.is_relative_to(workspace):
                return True
    return False


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    code: str = ""
    risk: str = "low"


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def classify_terminal(argv: Any) -> PolicyDecision:
    if not isinstance(argv, list) or not argv:
        return PolicyDecision(False, "terminal requires a non-empty argv list", "bad_argv", "blocked")
    exe = str(argv[0]).replace("\\", "/").split("/")[-1].lower()
    if exe in SHELL_EXES:
        return PolicyDecision(False, "shell executables are not allowed; pass argv directly", "shell_exe", "blocked")
    if any(tok in str(part) for part in argv for tok in SHELL_TOKENS):
        return PolicyDecision(False, "shell control/redirection tokens are not allowed", "shell_token", "blocked")
    if exe in DESTRUCTIVE_EXES:
        return PolicyDecision(False, "destructive command blocked", "destructive", "blocked")
    if exe in {"git", "git.exe"} and len(argv) >= 2 and str(argv[1]).lower() in GIT_MUTATIONS and not _truthy(
        "AGENT_ALLOW_GIT_MUTATIONS"
    ):
        return PolicyDecision(False, f"git {argv[1]} blocked (set AGENT_ALLOW_GIT_MUTATIONS=1)", "git_mutation", "blocked")
    if _argv_escapes_workspace(argv):
        return PolicyDecision(
            False, "argv references an absolute path outside the workspace", "path_escape", "blocked"
        )
    return PolicyDecision(True, risk="low")


WHOLE_FILE_WRITES = {"fs_write", "fs.write", "file_write"}


class ToolPolicy:
    """The single cross-cutting safety gate. Extend here, not per-server.

    In ``repair_mode`` (entered after a failed test/validation), a whole-file
    rewrite is refused with ``policy_code=repair_requires_patch_tool`` so a repair
    must be a scoped patch, not a clobbering overwrite (E10 S10.12).
    """

    def __init__(self, *, repair_mode: bool = False) -> None:
        self.repair_mode = repair_mode

    def check(self, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
        if tool_name in {"terminal_run", "terminal.run", "terminal"}:
            return classify_terminal(args.get("argv"))
        if any(m in tool_name for m in ("git_commit", "git_add", "git_reset", "git_checkout", "git_push")) and not _truthy(
            "AGENT_ALLOW_GIT_MUTATIONS"
        ):
            return PolicyDecision(False, f"git mutation tool '{tool_name}' blocked", "git_mutation", "blocked")
        if self.repair_mode and tool_name in WHOLE_FILE_WRITES:
            return PolicyDecision(
                False,
                "in repair mode a whole-file rewrite is blocked; use a patch tool",
                "repair_requires_patch_tool",
                "blocked",
            )
        return PolicyDecision(True)


class SafeToolPort:
    """Wrap a tool executor; run the policy chokepoint before delegating. Epic E06."""

    def __init__(self, name: str, inner: Any, policy: ToolPolicy | None = None) -> None:
        self.name = name
        self._inner = inner
        self._policy = policy or ToolPolicy()

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        decision = self._policy.check(request.name, request.args)
        if not decision.allowed:
            return {
                "ok": False,
                "tool": request.name,
                "policy_blocked": True,
                "policy_code": decision.code,
                "error": decision.reason,
                "metadata": {"risk": decision.risk},
            }
        return self._inner.execute(request)
