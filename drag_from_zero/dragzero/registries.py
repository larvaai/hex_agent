"""Empty-by-default gates. The harness ships the cổng, not the luật.

Every registry is inert until something is registered, so default behaviour is
pure pass-through. Budget is a counter that stays disabled until a limit is set.
"""
from __future__ import annotations

from typing import Callable, Optional


class HookRegistry:
    """Hooks per phase. check() returns the first block reason, or None (pass-through)."""

    def __init__(self) -> None:
        self._hooks: list[tuple[str, Callable[[dict], Optional[str]]]] = []

    def register(self, phase: str, fn: Callable[[dict], Optional[str]]) -> None:
        self._hooks.append((phase, fn))

    def check(self, phase: str, ctx: dict) -> Optional[str]:
        for p, fn in self._hooks:
            if p == phase:
                reason = fn(ctx)
                if reason:
                    return reason
        return None


class RuleRegistry:
    """Routing rules. route() returns an agent id, or None (fall back to default routing)."""

    def __init__(self) -> None:
        self._rules: list[Callable[[object], Optional[str]]] = []

    def add(self, fn: Callable[[object], Optional[str]]) -> None:
        self._rules.append(fn)

    def route(self, task) -> Optional[str]:
        for fn in self._rules:
            aid = fn(task)
            if aid:
                return aid
        return None


class ToolRegistry:
    """Tools registered at runtime, keyed by ``tool.name``. Empty by default."""

    def __init__(self) -> None:
        self._tools: dict = {}

    def register(self, tool):
        """Register a Tool (anything with a ``.name`` and ``.run(args, sandbox)``)."""
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str):
        return self._tools.get(name)

    def names(self) -> list:
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)


class Budget:
    """Counter, disabled until a limit is set. Halts a run when the limit is reached."""

    def __init__(self, limit: Optional[int] = None) -> None:
        self.limit = limit
        self.used = 0

    @property
    def enabled(self) -> bool:
        return self.limit is not None

    def charge(self, n: int = 1) -> bool:
        """Return False (do not spend) when the charge would exceed the limit."""
        if self.enabled and self.used + n > self.limit:
            return False
        self.used += n
        return True
