"""A declarative eval scenario: a task, the available roles, and a rubric."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Scenario:
    name: str
    task: str
    roles: list           # role names available in the roster
    scorers: list         # list of scorer callables (ctx -> ScoreResult)
    entry_role: Optional[str] = None  # role the root is routed to (default roles[0])
    trials: int = 1
    tools: list = field(default_factory=list)        # Tool objects to register
    sandbox_factory: Optional[Callable] = None        # () -> sandbox (fresh per trial)
