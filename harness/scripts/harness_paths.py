#!/usr/bin/env python3
"""harness_paths.py — single home for root + state-dir resolution.

Every harness script resolves the repo root and the runtime state dirs
through here so a path fix lands once. Resolution is PURE (no mkdir):
writers own their own mkdir, readers never create what they inspect.

root() order: HARNESS_ROOT env (tests, odd layouts) > upward walk from CWD
looking for harness/manifest.json (post-install marker) or harness/hooks/
(pre-manifest bootstrap — the manifest only exists after the first
build_manifest run) > CWD as-is.
"""

import os
from pathlib import Path


def root() -> Path:
    raw = os.environ.get("HARNESS_ROOT")
    if raw:
        return Path(raw).resolve()
    cur = Path.cwd().resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / "harness" / "manifest.json").is_file():
            return candidate
        if (candidate / "harness" / "hooks").is_dir():
            return candidate
    return cur


def state_dir() -> Path:
    raw = os.environ.get("HARNESS_STATE_DIR")
    if raw:
        return Path(raw)
    return root() / "harness" / "state"


def trace_dir() -> Path:
    return state_dir() / "trace"


def telemetry_dir() -> Path:
    return state_dir() / "telemetry"
