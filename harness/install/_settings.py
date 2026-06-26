#!/usr/bin/env python3
"""_settings.py — read/merge/write .claude settings JSON (extracted from
install.py). Leaf IO over the target settings file; a syntax error becomes a
deployer-actionable InstallError."""
import json
from pathlib import Path

from _errors import InstallError


def _settings_path(target_root: Path, local: bool) -> Path:
    name = "settings.local.json" if local else "settings.json"
    return target_root / ".claude" / name

def _read_json(path: Path) -> dict:
    """Read a JSON settings file, turning a syntax error into an actionable
    InstallError (a team may hand-edit .claude/settings.json and leave it
    invalid). Missing file -> empty settings, the install-from-scratch case."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InstallError(
            "%s is not valid JSON (%s) — fix or move it, then re-run the "
            "installer." % (path, e)) from e

def _load_settings(path: Path) -> dict:
    return _read_json(path)

def _write_settings(path: Path, settings: dict, dry_run: bool):
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
