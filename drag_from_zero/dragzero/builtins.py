"""Built-in hook and routing-rule catalogs the topology references by name.

A drag-drop palette: a Hook node names one of `BUILTIN_HOOKS`; a Router node
names one of `BUILTIN_RULES` (a factory taking the node's `config`). Users can
pass their own catalogs to `build_runtime` to extend the palette.
"""
from __future__ import annotations

from typing import Callable, Optional


# --- hooks: name -> fn(ctx) -> Optional[block_reason] ---
def _deny_delegation(ctx) -> Optional[str]:
    return "policy: delegation disabled"


def _deny_all(ctx) -> Optional[str]:
    return "policy: blocked by hook"


BUILTIN_HOOKS: dict = {
    "deny_delegation": _deny_delegation,
    "deny_all": _deny_all,
}


# --- rules: name -> factory(config) -> rule(task) -> Optional[role_or_id] ---
def _by_keyword(config: dict) -> Callable:
    keyword = str(config.get("keyword", "")).lower()
    role = config.get("role")

    def rule(task):
        if role and keyword and keyword in task.description.lower():
            return role
        return None

    return rule


def _always(config: dict) -> Callable:
    role = config.get("role")
    return lambda task: role


BUILTIN_RULES: dict = {
    "by_keyword": _by_keyword,
    "always": _always,
}
