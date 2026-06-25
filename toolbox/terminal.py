"""Terminal tool — run an argv (no shell) inside the workspace with a timeout. Policy gates danger. Epic E06."""
from __future__ import annotations

import subprocess
from typing import Any

from core.schemas import ToolRequest
from safety.policy import classify_terminal
from safety.sandbox import workspace_dir


class Terminal:
    name = "terminal_run"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        argv = request.args.get("argv")
        if not isinstance(argv, list) or not argv:
            return {"ok": False, "error": "argv must be a non-empty list"}
        # Enforce the safety policy in the tool itself, not only in the SafeToolPort wrapper,
        # so a direct invocation cannot bypass the chokepoint (defense in depth).
        decision = classify_terminal(argv)
        if not decision.allowed:
            return {
                "ok": False,
                "error": decision.reason,
                "policy_blocked": True,
                "policy_code": decision.code,
            }
        timeout = min(max(int(request.args.get("timeout", 10)), 1), 30)
        cwd = workspace_dir()
        cwd.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                [str(a) for a in argv],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            return {"ok": False, "error": f"command not found: {exc}"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"timeout after {timeout}s"}
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
