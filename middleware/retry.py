"""Retry — re-invoke the inner handler on a non-ok result (never on a policy block). Epic E06."""
from __future__ import annotations

from typing import Any

from core.schemas import ToolRequest


class Retry:
    def __init__(self, *, attempts: int = 2) -> None:
        self.attempts = max(1, attempts)

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while (isinstance(env, dict) and not env.get("ok") and tries < self.attempts
               and not (env.get("metadata") or {}).get("policy_block")):
            env = nxt(request)
            tries += 1
        return env
