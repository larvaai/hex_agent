"""_hooks.py — settings.json hook-wiring transforms for the installer.

Pure transforms over the hook registration, split out of install.py so the
orchestrator stays thin:
  - load_registration: parse hooks-registration.yaml from the source tree;
  - materialize_hooks: build Claude Code's settings `hooks` object from it,
    translating the `$HARNESS_ROOT` placeholder to "$CLAUDE_PROJECT_DIR";
  - merge_hooks: additively merge into a user's existing hooks (dedup by command,
    never clobber) — idempotent;
  - strip_harness_hooks: drop only harness-owned hooks back out on uninstall.

install.py re-exports these names, so callers and tests that reach them through
the `install` module see no change.
"""
import json
import re
from pathlib import Path

# Real Claude Code hook events. UserPromptExpansion is a live event on current
# Claude Code — verified via payload capture: a user-typed /hs:* fires it with a
# structured `command_name` — so it is wired (it captures user-typed skill
# invocations that the model-only PreToolUse:Skill path misses). On a host that
# does not support it the entry is inert (ignored), never an error. Genuinely
# unknown events are still allow-listed out and reported.
ALLOWED_EVENTS = {
    "SessionStart", "SessionEnd", "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PostToolUse", "Stop", "SubagentStop", "SubagentStart",
    "PreCompact", "Notification",
}

# A command is "ours" when it INVOKES a harness hook script —
# .../harness/hooks/<name>.py — not merely when it mentions the directory. A
# substring test on "harness/hooks/" would delete a user's own audit hook (e.g.
# `grep harness/hooks/ …`) on uninstall, so match the hook .py filename shape.
_HARNESS_HOOK_CMD = re.compile(r"harness/hooks/[A-Za-z0-9_]+\.py(?![A-Za-z0-9_])")


def _invokes_harness_hook(command) -> bool:
    """True when a settings.json command runs a harness hook .py (not just names
    the dir). Single test for the uninstall strip."""
    return bool(_HARNESS_HOOK_CMD.search(str(command or "")))


def to_command(raw: str) -> str:
    """Translate a registration command to the live settings form: the
    installer-time `$HARNESS_ROOT` placeholder becomes Claude Code's runtime
    `"$CLAUDE_PROJECT_DIR"` (quoted so a space in the path survives)."""
    return raw.replace("$HARNESS_ROOT", '"$CLAUDE_PROJECT_DIR"')


def load_registration(source_root: Path) -> dict:
    """Parse harness/install/hooks-registration.yaml from the source tree."""
    import yaml  # lazy: a declared dep, but keep import-time light

    reg_path = (Path(source_root) / "harness" / "install"
                / "hooks-registration.yaml")
    raw = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    return raw


def materialize_hooks(registration: dict):
    """Build the Claude Code `hooks` settings object from the registration.

    Returns (hooks, skipped). `hooks` is keyed by event; each event holds a list
    of matcher-groups ({matcher?, hooks:[{type:command, command}]}); entries
    sharing an (event, matcher) collapse into one group, preserving order.
    `skipped` lists (event, command) for events outside ALLOWED_EVENTS.
    """
    hooks: dict = {}
    skipped: list = []
    for entry in registration.get("hooks", []) or []:
        event = entry.get("event")
        command = entry.get("command", "")
        matcher = entry.get("matcher")  # may be absent (no-matcher events)
        if event not in ALLOWED_EVENTS:
            skipped.append((event, command))
            continue
        groups = hooks.setdefault(event, [])
        group = _find_group(groups, matcher)
        if group is None:
            group = {} if matcher is None else {"matcher": matcher}
            group["hooks"] = []
            groups.append(group)
        group["hooks"].append({"type": "command", "command": to_command(command)})
    return hooks, skipped


def _find_group(groups: list, matcher):
    for g in groups:
        if g.get("matcher") == matcher:
            return g
    return None


def merge_hooks(existing: dict, new: dict) -> dict:
    """Additively merge `new` into `existing`: same (event, matcher) groups are
    joined, commands deduped by string, and every user-authored event/group/hook
    is preserved. Idempotent — merging the same `new` twice adds nothing."""
    result = json.loads(json.dumps(existing)) if existing else {}
    for event, groups in new.items():
        dst_groups = result.setdefault(event, [])
        for g in groups:
            matcher = g.get("matcher")
            target = _find_group(dst_groups, matcher)
            if target is None:
                dst_groups.append(json.loads(json.dumps(g)))
                continue
            seen = {h.get("command") for h in target.get("hooks", [])}
            for h in g.get("hooks", []):
                if h.get("command") not in seen:
                    target.setdefault("hooks", []).append(
                        json.loads(json.dumps(h)))
                    seen.add(h.get("command"))
    return result


def strip_harness_hooks(existing: dict) -> dict:
    """Drop every harness-owned hook (command points into harness/hooks/),
    pruning groups and events that empty out. User-authored hooks survive."""
    result: dict = {}
    for event, groups in existing.items():
        new_groups = []
        for g in groups:
            kept = [h for h in g.get("hooks", [])
                    if not _invokes_harness_hook(h.get("command", ""))]
            if kept:
                ng = {k: v for k, v in g.items() if k != "hooks"}
                ng["hooks"] = kept
                new_groups.append(ng)
        if new_groups:
            result[event] = new_groups
    return result
