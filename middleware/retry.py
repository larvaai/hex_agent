"""Retry — re-invoke the inner handler on a non-ok result. Epic E06 / E10 S10.13.

Never retries a policy block, nor a non-idempotent side-effecting capability
(``kind == "effect"`` and ``idempotent is False``) — re-running an effect could
double-apply it. Read/model/idempotent capabilities may be retried.
"""
from __future__ import annotations

from typing import Any

from core.schemas import ToolRequest


def _retryable(env: dict[str, Any]) -> bool:
    meta = env.get("metadata") or {}
    if meta.get("policy_block"):
        return False
    if meta.get("kind") == "effect" and meta.get("idempotent") is False:
        return False
    return True


class Retry:
    def __init__(self, *, attempts: int = 2) -> None:
        self.attempts = max(1, attempts)

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts and _retryable(env):
            env = nxt(request)
            tries += 1
        return env
