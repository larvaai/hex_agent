"""AgentRunner — drive a real agent run for one IDE session and frame it as loop.* events.

``SubmitPrompt`` lands here. The runner is the only component that knows a run's *boundaries*, so it
owns the lifecycle events the bridge can't: it opens with ``loop.team_composed`` +
``loop.decision`` (the agent node appears and goes *running*), lets the bridge stream each
``loop.tool`` as the agent works, and closes with ``loop.turn`` (node → *done*) + ``loop.finished``
or ``loop.failed``. That ordering is exactly what ``build_snapshot`` folds into a correct graph.

It also snapshots the workspace file *baseline* before the agent touches anything, so the diff
endpoint can show precisely what changed. The run executes on a daemon thread — the HTTP command
returns its ack immediately while the agent works; the held-open SSE stream delivers the progress.

The LLM is optional: if the local model endpoint is down, ``orchestrator.run`` returns a structured
error outcome rather than raising, and the runner reports it as ``loop.failed`` — an honest IDE
shows the failure instead of hanging.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any

from control.events import Actor

from . import files
from .bridge import KernelEventBridge
from .session import IdeSession

_AGENT_ID = "agent:root"


_MAX_CHAT_CHARS = 20_000  # cap a chat bubble's text (the prompt is already capped server-side)


class RunCancelled(BaseException):
    """Raised at the ``execute_tool`` chokepoint when the user stops a run. It subclasses
    ``BaseException`` *on purpose*: every layer on the path home — Retry, the kernel's
    ``execute_tool`` boundary, and ``orchestrator._stream`` — guards with ``except Exception``, which
    would otherwise swallow a cancel and convert it into an ordinary tool-error envelope (the run
    would limp on). As a ``BaseException`` it slips past all of them and reaches ``_run``'s
    ``except RunCancelled``, which reports a clean ``loop.failed`` (cancelled) + ``chat.error``."""

# Arg hints for the tools an IDE agent actually reaches for. The registry only knows tool *names*
# (no schema), and a local model that isn't told the exact name + args guesses "write_file" /
# "file_editor" and fails the call — so we spell them out. Paths are workspace-relative.
_TOOL_HINTS: dict[str, str] = {
    "fs_write": '{"path":"<rel>","content":"<text>"} — create or overwrite a file',
    "fs_read": '{"path":"<rel>"} — read a file',
    "fs_str_replace": '{"path":"<rel>","old_text":"<exact>","new_text":"<new>","expected_replacements":1} — surgical edit',
    "fs_insert": '{"path":"<rel>","line":<1-based>,"content":"<text>"} — insert before a line',
    "fs_write_lines": '{"path":"<rel>","lines":["..."],"overwrite":true} — write a file from a list of lines',
    "fs_list": '{"path":"<rel>"} — list a directory',
    "terminal_run": '{"argv":["cmd","arg"],"timeout":10} — run a command in the workspace',
}


def _tool_guide(kernel) -> str:
    """Build a system-prompt tool catalog from the *live* registry so the names are always correct."""
    names = [
        t["name"]
        for t in kernel.registry.list_tools()
        if not str(t["name"]).startswith("llm.") and t["name"] not in {"echo", "null_tool"}
    ]
    detailed = [f'- {n}  {_TOOL_HINTS[n]}' for n in names if n in _TOOL_HINTS]
    others = [n for n in names if n not in _TOOL_HINTS]
    lines = ["Available tools — call by EXACT name (do NOT invent names like 'write_file'):", *detailed]
    if others:
        lines.append("- other tools: " + ", ".join(sorted(others)))
    lines.append("Paths are relative to the workspace root. To edit a file, use fs_write/fs_str_replace.")
    return "\n".join(lines)


class AgentRunner:
    def __init__(self, session: IdeSession) -> None:
        self.session = session
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    def cancel(self) -> bool:
        """Request the running agent stop. Cooperative: the cancel middleware raises at the next
        tool/LLM chokepoint, so the run aborts within one step (an in-flight LLM call finishes
        first). Returns True if a run was actually active to cancel. ``run_status`` is read through
        the session's own lock (``snapshot_status``) so this never races the runner thread's write."""
        if self.session.snapshot_status() != "running":
            return False
        self._cancel.set()
        return True

    def start(self, prompt: str, system_prompt: str | None = None) -> str | None:
        """Snapshot the baseline, emit the opening events, and run the agent on a daemon thread.

        Returns the run_id, or ``None`` if a run is already active — starting a second run would
        clobber the diff baseline and interleave two runs' events. The check-and-claim is atomic
        under ``self._lock`` so two concurrent SubmitPrompts cannot both pass it."""
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        # Snapshot the baseline before claiming (it walks the workspace); the atomic claim lives in
        # the session under its own lock, so two concurrent SubmitPrompts cannot both win.
        baseline = files.snapshot_baseline("workspace")
        with self._lock:
            if not self.session.try_begin_run(prompt, baseline, "workspace"):
                return None
            self._cancel.clear()
        # chat.user first so the conversation thread (ordered by seq) opens with the prompt.
        self.session.emit("chat.user", {"text": prompt[:_MAX_CHAT_CHARS]})
        self.session.emit("loop.team_composed", {"selected": [_AGENT_ID]})
        self.session.emit(
            "loop.decision",
            {
                "decision": "dispatch",
                "reason": prompt[:300],
                "round": 1,
                "next_agent_calls": [{"agent_id": _AGENT_ID, "objective": prompt[:300], "target_kind": "agent"}],
            },
            round_no=1,
        )
        thread = threading.Thread(
            target=self._run, args=(run_id, prompt, system_prompt), name=f"ide-run-{run_id}", daemon=True
        )
        thread.start()
        return run_id

    def _run(self, run_id: str, prompt: str, system_prompt: str | None) -> None:
        # Imports are deferred so the file API works even if the agent stack (langgraph/openai)
        # is not installed — file editing must not depend on the runtime being importable.
        from core.bootstrap import create_kernel
        from delegation.bootstrap import create_delegation_service
        from observability import EventLogger, attach_to_bus
        from orchestrator import run as run_agent
        from orchestrator.loop import DEFAULT_SYSTEM

        bridge = KernelEventBridge(self.session)
        outcome: dict[str, Any]
        try:
            kernel = create_kernel()
            # Cooperative cancel: this middleware sits on the single execute_tool chokepoint and
            # raises once the user hits Stop. Registered before run_agent freezes the kernel.
            def _cancel_mw(request, nxt):  # noqa: ANN001 — middleware signature is (request, nxt)
                if self._cancel.is_set():
                    raise RunCancelled()
                return nxt(request)

            try:
                kernel.use(_cancel_mw)
            except RuntimeError:
                pass  # already frozen (not expected pre-run) — Stop degrades to a no-op
            kernel.events.subscribe(bridge.subscriber)
            attach_to_bus(EventLogger(run_id=run_id), kernel.events)  # persist to var/agent_runs too
            delegation_service = create_delegation_service(kernel)
            full_system = (system_prompt or DEFAULT_SYSTEM) + "\n\n" + _tool_guide(kernel)
            outcome = run_agent(
                kernel,
                prompt,
                system_prompt=full_system,
                run_id=run_id,
                checkpoint=True,
                delegation_service=delegation_service,
            )
        except RunCancelled:
            self._finish_cancelled()
            return
        except Exception as exc:  # the run stack itself failed (import/bootstrap) — report honestly
            self._finish_failed(f"{type(exc).__name__}: {exc}")
            return

        if self._cancel.is_set():  # cancel landed as the run wound down — report it as cancelled
            self._finish_cancelled()
            return
        status = str(outcome.get("status") or "completed")
        result = outcome.get("result")
        summary = _stringify(result)
        if status in ("failed", "error"):
            self._finish_failed(summary or status)
            return
        self.session.emit(
            "loop.turn",
            {"agent_id": _AGENT_ID, "outcome": summary[:500], "round": 1},
            actor=Actor(type="agent", id=_AGENT_ID),
            round_no=1,
        )
        self.session.emit("loop.finished", {"status": status, "result": summary[:1000]})
        self.session.emit("chat.assistant", {"text": summary[:_MAX_CHAT_CHARS]})
        self.session.set_status("finished")

    def _finish_failed(self, message: str) -> None:
        self.session.emit(
            "loop.turn",
            {"agent_id": _AGENT_ID, "outcome": f"(failed) {message}"[:500], "round": 1},
            actor=Actor(type="agent", id=_AGENT_ID),
            round_no=1,
        )
        self.session.emit("loop.failed", {"error": message[:1000]})
        self.session.emit("chat.error", {"text": message[:_MAX_CHAT_CHARS]})
        self.session.set_status("failed")

    def _finish_cancelled(self) -> None:
        message = "Run stopped by user."
        self.session.emit(
            "loop.turn",
            {"agent_id": _AGENT_ID, "outcome": f"(cancelled) {message}", "round": 1},
            actor=Actor(type="agent", id=_AGENT_ID),
            round_no=1,
        )
        self.session.emit("loop.failed", {"error": message, "cancelled": True})
        self.session.emit("chat.error", {"text": message, "cancelled": True})
        self.session.set_status("cancelled")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    import json

    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)
