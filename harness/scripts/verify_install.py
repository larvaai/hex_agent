#!/usr/bin/env python3
"""verify_install.py — compare files on disk against harness/manifest.json.

Fails LOUD per asset (R8 install drift): every drifted/missing file is named
individually — never a bare "mismatch". --strict exits non-zero on any drift;
without it the report still prints but exit is 0 (inspection mode).

Usage:
    python3 harness/scripts/verify_install.py [--root <repo-root>] [--strict]
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Same hashing as the builder — single source for the digest algorithm.
sys.path.append(str(Path(__file__).resolve().parent))
from build_manifest import MANIFEST_REL, sha256_file  # noqa: E402

# A hook command line names its script as harness/hooks/<name>.py. Parsed by
# pattern (not YAML) so verify stays dependency-free; hooks-registration.yaml is
# the installer's input — the one place a hook gets wired to a Claude Code event.
_HOOK_CMD_RE = re.compile(r"harness/hooks/([A-Za-z0-9_]+\.py)(?![A-Za-z0-9_])")


def is_localized(rel: str) -> bool:
    """True for files a deploying team is EXPECTED to edit per target: the
    gate-input config under harness/data/*.yaml (reviewer roster, stage/guard
    policy, protected branches, voice knobs, output language) and the hook
    registration. They ship in the manifest as a baseline, but post-install
    divergence is customization, not integrity drift — gate config is
    tamper-visible via git, not integrity-locked by the manifest. Single
    source of truth shared with the installer's final verify (DRY). Code under
    harness/hooks, scripts, rules, skills, etc. is NOT localized: it still fails
    --strict on any mismatch.

    harness/hooks/harness-hooks.yaml is localized too: it is the per-deployment
    hook enable/mode override file (the component projector writes enabled flags
    into it, and a deployer may flip a gate in an emergency). Like the other
    gate configs it is tamper-visible via git + the gate_skip trace, not
    integrity-locked by the manifest."""
    if rel in ("harness/install/hooks-registration.yaml",
               "harness/hooks/harness-hooks.yaml"):
        return True
    return (rel.startswith("harness/data/")
            and rel.endswith(".yaml")
            and "/" not in rel[len("harness/data/"):])


def split_localized(problems: list) -> tuple:
    """Partition (rel, problem) tuples into (hard_drift, localized) by
    is_localized. The installer and the CLI both classify through this — one
    rule, two callers."""
    hard, localized = [], []
    for rel, prob in problems:
        (localized if is_localized(rel) else hard).append((rel, prob))
    return hard, localized


def verify(root: Path) -> list:
    """Return list of (relpath, problem) tuples; empty = clean."""
    manifest_path = root / MANIFEST_REL
    if not manifest_path.is_file():
        return [(MANIFEST_REL, "manifest missing — run build_manifest.py")]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = []
    for rel, expected in sorted(manifest.get("files", {}).items()):
        p = root / rel
        if not p.is_file():
            problems.append((rel, "missing"))
        elif sha256_file(p) != expected:
            problems.append((rel, "hash mismatch"))
    return problems


def prepush_copy_warnings(root: Path) -> list:
    """The ACTIVE pre-push hook lives at .git/hooks/pre-push, outside the
    manifest's reach — the manifest only hashes harness/. This cheap check
    compares the installed copy against its source and NAMES a difference.
    Warn-only by decision: a repo that never installed the git hook (or has
    no .git dir at all) must not fail verification over it."""
    src = root / "harness" / "install" / "git-pre-push-hook.sh"
    installed = root / ".git" / "hooks" / "pre-push"
    if not src.is_file() or not (root / ".git").is_dir():
        return []
    if not installed.is_file():
        return [(".git/hooks/pre-push",
                 "not installed (transport gate inactive — the installer "
                 "copies harness/install/git-pre-push-hook.sh there)")]
    if sha256_file(installed) != sha256_file(src):
        return [(".git/hooks/pre-push",
                 "installed copy differs from harness/install/"
                 "git-pre-push-hook.sh — reinstall or diff the two")]
    return []


def hook_registration_problems(root: Path) -> list:
    """Co-presence between shipped entrypoint hooks and hooks-registration.yaml.
    Two failure modes, each NAMED per file (R8 install drift):
      - a registered command names a hook file that is absent on disk — the
        installer would wire a dangling command;
      - a shipped entrypoint hook (carries `__main__`) is missing from the
        registration — it ships but never fires (a silent no-op).
    A hook library WITHOUT `__main__` (hook_runtime, trace_log) is not an
    entrypoint and is not required to be registered. Returns [] for a layout
    that has no registration file or hooks dir (not an installable tree)."""
    reg = root / "harness" / "install" / "hooks-registration.yaml"
    hooks_dir = root / "harness" / "hooks"
    if not reg.is_file() or not hooks_dir.is_dir():
        return []
    registered = set(_HOOK_CMD_RE.findall(reg.read_text(encoding="utf-8")))
    problems = []
    for fname in sorted(registered):
        if not (hooks_dir / fname).is_file():
            problems.append(
                ("harness/install/hooks-registration.yaml",
                 "registers %s but harness/hooks/%s is absent" % (fname, fname)))
    for p in sorted(hooks_dir.glob("*.py")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "__main__" not in text:
            continue  # library module, not an entrypoint hook
        if p.name not in registered:
            problems.append(
                ("harness/hooks/%s" % p.name,
                 "entrypoint hook not registered in hooks-registration.yaml "
                 "(ships but never fires)"))
    return problems


def component_file_problems(root: Path) -> list:
    """Each file a component DECLARES (its hooks/scripts/data) must exist on
    disk — a component that ships a dangling member would wire/enable a file
    that isn't there. NAMED per missing file (R8 install drift). SKILLS are
    informational (a skill may be a not-yet-ported placeholder) and are not
    checked. Returns [] when components.yaml is absent (not a component-aware
    tree); a malformed manifest is itself reported as drift."""
    comp_file = root / "harness" / "data" / "components.yaml"
    if not comp_file.is_file():
        return []
    sys.path.append(str(root / "harness" / "scripts"))
    try:
        import component_config
        components = component_config.load_components(comp_file)
    except Exception as e:  # noqa: BLE001 — an unreadable manifest is drift
        return [("harness/data/components.yaml", "unreadable: %s" % e)]
    member_dirs = {
        "hooks": ("harness/hooks", ".py"),
        "scripts": ("harness/scripts", ".py"),
        "data": ("harness/data", ""),
    }
    problems = []
    for name in sorted(components):
        spec = components[name]
        for kind, (subdir, suffix) in member_dirs.items():
            for member in spec.get(kind, []):
                rel = "%s/%s%s" % (subdir, member, suffix)
                if not (root / rel).is_file():
                    problems.append(
                        (rel, "declared by component %r but missing on disk"
                         % name))
    return problems


def plugin_presence_problems(root: Path) -> list:
    """Every plugin the local marketplace DECLARES must exist on disk: a
    `.claude-plugin/plugin.json` plus a `skills/` or `agents/` dir (a plugin
    with neither loads nothing). NAMED per offending plugin (R8 install drift) —
    a marketplace that points at a missing plugin loads silently nothing.
    Returns [] when there is no marketplace.json (not a plugin-aware tree); an
    unreadable marketplace is itself reported as drift."""
    mp = root / "harness" / "plugins" / ".claude-plugin" / "marketplace.json"
    if not mp.is_file():
        return []
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — an unreadable marketplace is drift
        return [("harness/plugins/.claude-plugin/marketplace.json",
                 "unreadable: %s" % e)]
    problems = []
    for entry in data.get("plugins", []):
        name = entry.get("name")
        if not name:
            continue
        # `source` is a path relative to the marketplace dir; strip the leading
        # "./" as a PREFIX (not lstrip, which is a char-set strip that would eat a
        # leading dot of a real segment like "./.internal").
        src = entry.get("source") or ("./%s" % name)
        if src.startswith("./"):
            src = src[2:]
        base = root / "harness" / "plugins" / src
        rel = "harness/plugins/%s" % src
        if not (base / ".claude-plugin" / "plugin.json").is_file():
            problems.append(
                (rel, "marketplace declares plugin %r but %s/.claude-plugin/"
                 "plugin.json is absent" % (name, rel)))
            continue
        # A plugin is loadable if it ships ANY content CC loads: skills, agents,
        # commands, or hooks. A hook-only plugin is legitimate (the harness has
        # hook-only feature bundles), so do not flag it as "nothing to load".
        if not any((base / d).is_dir()
                   for d in ("skills", "agents", "commands", "hooks")):
            problems.append(
                (rel, "plugin %r has no skills/agents/commands/hooks dir "
                 "(nothing to load)" % name))
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero on any drift")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    for rel, problem in prepush_copy_warnings(root):
        sys.stderr.write("WARN %s: %s\n" % (rel, problem))
    # Localization applies to integrity hash drift only. Hook-registration
    # co-presence defects (a dangling wire, an unregistered entrypoint) are real
    # bugs regardless of which file they are keyed to, so they stay hard.
    hard, localized = split_localized(verify(root))
    hard += hook_registration_problems(root)
    hard += component_file_problems(root)
    hard += plugin_presence_problems(root)
    for rel, problem in localized:
        sys.stderr.write(
            "WARN %s: %s (deployer-localized config — expected to differ from "
            "the shipped baseline)\n" % (rel, problem))
    if not hard:
        print("verify_install OK: manifest + hook registration consistent")
        return 0
    for rel, problem in hard:
        sys.stderr.write("DRIFT %s: %s\n" % (rel, problem))
    sys.stderr.write("verify_install: %d file(s) drifted\n" % len(hard))
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
