"""TimingLog — measure wall-time around a tool call; register outermost. Epic E04."""
from __future__ import annotations

import time
from typing import Any, Callable

from core.schemas import ToolRequest


class TimingLog:
    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        t0 = time.perf_counter()
        env = nxt(request)
        if self.sink:
            self.sink({"tool": request.name, "ok": (env or {}).get("ok"),
                       "ms": round((time.perf_counter() - t0) * 1000, 2)})
        return env
