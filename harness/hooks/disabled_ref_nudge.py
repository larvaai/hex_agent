#!/usr/bin/env python3
"""disabled_ref_nudge.py — advisory pointer for refs into a disabled group (nudge class).

After the decomposition a fresh install enables only the spine; the six themed groups
(flow/think/research/create/mem/meta) and the ck-port siblings are opt-in. A skill
handoff that names `hs-<group>:<skill>` while `hs-<group>` is disabled is NOT a broken
reference — the contract still stands. This nudge spots such a reference in the session
context and suggests the two ways forward: enable the group, or read the skill inline.

Self-describing by design: the reference carries its own group, so detection needs only
the live `enabledPlugins` — never a skill->group map. Spine refs (`hs:<skill>`) use the
`hs:` prefix, never `hs-`, so they can never trip this.

Nudge posture: advisory, fail-open, ALWAYS exit 0 — it writes at most one reminder line
to stderr and never blocks. The binding HOOK_CLASS lives here in code, not in config.
"""
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 — older/detached streams; never fatal
    pass

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS_DIR, "..", "scripts"))
if _HOOKS_DIR not in sys.path:
    sys.path.append(_HOOKS_DIR)
import hook_runtime  # noqa: E402

HOOK_CLASS = "nudge"
_NAME = Path(__file__).stem

# hs-<group>:<skill> — group is letters only; skill may carry hyphens. The
# negative lookbehind (no word-char, '.', '/' or '-' before) keeps it from
# matching inside a longer token or inside a URL/domain (www.hs-x:, /hs-x:).
_REF_RE = re.compile(r"(?<![\w./-])hs-([a-z]+):([a-z][\w-]*)")


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _enabled_plugins() -> dict:
    """Live enabledPlugins merged from .claude/settings.json then settings.local.json
    (local wins). Missing/invalid files are skipped — an empty map reads as
    everything-off, which at worst yields a harmless advisory (fail-open)."""
    merged: dict = {}
    base = _project_dir() / ".claude"
    for fn in ("settings.json", "settings.local.json"):
        try:
            d = json.loads((base / fn).read_text(encoding="utf-8"))
            ep = d.get("enabledPlugins")
            if isinstance(ep, dict):
                merged.update(ep)
        except Exception:  # noqa: BLE001 — absent/invalid settings -> skip
            continue
    return merged


def _group_enabled(group: str, enabled: dict) -> bool:
    """Is plugin hs-<group> enabled? Keys may be bare (`hs-mem`) or marketplace-
    qualified (`hs-mem@hs-local`); compare on the name before any `@`."""
    target = f"hs-{group}"
    for key, val in enabled.items():
        if str(key).split("@", 1)[0] == target:
            # enabledPlugins values are JSON booleans; only real True counts
            # as enabled (a malformed string like "false" must NOT pass).
            return val is True
    return False  # not listed -> not enabled


def _scan_refs(data) -> set:
    """Every hs-<group>:<skill> reference anywhere in the payload (recursive)."""
    found: set = set()

    def walk(v):
        if isinstance(v, str):
            for g, s in _REF_RE.findall(v):
                found.add((g, s))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(data)
    return found


def core(data: dict):
    """Return one advisory line iff the context references a disabled-group skill."""
    refs = _scan_refs(data if isinstance(data, dict) else {})
    if not refs:
        return None
    enabled = _enabled_plugins()
    off = sorted({(g, s) for g, s in refs if not _group_enabled(g, enabled)})
    if not off:
        return None
    groups = sorted({g for g, _ in off})
    examples = "; ".join(f"hs-{g}:{s}" for g, s in off[:3])
    group_list = ", ".join(f"hs-{g}" for g in groups)
    return (
        f"disabled-group ref: {examples} — group(s) {group_list} are not enabled. "
        f"Enable with `hs-cli components --enable <group>` (or at install time), or "
        f"read harness/plugins/hs-<group>/skills/<skill>/SKILL.md and perform it inline. "
        f"The handoff still stands — do not drop it."
    )


def main() -> int:
    hook_runtime.run_nudge_hook(_NAME, core)
    return 0


if __name__ == "__main__":
    sys.exit(main())
