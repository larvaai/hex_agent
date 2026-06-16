"""Condense large tool results before re-feeding them to the model. Epic E02."""
from __future__ import annotations

from typing import Any


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [+{len(text) - max_chars} chars]"


def condense(value: Any, *, max_chars: int = 2000, max_list: int = 10) -> Any:
    """Shrink a tool result before re-feeding it to the model."""
    if isinstance(value, dict):
        return {k: condense(v, max_chars=max_chars, max_list=max_list) for k, v in value.items()}
    if isinstance(value, list):
        head = [condense(v, max_chars=max_chars, max_list=max_list) for v in value[:max_list]]
        if len(value) > max_list:
            head.append(f"... [+{len(value) - max_list} items]")
        return head
    if isinstance(value, str):
        return _truncate(value, max_chars)
    return value
