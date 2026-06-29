"""ToolMiddleware protocol — pre/post hook around execute_tool. Epic E01/E06."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from core.schemas import ToolRequest

ToolHandler = Callable[[ToolRequest], dict[str, Any]]


class ToolMiddleware(Protocol):
    """Receives the request and `nxt` (the inner handler). May act before/after,
    short-circuit (return without calling nxt), or modify the result envelope.

    Failure posture (read by the kernel, optional attribute — Protocol is structural, so it is
    not enforced here): a middleware MAY declare ``fail_open = True`` to mark itself **advisory**
    (telemetry/condense). If a fail-open middleware raises, the kernel SKIPS it and continues with
    the inner result instead of failing the call. Absent/False (the default) = **blocking**: a
    raise propagates to the kernel boundary as ok=False. Leave it unset for any gate/guard.
    (Optional by convention — read via getattr, never required; Protocol stays structural.)"""

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
