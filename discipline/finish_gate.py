"""Finish gate — block a final when code changed but no validation passed. Epic E02."""
from __future__ import annotations

from typing import Any


def requires_validation(state: dict[str, Any]) -> bool:
    return bool(state.get("code_changed"))


def has_passing_validation(state: dict[str, Any]) -> bool:
    return bool(state.get("validation_passed"))


def check_finish(state: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    """Block a `final` when code changed but no validation passed (unless a blocker is declared)."""
    if requires_validation(state) and not has_passing_validation(state) and finish_reason != "blocker":
        return {
            "allowed": False,
            "reason": "Code changed but no passing validation. Validate or finish with finish_reason='blocker'.",
        }
    return {"allowed": True, "reason": ""}
