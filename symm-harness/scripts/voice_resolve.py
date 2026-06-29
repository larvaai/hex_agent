#!/usr/bin/env python3
"""voice_resolve.py — resolve the symm-harness voice knobs from data/voice.yaml.

The voice is the front-stage register — how voice:render talks to the user. Knobs:

  register           soft | blunt | off   directness of the prose (off = neutral)
  persona            none + one name      surface FORM of the prose
  explanation_depth  1..3                 answer + one-line why … + reasoning sketch
  no_markdown        bool                 drop markdown from the answer

SCOPE-FENCE: these shape surface prose ONLY — never conclusion.json substance,
numbers, IDs, anchors, quotes, or the verdict. See rules/psych-front.md.

Tolerance: a missing file, missing key, out-of-range enum, wrong type, or corrupt
YAML all resolve to the default — load() NEVER raises. Env override SYMM_VOICE
points the loader at a scratch file (tests / ephemeral runs).
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402  — single root resolver

DEFAULTS = {
    "register": "off",
    "persona": "none",
    "explanation_depth": 2,
    "no_markdown": False,
}
_REGISTERS = {"soft", "blunt", "off"}


def _voice_file() -> Path:
    raw = os.environ.get("SYMM_VOICE")
    return Path(raw) if raw else paths.root() / "data" / "voice.yaml"


def load() -> dict:
    """Resolved knobs, always a full dict. Any failure → DEFAULTS (never raises)."""
    out = dict(DEFAULTS)
    try:
        p = _voice_file()
        if not p.is_file():
            return out
        import yaml  # lazy: absence degrades to defaults, not a crash
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return out
        reg = raw.get("register")
        if isinstance(reg, str) and reg.lower() in _REGISTERS:
            out["register"] = reg.lower()
        pers = raw.get("persona")
        if isinstance(pers, str) and pers.strip():
            out["persona"] = pers.strip()
        depth = raw.get("explanation_depth")
        if isinstance(depth, int) and not isinstance(depth, bool) and 1 <= depth <= 3:
            out["explanation_depth"] = depth
        nm = raw.get("no_markdown")
        if isinstance(nm, bool):
            out["no_markdown"] = nm
    except Exception:
        return dict(DEFAULTS)  # corrupt YAML / unreadable → canonical default
    return out


if __name__ == "__main__":  # debug: print the resolved knobs
    print(json.dumps(load(), ensure_ascii=False))
