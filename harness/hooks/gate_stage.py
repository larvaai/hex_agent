#!/usr/bin/env python3
"""gate_stage.py — PreToolUse(Bash) compliance hook: the stage gate.

Detects whether the incoming Bash command advances an SDLC stage
(stage_detector, boundary-strict) and, for hard stages, demands the
required artifacts (artifact_check, policy from stage-policy.yaml). Missing
artifact / unresolvable plan / internal crash / missing dependency → exit 2
with an actionable reason (fail-closed, via run_compliance_hook).

HONESTY: this is a PRESENCE gate — it proves the gated step RAN (the
artifact exists and satisfies the verdict policy), NOT who ran it. An agent
writing its own PASS artifact passes it. Actor on trace events is
attribution, never authorization. Role checks live in plan_approval, not here.

Every decision is traced with actor: gate_block / gate_pass /
gate_skip (always with a reason) / stage_guess (advisory sampling of
free-floating stage words — evasion like `sh -c 'git push'` shows up here
and is otherwise caught at the transport level by the git pre-push hook).
Config consumption is traced as gate_config_loaded with the policy file hash
(tamper-visible).
"""

import hashlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.join(os.path.dirname(_HERE), "scripts"))

import hook_runtime  # noqa: E402
import trace_log     # noqa: E402

HOOK_CLASS = "compliance"
_HOOK = "gate_stage"

# Plan artifacts are produced ONLY by their skill controller via the Write tool
# (traced). A shell-spelled write into one is forgery — an agent fabricating a
# verdict to clear this gate. Blocked PRE here, the last point a Bash write can
# be stopped (bash_write_guard is PostToolUse, too late).
_ARTIFACT_GLOBS = ("plans/*/artifacts/*.json",)


def _artifact_forgery_reason(command):
    """Block reason if ``command`` shell-writes a plan artifact, else None.
    Reuses the shared shell-write-target parser with copy/move INCLUDED. A
    parser error never fabricates a block (returns None)."""
    if not command:
        return None
    try:
        import fnmatch
        import bash_write_guard
        targets = bash_write_guard.shell_write_targets(
            command, include_copy_move=True)
    except Exception:  # noqa: BLE001 — a parser error must not invent a block
        return None
    for rel in targets:
        if any(fnmatch.fnmatch(rel, pat) for pat in _ARTIFACT_GLOBS):
            return (
                "%s is a gate artifact — written ONLY by its producing skill "
                "via the Write tool (which the harness traces), never through "
                "the shell. A shell write here is forgery and is blocked. If "
                "you are the producing skill, use the Write tool." % rel
            )
    return None


def _policy_hash() -> str:
    """sha256 (12-hex) of the policy file bytes — ties the trace line to the
    exact config the decision used; any tampering shifts the hash."""
    import artifact_check
    try:
        return hashlib.sha256(
            artifact_check._policy_path().read_bytes()).hexdigest()[:12]
    except OSError:
        return "unreadable"


# Posture-env knobs that redirect the in-session gate's config. They are
# legitimate dev/test flexibility (the pre-push hook prefix-scrubs them and
# re-judges a push against tracked config), so the gate does NOT refuse them
# here — but it makes an active override tamper-EVIDENT: a stage gated under a
# redirected policy emits gate_env_override so the redirection is auditable,
# never silent. Prevention lives at the transport layer (pre-push) and the
# remote tier; in-session, evidence is the honest ceiling.
_POSTURE_ENV = ("HARNESS_STAGE_POLICY", "HARNESS_PROTECTED_BRANCHES",
                "HARNESS_GUARD_POLICY")


def _active_posture_overrides():
    return [k for k in _POSTURE_ENV if (os.environ.get(k) or "").strip()]


def core(data: dict):
    """None ⇒ pass; string ⇒ block reason (run_compliance_hook contract)."""
    # Imports that need PyYAML stay INSIDE core so a machine that skipped
    # preflight fails through the wrapper's ImportError arm (exit 2 + install
    # command), never an unguarded import-time crash.
    import artifact_check
    import harness_paths
    import stage_detector

    # Shape guard: an unexpected payload shape means "no command to gate",
    # not an internal crash — letting an AttributeError bubble here would
    # block with a misleading "gate crashed" message.
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    command = tool_input.get("command")
    if not isinstance(command, str):
        command = ""
    session = data.get("session_id")

    forge = _artifact_forgery_reason(command)
    if forge:
        trace_log.append_event(hook=_HOOK, event="gate_block", session=session,
                               tool="Bash", target="artifact-forgery",
                               status="BLOCKED", note=forge, tool_input=tool_input)
        return forge

    stage = stage_detector.detect_stage(command)
    if stage is None:
        guess = stage_detector.guess_stage(command)
        if guess:
            trace_log.append_event(hook=_HOOK, event="stage_guess",
                                   session=session, tool="Bash", target=guess,
                                   tool_input=tool_input)
        return None

    root = harness_paths.root()
    policy = artifact_check.load_policy()["stages"].get(stage) or {}
    trace_log.append_event(hook=_HOOK, event="gate_config_loaded",
                           session=session, target=stage,
                           note="stage-policy sha256:%s" % _policy_hash())

    overrides = _active_posture_overrides()
    if overrides:
        trace_log.append_event(
            hook=_HOOK, event="gate_env_override", session=session,
            target=stage,
            note="posture env override(s) active: %s — the in-session gate "
                 "honored a redirected policy; the pre-push transport re-judges "
                 "with tracked config. Audit the source." % ",".join(overrides))
        sys.stderr.write(
            "[advisory] %s: posture env override active (%s) — in-session policy "
            "may be redirected; tracked config still governs the transport push.\n"
            % (_HOOK, ",".join(overrides)))

    reason = artifact_check.check_stage(stage, root)
    if reason:
        trace_log.append_event(hook=_HOOK, event="gate_block", session=session,
                               tool="Bash", target=stage, status="BLOCKED",
                               note=reason, tool_input=tool_input)
        return reason

    if policy.get("hard"):
        trace_log.append_event(hook=_HOOK, event="gate_pass", session=session,
                               tool="Bash", target=stage, status="PASS",
                               tool_input=tool_input)
    else:
        # Soft stage: never blocks; advisory note only (check_stage already
        # returned None — soft stages carry no enforced requirement).
        sys.stderr.write("[advisory] %s: soft stage %r proceeding\n"
                         % (_HOOK, stage))
    return None


def main() -> None:
    raw = hook_runtime.read_stdin_json()
    # The wrapper exits silently when disabled; the gate's own contract is
    # stronger — a skipped gate decision must be VISIBLE in the audit trace
    # with its reason, so handle the disabled case before the wrapper.
    if not hook_runtime.hook_enabled(_HOOK, HOOK_CLASS):
        # Name the ACTUAL config file that disabled the gate: an env override
        # (HARNESS_HOOK_CONFIG) points outside the tracked default, and an
        # auditor following this note must land on the file that really
        # decided, not on a tracked default that still says enabled.
        trace_log.append_event(
            hook=_HOOK, event="gate_skip",
            session=raw.get("session_id"),
            note="disabled (enabled: false) via %s"
                 % hook_runtime._config_path())
        hook_runtime.emit_continue()
        sys.exit(0)
    import json
    hook_runtime.run_compliance_hook(_HOOK, core, raw=json.dumps(raw))


if __name__ == "__main__":
    main()
