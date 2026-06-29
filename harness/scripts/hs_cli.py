#!/usr/bin/env python3
"""hs-cli — a thin operator front-end over the harness scripts.

Every verb wraps a script that already owns the logic; the CLI adds no new
behaviour, just one discoverable entry point and install-time group selection.

    hs doctor                      verify_install --strict + preflight_deps
    hs migrate [--check|--dry-run] run the decomposition migrate engine
    hs list                        plugins, their skills, and on/off state
    hs components --enable G ...    flip a group on/off (--disable G; bare or hs-G)
    hs version                     harness_version + kit_digest from release.json
    hs install [install.py args]   install + interactive group selection

No watch/content/dashboard verbs — those belong to a different tool (YAGNI).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parents[1]  # harness/scripts -> harness -> repo root
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _run(argv: list[str]) -> int:
    """Run a child process, inheriting stdio, and return its exit code."""
    return subprocess.run(argv).returncode


# --------------------------------------------------------------------- verbs

def cmd_version(args) -> int:
    import harness_release
    rel = harness_release.read_release(_ROOT)
    print("hs {ver} ({ch})  kit_digest={dig}".format(
        ver=rel.get("harness_version", "?"),
        ch=rel.get("channel", "?"),
        dig=rel.get("kit_digest", "?"),
    ))
    return 0


def cmd_doctor(args) -> int:
    # verify_install reds on inconsistency; preflight never blocks (advisory).
    rc = _run([sys.executable, str(_SCRIPTS / "verify_install.py"), "--strict"])
    _run([sys.executable, str(_SCRIPTS / "preflight_deps.py")])
    return 1 if rc else 0


def _component_name(group: str) -> str:
    """Accept either the plugin name (hs-flow) or the bare component (flow)."""
    return group[3:] if group.startswith("hs-") else group


def cmd_components(args) -> int:
    import component_config as cc
    if not args.enable and not args.disable:
        argv = ["show"]
        if args.policy_file:
            argv += ["--policy-file", args.policy_file]
        return cc.main(argv)
    selection: dict[str, bool] = {}
    for g in args.enable or []:
        selection[_component_name(g)] = True
    for g in args.disable or []:
        selection[_component_name(g)] = False
    try:
        cc.apply_selection(
            selection,
            policy_path=args.policy_file,
            settings_path=args.settings_file,
            hooks_path=args.hooks_file,
            state_path=args.state_file,
        )
    except cc.ComponentConfigError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    print("components updated: " + ", ".join(
        "%s=%s" % (k, "on" if v else "off") for k, v in sorted(selection.items())))
    return 0


def _enabled_plugins() -> dict:
    merged: dict = {}
    base = Path(os.environ.get("CLAUDE_PROJECT_DIR") or _ROOT) / ".claude"
    for fn in ("settings.json", "settings.local.json"):
        try:
            d = json.loads((base / fn).read_text(encoding="utf-8"))
            ep = d.get("enabledPlugins")
            if isinstance(ep, dict):
                merged.update(ep)
        except Exception:  # noqa: BLE001 — absent/invalid settings
            continue
    return merged


def _plugin_on(plugin: str, enabled: dict) -> bool:
    if plugin == "hs":
        return True  # spine is always on
    for key, val in enabled.items():
        if str(key).split("@", 1)[0] == plugin:
            return bool(val)
    return False


def cmd_list(args) -> int:
    plugins_dir = _ROOT / "harness/plugins"
    enabled = _enabled_plugins()
    rows = []
    for pdir in sorted(plugins_dir.iterdir()):
        sdir = pdir / "skills"
        if not sdir.is_dir():
            continue
        skills = sorted(p.name for p in sdir.iterdir() if p.is_dir())
        if not skills:
            continue
        state = "spine" if pdir.name == "hs" else ("on" if _plugin_on(pdir.name, enabled) else "off")
        rows.append((pdir.name, state, skills))
    width = max((len(n) for n, _, _ in rows), default=2)
    for name, state, skills in rows:
        print("%-*s  [%-5s]  %2d  %s" % (width, name, state, len(skills), ", ".join(skills)))
    return 0


def cmd_install(rest: list[str]) -> int:
    argv = [sys.executable, str(_ROOT / "harness/install/install.py")]
    return _run(argv + (rest or []))


# ----------------------------------------------------------------------- cli

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="hs", description="harness operator CLI")
    sub = ap.add_subparsers(dest="verb", required=True)

    sub.add_parser("version", help="print harness version + kit digest").set_defaults(fn=cmd_version)
    sub.add_parser("doctor", help="health-check the install").set_defaults(fn=cmd_doctor)
    sub.add_parser("list", help="list plugins, skills, and on/off state").set_defaults(fn=cmd_list)

    sub.add_parser("migrate", help="run the decomposition migrate engine "
                   "(args pass through to the engine)")

    c = sub.add_parser("components", help="enable/disable a group")
    c.add_argument("--enable", action="append", metavar="GROUP")
    c.add_argument("--disable", action="append", metavar="GROUP")
    c.add_argument("--policy-file", default=None)
    c.add_argument("--settings-file", default=None)
    c.add_argument("--hooks-file", default=None)
    c.add_argument("--state-file", default=None)
    c.set_defaults(fn=cmd_components)

    sub.add_parser("install", help="install + pick which groups to enable "
                   "(args pass through to install.py)")

    return ap


# Verbs whose args are forwarded verbatim to the wrapped tool — intercepted
# before argparse so engine flags like --check are not swallowed by this parser.
_PASSTHROUGH = {"migrate", "install"}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in _PASSTHROUGH:
        verb, rest = argv[0], argv[1:]
        if verb == "migrate":
            import migrate_decomposition as md
            return md.main(rest)
        return cmd_install(rest)
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
