"""Safety chokepoint — policy check + SafeToolPort wrapper applied to every toolbox tool. Epic E06."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from core.schemas import ToolRequest

SHELL_EXES = {"bash", "sh", "zsh", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh"}
SHELL_TOKENS = ("|", "&", ";", ">", "<", "`", "$(", "&&", "||")
DESTRUCTIVE_EXES = {"rm", "del", "rmdir", "format", "mkfs", "dd"}
GIT_MUTATIONS = {"add", "commit", "reset", "checkout", "rebase", "push", "merge", "branch", "stash"}


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
    return PolicyDecision(True, risk="low")


class ToolPolicy:
    """The single cross-cutting safety gate. Extend here, not per-server."""

    def check(self, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
        if tool_name in {"terminal_run", "terminal.run", "terminal"}:
            return classify_terminal(args.get("argv"))
        if any(m in tool_name for m in ("git_commit", "git_add", "git_reset", "git_checkout", "git_push")) and not _truthy(
            "AGENT_ALLOW_GIT_MUTATIONS"
        ):
            return PolicyDecision(False, f"git mutation tool '{tool_name}' blocked", "git_mutation", "blocked")
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
