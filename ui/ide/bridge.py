"""KernelEventBridge — translate the kernel's EventBus topics into control-plane loop.* events.

The single-agent kernel publishes ``tool.requested`` / ``tool.completed`` / ``tool.failed`` (and
``graph.parse_error``) on its EventBus — it does *not* speak the supervisor's ``loop.*`` vocabulary
that ``build_snapshot`` folds. This bridge is the adapter between the two so the existing Graph and
Timeline light up for a real run with zero UI changes.

It deliberately emits **only event types the UI adapter already listens for** (``loop.tool`` /
``loop.parse_error``); the run *boundaries* (``loop.team_composed`` → ``loop.turn`` → ``loop.finished``)
are emitted by the runner, which alone knows when a run starts and ends. That split keeps the agent
node's lifecycle correct: a ``loop.turn`` marks the node *done*, so it must fire once at the end, not
on every tool call.

``tool.completed`` carries no args (only ``tool.requested`` does), so the bridge correlates the two by
``request_id`` to lift the file ``path`` onto the completion event — that path is what turns the
timeline from "fs_write ✓" into "fs_write ✓ · src/app.py", the detail an IDE user actually wants.
"""
from __future__ import annotations

import threading
from typing import Any

from control.events import Actor

from .session import IdeSession

# fs tools carry the edited path in args["path"]; surfacing it makes the timeline legible.
_PATH_ARG_KEYS = ("path",)
_MAX_PENDING = 1_024  # bound the requested→completed correlation map against orphaned requests


class KernelEventBridge:
    def __init__(self, session: IdeSession) -> None:
        self.session = session
        self._lock = threading.Lock()
        self._pending: dict[str, dict[str, Any]] = {}  # request_id -> {tool, path}

    def subscriber(self, topic: str, payload: dict[str, Any]) -> None:
        """Attach via ``kernel.events.subscribe(bridge.subscriber)``. Never raises (the bus swallows
        exceptions, but we keep it defensive so a bad event can't poison the run)."""
        try:
            self._handle(topic, payload)
        except Exception:
            pass

    def _handle(self, topic: str, payload: dict[str, Any]) -> None:
        if topic == "tool.requested":
            request_id = str(payload.get("request_id") or "")
            if request_id:
                with self._lock:
                    self._pending[request_id] = {
                        "tool": str(payload.get("tool") or ""),
                        "path": _extract_path(payload.get("args")),
                    }
                    # A tool that never reports completion would orphan its entry — evict oldest.
                    if len(self._pending) > _MAX_PENDING:
                        del self._pending[next(iter(self._pending))]
            return

        if topic in ("tool.completed", "tool.failed"):
            request_id = str(payload.get("request_id") or "")
            with self._lock:
                meta = self._pending.pop(request_id, {})
            tool = str(payload.get("tool") or meta.get("tool") or "")
            ok = bool(payload.get("ok")) if topic == "tool.completed" else False
            ui_payload: dict[str, Any] = {
                "tool": tool,
                "ok": ok,
                "status": "ok" if ok else "failed",
            }
            path = meta.get("path")
            if path:
                ui_payload["path"] = path
            error = payload.get("error")
            if error and not ok:
                ui_payload["error"] = str(error)[:300]
            actor_id = str(payload.get("actor_id") or "agent:root")
            self.session.emit("loop.tool", ui_payload, actor=Actor(type="agent", id=actor_id))
            return

        if topic == "graph.parse_error":
            self.session.emit(
                "loop.parse_error",
                {"detail": str(payload.get("error") or payload.get("detail") or "parse error")[:300]},
            )


def _extract_path(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    for key in _PATH_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
