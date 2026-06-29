#!/usr/bin/env python3
"""paths.py — single home for symm-harness root + runtime-dir resolution.

Every hook/script resolves the symm-harness root and its state dirs through
here, so a path fix lands once. Resolution is PURE (no mkdir): writers own
their mkdir, readers never create what they inspect.

root() is __file__-anchored (scripts/ lives directly under the root), so it
needs no cwd-walk and works from any invocation dir. SYMM_ROOT / SYMM_STATE_DIR
override for tests. The SYMM_ prefix keeps this isolated from the sibling
harness/ tree (HARNESS_*), so the two never write into each other's state.
"""

import os
from pathlib import Path


def root() -> Path:
    raw = os.environ.get("SYMM_ROOT")
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parent.parent  # symm-harness/


def state_dir() -> Path:
    raw = os.environ.get("SYMM_STATE_DIR")
    return Path(raw) if raw else root() / "state"


def trace_dir() -> Path:
    return state_dir() / "trace"


def telemetry_dir() -> Path:
    return state_dir() / "telemetry"


def sessions_dir() -> Path:
    return state_dir() / "sessions"


def handoff_dir() -> Path:
    """The mind→voice seam: consolidator writes <session>-conclusion.json here,
    render reads it. Lives under state/ so it is gitignored and ephemeral."""
    return state_dir() / "handoff"


def config_file() -> Path:
    """symm-hooks.yaml (per-hook enabled/mode overrides), at the root."""
    raw = os.environ.get("SYMM_HOOK_CONFIG")
    return Path(raw) if raw else root() / "symm-hooks.yaml"
