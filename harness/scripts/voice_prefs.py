#!/usr/bin/env python3
"""voice_prefs.py — resolve the terminal-voice knobs from terminal-voice.yaml.

The terminal voice is the harness's CONVERSATIONAL register in the terminal —
how the assistant talks to the user while working — NOT the language or candor
of any written artifact. Knobs:

  terminal_voice_level   0..5   explanation depth/format of terminal answers (5 = full)
  persona        none + 13 catalog ids   the surface FORM of terminal prose
                       (the 13 ids are added in phase 3; phase 1 ships `none`)
  voice_level    1..9   harshness/bluntness register on the terminal (5 = blunt,
                       no profanity; 6-9 escalate). The universal-harm floor and
                       the scope-fence are enforced in harness/rules/terminal-voice.md,
                       NOT here — this module stores closed-enum values, judges nothing.
  no_markdown    bool   drop markdown formatting from terminal answers

SCOPE-FENCE: these knobs shape terminal SURFACE prose only. They never alter
code, generated docs/reports, commits, evidence, or any gate decision; and they
do NOT control an artifact's own designed voice (the journal-writer's brutal
candor, the hs-think:critique neutral tone). See harness/rules/terminal-voice.md.

Tolerance ported from product-spec preferences.py: a missing file, missing key,
out-of-range enum, wrong-typed value, or corrupt YAML all resolve to the default
and load() NEVER raises. The write path (save) validates the closed enums and
raises VoicePrefsError so the on-disk file stays canonical for the next read.

Loader idiom mirrors guard_policy: resolve off __file__, honor an env override
HARNESS_TERMINAL_VOICE so tests/ephemeral runs point at a scratch file; the
committed default lives next to the data dir.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_VOICE_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "terminal-voice.yaml"


class VoicePrefsError(ValueError):
    """Raised by save() when a value violates a closed enum (write-path only).

    The read path is deliberately tolerant — load() never raises — but the write
    path validates so the on-disk file stays canonical for the next read."""


# The single authoritative home for the terminal-voice defaults. Adding a knob
# here (with its default) is the ONLY place a new knob is registered. Phase 4
# adds the interview-rigor knobs to these same tables.
DEFAULTS: Dict[str, Any] = {
    "terminal_voice_level": 5,
    "persona": "none",
    "voice_level": 5,
    "no_markdown": False,
    # Interview-rigor knobs (ported from product-spec preferences.py). LLM-side
    # guidance, not script gates: surfaced in the SessionStart additionalContext
    # and read by hs:plan / hs-research:discover / hs-think:brainstorm. Neutral default
    # `standard` so a fresh project is neither under- nor over-questioned.
    "interview_rigor": "standard",   # depth of challenge / gap-probing (NOT verbosity)
    "action_prompting": "standard",  # density of suggested next-actions at turn ends
    "detail_level": "standard",      # interview/turn verbosity — NOT report length (output.yaml)
    # Audience-adaptation axis (ported output-style profiles). UNLIKE every other
    # knob here this is NOT scope-fenced: it adapts the deliverable itself (prose
    # AND code — comment density, verbosity, analogies) to the reader's coding
    # expertise. Default None = off (no shaping); 0=beginner … 5=expert.
    "output_style": None,
}

# The persona catalog ids. The id strings live here (the enum's source); the
# one-line style descriptions + groups live in harness/rules/terminal-voice.md
# and the /hs-meta:voice menu — a parity test keeps the three homes from drifting.
# work-group personas are default-eligible; fun-group are opt-in only. persona
# sets the surface FORM of terminal prose; voice_level sets the harshness inside.
WORK_PERSONAS = (
    "military", "reality-check", "git-log", "socratic",
    "bluf", "rubber-duck", "feynman", "first-principles",
)
FUN_PERSONAS = ("caveman", "yoda", "pirate", "80s-hacker", "dad-joke")
PERSONAS = ("none",) + WORK_PERSONAS + FUN_PERSONAS

# Closed enums per scalar key. A value outside its set is treated as absent
# (read path: fall back to default; write path: VoicePrefsError).
ENUMS: Dict[str, frozenset] = {
    "terminal_voice_level": frozenset(range(0, 6)),   # 0..5
    "persona": frozenset(PERSONAS),           # none + 13 catalog ids
    "voice_level": frozenset(range(1, 10)),   # 1..9
    "interview_rigor": frozenset({"light", "standard", "deep"}),
    "action_prompting": frozenset({"minimal", "standard", "proactive"}),
    "detail_level": frozenset({"concise", "standard", "verbose"}),
    "output_style": frozenset({None}) | frozenset(range(0, 6)),  # off (None) or 0..5
}

# Output-style audience profiles (ported). The full directives live in
# harness/data/output-styles/coding-level-<n>-<name>.md; the short ESSENCE below
# is the always-injected steer, with the file available on demand for the full
# MANDATORY rules. NAMES is the single source for the level<->name mapping.
OUTPUT_STYLE_NAMES: Dict[int, str] = {
    0: "eli5", 1: "junior", 2: "mid", 3: "senior", 4: "lead", 5: "god",
}
OUTPUT_STYLE_ESSENCE: Dict[int, str] = {
    0: "reader is an absolute beginner — real-world analogies, define every term, "
       "comment every line, 5-10 line code blocks, show expected output, end with a check-in",
    1: "reader is a junior (0-2y) — explain the why before the how, name the patterns, "
       "moderate comments, link to docs, encourage",
    2: "reader is mid-level (3-5y) — system thinking and trade-offs, professional patterns, "
       "less hand-holding, brief rationale",
    3: "reader is senior (5-8y) — concise; lead with trade-offs, edge cases, operational "
       "concerns; skip the basics",
    4: "reader is a lead (8-15y) — strategic framing, risk assessment, business alignment, brevity",
    5: "reader is an expert (15y+) — terse, code-first, zero explanation unless asked; "
       "challenge a flawed approach as a peer",
}


def output_style_profile(level):
    """Resolve an output_style level to its profile, or None when off.

    Returns {"level", "name", "essence", "file"} for 0..5; None for None/unknown.
    `file` points at the full profile doc under harness/data/output-styles/.
    """
    if level is None or level not in OUTPUT_STYLE_NAMES:
        return None
    name = OUTPUT_STYLE_NAMES[level]
    f = Path(__file__).resolve().parent.parent / "data" / "output-styles" / (
        "coding-level-%d-%s.md" % (level, name))
    return {"level": level, "name": name, "essence": OUTPUT_STYLE_ESSENCE[level], "file": str(f)}

# Keys whose canonical type is bool: validated by TYPE, not membership. Kept
# out of ENUMS because `True == 1` / `False == 0` in Python would let a bool
# satisfy an int enum (and an int satisfy a bool), so bool is handled apart.
_BOOL_KEYS: frozenset = frozenset({"no_markdown"})


# Dev-only override discovery — TERMINAL VOICE ONLY. A gitignored
# .harness-dev/terminal-voice.yaml at the repo root lets a dev run a different
# CONVERSATIONAL posture without editing the committed default (which must ship
# safe) and without an env var or session restart — the file is read live on
# every load(). Resolved AFTER the env seam and BEFORE the shipped default.
#
# Deliberately limited to the terminal voice, which is scope-fenced and never
# changes a gate verdict. Gate-AFFECTING config (guard_policy, artifact_check
# stage policy) is NOT file-discovered: it stays env-bound so the pre-push hook's
# HARNESS_* env scrub can neutralize a local override and the real-push gate
# always reads the tracked file (see test_pre_push_env_scrub.py).
_DEV_OVERRIDE = (".harness-dev", "terminal-voice.yaml")


def _repo_root() -> Path:
    """Repo root for locating the dev override. Honors HARNESS_ROOT (the same
    test / odd-layout seam harness_paths uses), else derives from this file's
    location (harness/scripts/ -> repo root)."""
    raw = os.environ.get("HARNESS_ROOT")
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[2]


def _dev_override_path() -> Optional[Path]:
    """The gitignored repo-root dev override if present, else None."""
    cand = _repo_root().joinpath(*_DEV_OVERRIDE)
    return cand if cand.is_file() else None


def _voice_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    raw = os.environ.get("HARNESS_TERMINAL_VOICE")
    if raw:
        return Path(raw)
    dev = _dev_override_path()
    if dev is not None:
        return dev
    return _VOICE_DEFAULT


def voice_path(path=None) -> Path:
    """The resolved config path (explicit arg > HARNESS_TERMINAL_VOICE > shipped
    default). Public so the quick-switch skill writes the same file load reads."""
    return _voice_path(path)


def load(path=None) -> Dict[str, Any]:
    """Return the resolved terminal-voice knobs: every key present, defaults
    filled. A missing file, missing key, out-of-range enum, wrong-typed value,
    or unparseable YAML all degrade to defaults — this function never raises."""
    import yaml  # lazy: keep importable without PyYAML until actually used

    resolved = dict(DEFAULTS)
    p = _voice_path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, yaml.YAMLError):
        return resolved
    if not isinstance(raw, dict):
        # A scalar / list top-level (corrupt or hand-mangled) is not a mapping;
        # ignore it wholesale rather than guess.
        return resolved

    for key in DEFAULTS:
        if key not in raw:
            continue
        value = raw[key]
        if key in _BOOL_KEYS:
            # Accept only a real bool; a hand-edited non-bool is ignored.
            if isinstance(value, bool):
                resolved[key] = value
        elif key in ENUMS:
            # Reject bool explicitly: True/False would otherwise match an int
            # enum's 1/0. A level is an int, never a bool.
            if not isinstance(value, bool) and value in ENUMS[key]:
                resolved[key] = value
            # else: leave the default (defensive against a hand-edited typo)
        else:
            resolved[key] = value
    return resolved


def _preserved_header(p) -> str:
    """Keep terminal-voice.yaml's documentation header across a --set rewrite,
    mirroring the sibling config CLIs (output/guard/team via
    config_io.leading_comment_block) — the header is the only in-file record of
    the knob ranges, so a rewrite must not destroy it. Missing file → a minimal
    header."""
    import config_io
    return config_io.leading_comment_block(
        p, "# terminal-voice.yaml — conversational register for TERMINAL prose "
           "only (scope-fenced; never code/gates/evidence).\n")


def save(prefs: Dict[str, Any], path=None) -> Path:
    """Validate + write terminal-voice.yaml.

    Only known keys are persisted (unknown keys are dropped — the schema is
    closed). A value outside its closed enum, or a non-bool for a bool key,
    raises VoicePrefsError before any write. The leading comment header is
    preserved across the rewrite (matching the sibling config CLIs)."""
    import yaml

    out: Dict[str, Any] = {}
    for key, value in prefs.items():
        if key not in DEFAULTS:
            continue  # drop unknown keys — schema is closed
        if key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise VoicePrefsError(
                    f"terminal-voice {key!r}={value!r} must be true or false")
        elif key in ENUMS:
            if isinstance(value, bool) or value not in ENUMS[key]:
                raise VoicePrefsError(
                    f"terminal-voice {key!r}={value!r} is not one of "
                    f"{sorted(ENUMS[key], key=lambda v: (v is not None, v))}")
        out[key] = value

    p = _voice_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    header = _preserved_header(p)  # read BEFORE opening 'w' truncates the file
    body = yaml.safe_dump(out, sort_keys=True, allow_unicode=True,
                          default_flow_style=False)
    # newline='' keeps the file byte-stable (LF) across platforms.
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(header + body)
    return p


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="read/write the terminal-voice knobs (terminal-voice.yaml)")
    ap.add_argument(
        "--set",
        dest="sets",
        action="append",
        metavar="KEY=VALUE",
        help="write a known knob (repeatable). load->merge->save: every other "
             "committed knob is preserved. An unknown key OR a value outside the "
             "key's closed enum exits non-zero, writing nothing. Digit strings "
             "coerce to int for level keys; true/false to bool for no_markdown.",
    )
    args = ap.parse_args()

    if not args.sets:
        print(json.dumps(load(), indent=2, ensure_ascii=False))
        return 0

    prefs = load()
    for pair in args.sets:
        if "=" not in pair:
            print(f"--set: expected KEY=VALUE, got {pair!r}", file=sys.stderr)
            return 2
        key, value = pair.split("=", 1)  # split on FIRST '=' only
        if key not in DEFAULTS:
            # save() silently drops unknown keys; reject here so a typo is a
            # loud non-zero exit, not a "saved" no-op the user would trust.
            print(f"--set: unknown knob {key!r}", file=sys.stderr)
            return 2
        if key in _BOOL_KEYS:
            low = value.strip().lower()
            if low in ("true", "yes", "on", "1"):
                value = True
            elif low in ("false", "no", "off", "0"):
                value = False
            else:
                print(f"--set: knob {key!r} must be true/false; got {value!r}",
                      file=sys.stderr)
                return 2
        elif None in ENUMS.get(key, frozenset()):
            # off-able knob (e.g. output_style): off/none -> None, digits -> int
            low = value.strip().lower()
            if low in ("off", "none", "null", ""):
                value = None
            elif low.lstrip("-").isdigit():
                value = int(value)
        elif isinstance(DEFAULTS[key], int) and value.lstrip("-").isdigit():
            value = int(value)
        prefs[key] = value

    try:
        p = save(prefs)
    except VoicePrefsError as exc:
        print(f"VoicePrefsError: {exc}", file=sys.stderr)
        return 1
    print(f"saved terminal-voice → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
