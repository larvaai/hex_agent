#!/usr/bin/env python3
"""ownership_guard.py — PreToolUse(Bash) compliance hook: per-actor commit gate.

On a `git commit`, refuse staged files that fall in ANOTHER declared owner's
lane (ownership_gate.reconcile_actor, the poaching check). Only declared owners
are policed: a manifest with no `owner:` fields, a contributor not yet assigned
a lane, or a missing manifest all pass. Posture (off/warn/block) flows through
run_compliance_hook + the guard policy — ownership_guard is an enforcement guard
(block at strict/balanced, warn at lenient).

HONESTY: actor on the trace is attribution, not authorization — the gate proves
which lane a staged file falls in, it cannot prove who is at the keyboard. The
manifest path is HARNESS_WORK_OWNERSHIP_FILE, distinct from
HARNESS_OWNERSHIP_FILE (fs_guard already claims that for the script-path
containment manifest). Absent manifest => additive skip, never a block.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.join(os.path.dirname(_HERE), "scripts"))

import hook_runtime  # noqa: E402
import trace_log     # noqa: E402

HOOK_CLASS = "compliance"
_HOOK = "ownership_guard"


def _staged_files():
    """Repo-relative paths staged for the pending commit (git diff --cached).
    Best-effort: any git failure yields an empty list (nothing to police)."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001 — no git / not a repo → nothing to add
        return []
    if out.returncode != 0:
        return []
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def _manifest_path():
    raw = os.environ.get("HARNESS_WORK_OWNERSHIP_FILE")
    return raw.strip() if raw and raw.strip() else None


def core(data: dict):
    """None ⇒ pass; string ⇒ block reason (run_compliance_hook contract)."""
    import ownership_gate
    import stage_detector

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    command = tool_input.get("command")
    if not isinstance(command, str):
        command = ""
    session = data.get("session_id")

    if stage_detector.detect_stage(command) != "commit":
        return None  # only commits are policed

    manifest = _manifest_path()
    if not manifest or not os.path.exists(manifest):
        return None  # additive: no work manifest ⇒ nothing to enforce

    try:
        cfg = ownership_gate.load_ownership(manifest)
    except ownership_gate.OwnershipConfigError as e:
        return "work-ownership manifest invalid: %s" % e  # fail-closed

    changed = _staged_files()
    if not changed:
        return None
    actor = hook_runtime.resolve_actor(session_id=session)
    reason = ownership_gate.reconcile_actor(changed, cfg["units"], actor)
    if reason:
        trace_log.append_event(hook=_HOOK, event="ownership_block",
                               session=session, tool="Bash", actor=actor,
                               status="BLOCKED", note=reason,
                               tool_input=tool_input)
        return reason
    trace_log.append_event(hook=_HOOK, event="ownership_pass",
                           session=session, tool="Bash", actor=actor,
                           status="PASS",
                           note="%d staged file(s) within own lane" % len(changed))
    return None


def main() -> None:
    raw = hook_runtime.read_stdin_json()
    # Like gate_stage: a skipped gate decision must be VISIBLE in the trace with
    # its reason, so handle the disabled case before the silent wrapper.
    if not hook_runtime.hook_enabled(_HOOK, HOOK_CLASS):
        trace_log.append_event(
            hook=_HOOK, event="ownership_skip",
            session=raw.get("session_id"),
            note="disabled via %s" % hook_runtime._config_path())
        hook_runtime.emit_continue()
        sys.exit(0)
    import json
    hook_runtime.run_compliance_hook(_HOOK, core, raw=json.dumps(raw))


if __name__ == "__main__":
    main()
