#!/usr/bin/env python3
"""write_guard.py — tool-mediated config-edit gate (compliance, fail-closed).

PreToolUse(Write|Edit|MultiEdit): block when the target is one of the files
the gate posture depends on — hook code, gate configs, the pre-push source,
the plan-approval artifact. GUARD_LIST is a CODE CONSTANT: config can only
ADD paths (write-guard.yaml `extra_guarded`), never remove one — a config
knob that can shrink the guard is a guard that does not exist.

HONESTY — the name is the scope: this is a tool-mediated CONFIG-EDIT gate.
It sees Write/Edit/MultiEdit tool calls and nothing else. It does NOT see a
Bash redirect (`echo > file`), does NOT see an editor outside the session,
and must never be described as blocking "all writes" — those paths are
covered by the layer below (git diff visibility, manifest verify, pre-push
env scrub). The deliberate floor: an edit made around this gate lands in a
TRACKED file, so it surfaces as a git diff — tamper-EVIDENT only, which is
the designed level, not a stronger one.

Enable-path autonomy: the usual hook_enabled() reads HARNESS_HOOK_CONFIG,
which would let one env var switch this guard off silently. The guard
therefore resolves its enabled flag ONLY from write-guard.yaml next to this
file (tracked in git). Flipping it there is the break-glass: done with a
normal editor outside the session (in-session the switch file is itself on
the guard list), and the flip is a visible diff + a traced gate_skip.

Fail-closed is local too: this hook deliberately does not reuse
run_compliance_hook (it would inherit the env-driven enable path); the
wrapper's exception→exit-2 discipline is reimplemented here.

Known residual limit (same family as the rest of the hook layer):
HARNESS_ROOT redirects which repo the guard considers "its own" — that env
hole is closed where it matters for posture, at the pre-push transport
scrub; in-session it remains part of the documented tamper-EVIDENT floor.
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

HOOK_CLASS = "compliance"

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

# Repo-root-relative globs (fnmatch). Constant by design.
GUARD_LIST = (
    "harness/hooks/*.py",
    "harness/hooks/harness-hooks.yaml",
    "harness/hooks/write-guard.yaml",
    "harness/data/stage-policy.yaml",
    "harness/data/simplify-policy.yaml",
    "harness/data/team.yaml",
    "harness/data/ownership.yaml",
    "harness/data/agent-permissions.yaml",
    "harness/scripts/agent_permissions.py",
    "harness/data/task-store.yaml",
    "harness/scripts/artifact_check.py",
    "harness/scripts/stage_detector.py",
    "harness/scripts/fs_guard.py",
    "harness/scripts/claims.py",
    "harness/scripts/team_config.py",
    "harness/scripts/component_config.py",
    "harness/data/components.yaml",
    "harness/data/component-policy.yaml",
    "harness/scripts/plan_approval.py",
    "harness/scripts/task_store.py",
    "harness/scripts/task_store_http.py",
    "harness/scripts/task_store_github.py",
    "harness/scripts/task_store_gitlab.py",
    "harness/install/git-pre-push-hook.sh",
    "harness/install/hooks-registration.yaml",
    "plans/*/artifacts/plan-approval.json",
)

_SWITCH_NAME = "write-guard.yaml"


def _root() -> Path:
    raw = os.environ.get("HARNESS_ROOT")
    if raw:
        return Path(raw).resolve()
    # write_guard may live under <root>/harness/hooks (repo layout); resolve
    # off __file__ so an installed copy guards ITS OWN repo, never the CWD.
    return Path(__file__).resolve().parent.parent.parent


def _switch_config() -> dict:
    """Parse write-guard.yaml from the guarded repo's harness/hooks/ — the
    directory this hook is installed into, so "next to the hook" and "in the
    guarded tree" are the same file. ONLY this file decides enabled (no
    HARNESS_HOOK_CONFIG, no env knob). Malformed → {} and the caller treats
    the guard as ENABLED (fail-closed: a broken switch never opens the
    gate)."""
    p = _root() / "harness" / "hooks" / _SWITCH_NAME
    if not p.is_file():
        return {}
    try:
        import yaml
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}  # unparsable switch = guard stays on


def _extra_guarded(cfg) -> tuple:
    extra = cfg.get("extra_guarded")
    if isinstance(extra, list):
        return tuple(str(x) for x in extra if isinstance(x, str) and x.strip())
    return ()


def _rel_target(file_path, root: Path):
    """Target as a root-relative POSIX path, resolved (`..` collapsed,
    symlinks followed) so traversal cannot dodge the match. None when the
    target lies outside the repo root entirely."""
    target = Path(file_path)
    if not target.is_absolute():
        target = root / target
    resolved = target.resolve(strict=False)
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def check(data) -> "str | None":
    """None = allow; string = block reason (the compliance core contract)."""
    tool = data.get("tool_name")
    if tool not in _GUARDED_TOOLS:
        return None
    file_path = (data.get("tool_input") or {}).get("file_path")
    if not file_path:
        return None

    cfg = _switch_config()
    root = _root()
    rel = _rel_target(file_path, root)
    if rel is None:
        return None  # outside this repo — not this guard's jurisdiction

    patterns = GUARD_LIST + _extra_guarded(cfg)
    hit = next((pat for pat in patterns if fnmatch.fnmatch(rel, pat)), None)
    if hit is None:
        return None

    if cfg.get("enabled") is False:
        # Break-glass taken: tracked switch flipped outside the session.
        _trace("gate_skip", rel, data,
               note="write_guard disabled via %s (tracked break-glass; "
                    "the flip is a git diff)" % _SWITCH_NAME)
        return None

    _trace("gate_block", rel, data, note="matched %s" % hit)
    return (
        "%s is gate config (matched %r) — agent tools may not edit it. "
        "If the change is intended, make it with a normal editor outside "
        "the agent session: the file is tracked, the diff stays visible. "
        "Artifacts like plan-approval.json are written via their CLI "
        "(plan_approval.py) only." % (rel, hit)
    )


def _trace(event, target, data, note=None) -> None:
    try:
        import trace_log
        trace_log.append_event("write_guard", event,
                               session=data.get("session_id"),
                               tool=data.get("tool_name"), target=target,
                               note=note)
    except Exception:
        pass  # tracing must not break the gate decision


def main() -> None:
    """Fail-closed shell (the run_compliance_hook discipline, minus its
    env-driven enable path): every internal error blocks with exit 2."""
    try:
        try:
            data = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}

        reason = check(data)
        if reason:
            sys.stderr.write("[write_guard] BLOCKED: %s\n" % reason)
            sys.exit(2)
        try:
            sys.stdout.write(json.dumps({"continue": True}))
            sys.stdout.flush()
        except Exception:
            pass
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — a broken gate must gate
        try:
            import hook_runtime
            hook_runtime.log_hook_error("write_guard", e)
        except Exception:
            pass
        sys.stderr.write(
            "[write_guard] BLOCKED: gate crashed (%s: %s). Fail-closed by "
            "policy. Emergency off-switch: set `enabled: false` in "
            "harness/hooks/write-guard.yaml with an editor OUTSIDE the "
            "agent session (tracked file, diff visible).\n"
            % (type(e).__name__, e))
        sys.exit(2)


if __name__ == "__main__":
    main()
