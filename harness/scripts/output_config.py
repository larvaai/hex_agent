#!/usr/bin/env python3
"""output_config.py — loader for harness/data/output.yaml (generated-prose language).

Instruction files (SKILL.md, references, rules, CLAUDE.md) are English. This
setting picks the language of the prose the harness GENERATES — reports, docs,
plan narration — and whether the humanizer rule is applied. The harness default
is Vietnamese: English instructions in, human-friendly Vietnamese reports out.

One shared loader so every producer reads the language identically.
DELIBERATELY no env override: output.yaml is tracked config — a language change
is a git-visible diff, never a hidden in-session flip. The only load path is the
tracked file next to the repo's data dir (resolved off __file__, never CWD).
Callers that need a different file (tests) pass `path=` explicitly.
"""

from pathlib import Path

_OUTPUT_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "output.yaml"

VALID_LANGUAGES = {"en", "vi"}


class OutputConfigError(Exception):
    """Raised when output.yaml is missing or malformed. Message names the file
    and the offending key so the fix is a config edit, not a debug session."""


def load_output(path=None) -> dict:
    """Parse output.yaml → {language, humanize}.

    Missing file / non-mapping document / out-of-enum language raise
    OutputConfigError naming file + key. A missing `humanize` defaults to True
    (anti-AI-tell cleanup is on unless a human turns it off).
    """
    import yaml  # lazy: keep importable without PyYAML until actually used

    p = Path(path) if path else _OUTPUT_DEFAULT
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise OutputConfigError(
            "output config missing at %s — create it with at least:\n"
            "  language: vi\n  humanize: true" % p
        )
    if not isinstance(raw, dict):
        raise OutputConfigError(
            "output config %s is malformed — expected a YAML mapping with keys "
            "`language`, `humanize`" % p
        )

    lang = raw.get("language", "vi")
    if lang not in VALID_LANGUAGES:
        raise OutputConfigError(
            "key `language` in %s must be one of %s (got %r)"
            % (p, sorted(VALID_LANGUAGES), lang)
        )

    humanize = raw.get("humanize", True)
    if not isinstance(humanize, bool):
        raise OutputConfigError(
            "key `humanize` in %s must be true or false (got %r)" % (p, humanize)
        )

    return {"language": lang, "humanize": humanize}


def language(path=None) -> str:
    """Convenience: the configured output language (en|vi)."""
    return load_output(path=path)["language"]


def _preserved_header(path: Path) -> str:
    """Leading comment/blank header kept across a CLI write (shared extractor in
    config_io). Missing file → a minimal header."""
    import config_io
    return config_io.leading_comment_block(
        path, "# output.yaml — language + humanize for GENERATED prose.\n")


def save_output(updates: dict, path=None) -> Path:
    """Validate + write output.yaml, merging ``updates`` over the current values
    (every unspecified key is preserved). Raises OutputConfigError on an unknown
    key / bad language / non-bool humanize BEFORE any write, so the file stays
    canonical. The header comment block is preserved."""
    p = Path(path) if path else _OUTPUT_DEFAULT
    current = load_output(path=p)
    for key in updates:
        if key not in ("language", "humanize"):
            raise OutputConfigError(
                "unknown output knob %r — valid: language, humanize" % key)
    merged = dict(current)
    merged.update(updates)
    if merged["language"] not in VALID_LANGUAGES:
        raise OutputConfigError(
            "key `language` must be one of %s (got %r)"
            % (sorted(VALID_LANGUAGES), merged["language"]))
    if not isinstance(merged["humanize"], bool):
        raise OutputConfigError(
            "key `humanize` must be true or false (got %r)" % merged["humanize"])
    body = "language: %s\nhumanize: %s\n" % (
        merged["language"], "true" if merged["humanize"] else "false")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_preserved_header(p) + body, encoding="utf-8")
    return p


def _coerce(key: str, value: str):
    if key == "humanize":
        low = value.strip().lower()
        if low in ("true", "yes", "on", "1"):
            return True
        if low in ("false", "no", "off", "0"):
            return False
        raise OutputConfigError("humanize must be true/false (got %r)" % value)
    return value


def main(argv=None) -> int:
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="read/write output.yaml (generated-prose language)")
    ap.add_argument("--file", default=None,
                    help="explicit output.yaml path (default: shipped tracked file)")
    ap.add_argument("--set", dest="sets", action="append", metavar="KEY=VALUE",
                    help="write a knob (language|humanize); repeatable")
    args = ap.parse_args(argv)
    path = args.file
    if not args.sets:
        import json
        print(json.dumps(load_output(path=path), indent=2, ensure_ascii=False))
        return 0
    updates = {}
    for pair in args.sets:
        if "=" not in pair:
            sys.stderr.write("--set expects KEY=VALUE, got %r\n" % pair)
            return 2
        key, value = pair.split("=", 1)
        try:
            updates[key] = _coerce(key, value)
        except OutputConfigError as e:
            sys.stderr.write("%s\n" % e)
            return 2
    try:
        p = save_output(updates, path=path)
    except OutputConfigError as e:
        sys.stderr.write("OutputConfigError: %s\n" % e)
        return 1
    print("saved output → %s" % p)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
