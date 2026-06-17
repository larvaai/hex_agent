"""AgentState for the single-agent graph loop (reused by multi-agent later). Epic E05."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    task: str
    messages: list[dict[str, str]] = field(default_factory=list)
    step: int = 0
    final: str | None = None
    last_action: dict[str, Any] | None = None
    # set by tools/roles later; consulted by the finish gate (E02)
    code_changed: bool = False
    validation_passed: bool = False
