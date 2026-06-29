#!/usr/bin/env python3
"""memory_gap_hook — opt-in tier-1 memory-gap hook (nudge-class).

A thin, deterministic wrapper around the `memory_gap` detector. It owns NO
detection logic: it imports `memory_gap.collect`, surfaces any signal as an
ADVISORY (stderr), and records one observation in the audit trace — then ALWAYS
allows turn-end. It never blocks and never writes the spec or the decision
register; the LLM acts on the nudge through the existing writers.

Class is `nudge` (default OFF in the taxonomy): the gap funnel is advisory, so
the hook stays asleep until an operator enables it in harness-hooks.yaml. When
enabled it warns + records; it cannot be escalated to blocking by config.

Two events, one file:
  - default          → `Stop`. Runs the detector (behind the touched-flag no-op
    guard), surfaces signals, records an observation.
  - `--post-tool-use`→ `PostToolUse`. Sets an EPHEMERAL, session-keyed
    touched-flag in $TMPDIR (never committed) — the no-op guard's cheap "did
    this session write anything?" signal.

Visible-degradation guarantee: if the detector module chain cannot be imported,
the hook does NOT silently allow (which would make a wired hook look alive while
never firing). It emits a `memory_gap_degraded` audit event first, then allows
— a silent no-op becomes a visible one. The audit write and the advisory are
the only side effects beyond the ephemeral flag.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import hook_runtime  # noqa: E402
import trace_log     # noqa: E402

HOOK_CLASS = "nudge"
NAME = "memory_gap_hook"
ALLOW_EXIT = 0

# Cap how many breach subjects are named in the one-line advisory before the
# tail is summarized — the detector already caps the signal list; this keeps the
# stderr line readable.
_ADVISORY_SUBJECT_CAP = 5


# ---------------------------------------------------------------------------
# Detector import (DRY: reuse memory_gap, never re-implement). Kept as a named
# function so a test can simulate a broken chain and exercise the degraded path.
# ---------------------------------------------------------------------------

def _import_memory_gap():
    """Insert the sibling scripts dir and import the detector. Hook and detector
    ship together (hooks/ <-> scripts/), so the file-relative sibling is the
    durable anchor. Raises ImportError when the chain is incomplete."""
    sd = str(Path(__file__).resolve().parent.parent / "scripts")
    if sd not in sys.path:
        sys.path.insert(0, sd)
    import memory_gap  # noqa: E402 — resolved only after the path insert
    return memory_gap


def _project_dir(stdin_cwd: Optional[str] = None) -> Optional[str]:
    """The project root to scan. CLAUDE_PROJECT_DIR (set by the host) wins; the
    Stop/PostToolUse stdin `cwd` is the fallback. None if neither is usable."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or stdin_cwd
    return root or None


def _enabled() -> bool:
    """Is the hook enabled? A config-read failure falls to the SAFE default for a
    nudge: OFF (do nothing) — never warn on an ambiguous config."""
    try:
        return hook_runtime.hook_enabled(NAME, HOOK_CLASS)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Ephemeral, session-keyed touched-flag ($TMPDIR — not committed).
# ---------------------------------------------------------------------------

def _temp_dir() -> Path:
    """Read $TMPDIR fresh each call (tempfile caches its first read, which breaks
    per-test TMPDIR isolation). Falls back to the stdlib default."""
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir())


def safe_id(session_id: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in (session_id or "_"))


def _flag_path(session_id: str) -> Path:
    return _temp_dir() / ("harness-memgap-touched-%s" % safe_id(session_id))


def set_touched_flag(session_id: str) -> Path:
    """Mark "this session wrote something". Ephemeral; best-effort (a write failure
    must never break the turn — the flag is an optimization)."""
    path = _flag_path(session_id)
    try:
        path.write_text("1", encoding="utf-8")
    except OSError:
        pass
    return path


def touched_flag_set(session_id: str) -> bool:
    return _flag_path(session_id).exists()


# ---------------------------------------------------------------------------
# Advisory text + observation note
# ---------------------------------------------------------------------------

def _subjects(signals: List[Dict[str, Any]], stype: str) -> List[str]:
    return [s.get("subject") for s in signals
            if s.get("type") == stype and s.get("subject")]


def _advisory_text(signals: List[Dict[str, Any]]) -> str:
    """One plain-language advisory line naming the gap. Advisory only — it never
    blocks; it asks the operator to confirm before ending the turn."""
    fence = _subjects(signals, "fence_breach")
    parse = _subjects(signals, "parse_error")
    parts: List[str] = []
    if fence:
        shown = ", ".join(fence[:_ADVISORY_SUBJECT_CAP])
        extra = len(fence) - _ADVISORY_SUBJECT_CAP
        if extra > 0:
            shown += " (+%d more)" % extra
        parts.append("%d change(s) outside the declared ownership zones: %s"
                     % (len(fence), shown))
    if parse:
        parts.append("%d artifact(s) failed to parse: %s"
                     % (len(parse), ", ".join(parse[:_ADVISORY_SUBJECT_CAP])))
    body = "; ".join(parts) or "%d memory-gap signal(s)" % len(signals)
    return "memory-gap: %s. Advisory only — confirm before ending the turn." % body


def _observation_note(signals: List[Dict[str, Any]]) -> str:
    """Compact audit note: per-type counts + a few subjects. The full signal
    bodies are not stored in the ledger (it is an audit trail, not a dump)."""
    counts: Dict[str, int] = {}
    for s in signals:
        counts[s.get("type")] = counts.get(s.get("type"), 0) + 1
    tally = " ".join("%s×%d" % (t, n) for t, n in sorted(counts.items()))
    subjects = [s.get("subject") for s in signals if s.get("subject")][:_ADVISORY_SUBJECT_CAP]
    return tally + ((" — " + ", ".join(subjects)) if subjects else "")


def _trace_degraded(actor: str, session_id: str, exc: Exception) -> None:
    """Visible no-op: the detector chain is broken, so record it instead of
    pretending the hook ran. Fail-open — the audit write never breaks the turn."""
    try:
        trace_log.append_event(hook=NAME, event="memory_gap_degraded",
                               actor=actor, session=session_id,
                               status="degraded", note=str(exc)[:200])
    except Exception:  # noqa: BLE001
        pass


def _record_observation(actor: str, session_id: str,
                        signals: List[Dict[str, Any]]) -> None:
    try:
        trace_log.append_event(hook=NAME, event="memory_gap_observation",
                               actor=actor, session=session_id,
                               status="observed", note=_observation_note(signals))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_stop(payload: Dict[str, Any], project_dir: Optional[str] = None) -> int:
    """Run the Stop policy: surface signals as an advisory + record an observation.
    Always returns ALLOW_EXIT (nudge never blocks)."""
    if not _enabled():
        return ALLOW_EXIT
    project_dir = project_dir or _project_dir(payload.get("cwd"))
    if not project_dir:
        return ALLOW_EXIT

    # No-op guard: only run the detector when this session actually wrote
    # something. Cheap; never imports the detector on read-only turns.
    session_id = payload.get("session_id") or ""
    if not touched_flag_set(session_id):
        return ALLOW_EXIT

    actor = hook_runtime.resolve_actor(session_id)

    try:
        memory_gap = _import_memory_gap()
    except ImportError as exc:
        # tier-0b: the detector chain is incomplete — degrade VISIBLY, then allow.
        _trace_degraded(actor, session_id, exc)
        return ALLOW_EXIT

    try:
        signals = memory_gap.collect(project_dir)
    except Exception as e:  # noqa: BLE001 — advisory: a hook must never break turn-end
        hook_runtime.log_hook_error(NAME, e)
        return ALLOW_EXIT

    if signals:
        _record_observation(actor, session_id, signals)
        sys.stderr.write("[advisory] %s\n" % _advisory_text(signals))
    return ALLOW_EXIT


def handle_post_tool_use(payload: Dict[str, Any],
                         project_dir: Optional[str] = None) -> int:
    """Set the touched-flag when a Write/Edit/MultiEdit landed a file_path. Any
    write arms the detector (an out-of-zone breach can be anywhere). Always allows
    — this handler only records state."""
    if not _enabled():
        return ALLOW_EXIT
    tool_input = payload.get("tool_input")
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if isinstance(file_path, str) and file_path:
        set_touched_flag(payload.get("session_id") or "")
    return ALLOW_EXIT


# ---------------------------------------------------------------------------
# CLI entry (the host invokes this file with stdin)
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    post_mode = "--post-tool-use" in argv
    payload = hook_runtime.read_stdin_json()
    project_dir = _project_dir(payload.get("cwd"))
    try:
        rc = (handle_post_tool_use if post_mode else handle_stop)(payload, project_dir)
    except Exception as e:  # noqa: BLE001 — a hook crash must never break the turn
        try:
            hook_runtime.log_hook_error(NAME, e)
        except Exception:
            pass
        rc = ALLOW_EXIT
    hook_runtime.emit_continue()
    return rc


if __name__ == "__main__":
    sys.exit(main())
