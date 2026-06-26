#!/usr/bin/env python3
"""Decomposition migrate engine — relocate non-spine skills + rewrite every reference.

The 2.0.0 decomposition splits the single core `hs` plugin into a spine (13 always-on
SDLC skills, kept in `hs`) plus six themed sibling plugins. This tool moves each
non-spine skill dir into its themed plugin and rewrites EVERY reference to it across
the repo, in all four forms:

  1. slash invocation   /hs:<s>            -> /hs-<g>:<s>
  2. bare invocation     hs:<s>            ->  hs-<g>:<s>      (the dominant form)
  3. frontmatter name    name: hs:<s>      ->  name: hs-<g>:<s>   (a bare-form case)
  4. path                hs/skills/<s>     ->  hs-<g>/skills/<s>

Spine skills (group "hs") and already-prefixed refs (hs-viz:, hs-devops:, …) are never
touched. The generated manifest and the entire plans/ tree are out of scope — manifest
is rebuilt by build_manifest, and plans/ is frozen history plus the drift-sensitive
active plan (rewriting it would change a plan_hash and trip the drift gate).

Idempotent: a second run is a no-op (already-moved dirs are skipped; already-prefixed
refs no longer match). `--check` independently scans for any surviving old-form ref.

This engine is the core of `hs-cli migrate` (wrapped in a later phase).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a harness dep
    yaml = None

_SCRIPT = Path(__file__).resolve()
_DEFAULT_ROOT = _SCRIPT.parents[2]

# Top-level paths never content-rewritten. plans/ is frozen+drift; manifest is
# regenerated; state/git/caches are not source.
_EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".mypy_cache"}
_EXCLUDE_REL = {
    "harness/manifest.json",
    "harness/data/decomposition-rename-map.json",  # generated; intentionally keeps old names
    "docs/decomposition-migration.md",  # user-facing old->new table; old column must survive
    "GOAL.md",  # program tracker; records the old->new transition, old names are intentional
    "CHANGELOG.md",  # release history; documents old->new renames, both names are intentional
    "harness/state",
    "plans",
    ".claude/plugins",
}
# Only these extensions are treated as rewritable text; everything else is left alone.
_TEXT_SUFFIXES = {
    ".md", ".py", ".yaml", ".yml", ".json", ".txt", ".sh", ".toml", ".cfg",
    ".ini", ".gitkeep", "",
    # JS/TS family — ported skills ship these and they can carry route references
    ".ts", ".tsx", ".js", ".jsx", ".cjs", ".mjs",
}


# --------------------------------------------------------------------------- map

def load_map(path: Path) -> dict[str, str]:
    """skill -> group ("hs" for spine). Reads decomposition-map.yaml."""
    if yaml is None:
        raise RuntimeError("pyyaml required")
    data = yaml.safe_load(Path(path).read_text()) or {}
    skills = data.get("skills", {})
    if not isinstance(skills, dict) or not skills:
        raise ValueError(f"no skills declared in {path}")
    return {str(k): str(v) for k, v in skills.items()}


def spine_skills(m: dict[str, str]) -> list[str]:
    return [s for s, g in m.items() if g == "hs"]


def non_spine_skills(m: dict[str, str]) -> dict[str, str]:
    """{skill: group} for every skill that moves out of the spine."""
    return {s: g for s, g in m.items() if g != "hs"}


# ----------------------------------------------------------------- text rewrite

def _alt(names) -> str:
    # longest-first so the alternation never prefers a shorter prefix of a longer name
    return "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))


def _invoke_re(non_spine: dict[str, str]) -> re.Pattern:
    # (?<![\w-/]) rejects a word-char, '-' or '/' before hs (so hs-viz:, xhs: and
    # the `//hs:` inside a URL like https://hs:skill never match). A real slash-
    # command `/hs:s` or bare `hs:s` is preceded by start/space, so it still fires.
    # optional leading '/' is preserved. trailing (?![\w-]) is the name boundary
    # (so hs:zzfoo does not fire inside hs:zzfoobar).
    return re.compile(rf"(?<![\w\-/])(/?)hs:({_alt(non_spine)})(?![\w-])")


def _path_re(non_spine: dict[str, str]) -> re.Pattern:
    return re.compile(rf"(?<![\w-])hs/skills/({_alt(non_spine)})(?![\w-])")


def rewrite_text(text: str, non_spine: dict[str, str]) -> str:
    """Apply all four reference rewrites. Frontmatter `name:` is a bare-form case."""
    if not non_spine:
        return text
    inv = _invoke_re(non_spine)
    pth = _path_re(non_spine)
    text = inv.sub(lambda m: f"{m.group(1)}hs-{non_spine[m.group(2)]}:{m.group(2)}", text)
    text = pth.sub(lambda m: f"hs-{non_spine[m.group(1)]}/skills/{m.group(1)}", text)
    return text


def _check_res(non_spine: dict[str, str]) -> tuple[re.Pattern, re.Pattern]:
    # Independently constructed alternation detectors (NOT the rewrite Pattern objects),
    # so a rewrite-regex bug cannot blind the checker — but combined into one scan each
    # for speed (per-name finditer over the whole tree was minutes-slow).
    alt = _alt(non_spine)
    inv = re.compile(rf"(?<![\w\-/])/?hs:({alt})(?![\w-])")
    pth = re.compile(rf"(?<![\w-])hs/skills/({alt})(?![\w-])")
    return inv, pth


def find_dangling(text: str, non_spine: dict[str, str]) -> list[tuple[str, str, str]]:
    """Independent old-form detector (NOT the rewrite regex) — (kind, skill, match)."""
    if not non_spine:
        return []
    inv, pth = _check_res(non_spine)
    hits: list[tuple[str, str, str]] = []
    for m in inv.finditer(text):
        hits.append(("invoke", m.group(1), m.group(0)))
    for m in pth.finditer(text):
        hits.append(("path", m.group(1), m.group(0)))
    return hits


# ----------------------------------------------------------------- scope / walk

def _excluded(rel: Path, root: Path) -> bool:
    parts = rel.parts
    if any(p in _EXCLUDE_DIRS for p in parts):
        return True
    rel_str = rel.as_posix()
    for ex in _EXCLUDE_REL:
        if rel_str == ex or rel_str.startswith(ex + "/"):
            return True
    return False


def iter_text_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if _excluded(rel, root):
            continue
        if p.suffix not in _TEXT_SUFFIXES:
            continue
        yield p


# --------------------------------------------------------------------- dir move

def plan_moves(root: Path, non_spine: dict[str, str]) -> list[tuple[Path, Path]]:
    moves = []
    for skill, group in non_spine.items():
        src = root / "harness/plugins/hs/skills" / skill
        dst = root / f"harness/plugins/hs-{group}/skills" / skill
        if src.is_dir() and not dst.exists():
            moves.append((src, dst))
    return moves


def move_skill_dirs(root: Path, non_spine: dict[str, str]) -> list[tuple[Path, Path]]:
    done = []
    for src, dst in plan_moves(root, non_spine):
        # Re-check at move time: plan_moves snapshots the source set, so a source
        # that disappeared since (e.g. another migrate run already moved it) is
        # skipped rather than crashing the run.
        if not src.is_dir() or dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        done.append((src, dst))
    return done


# ------------------------------------------------------------------ rename map

def build_rename_map(m: dict[str, str]) -> dict:
    ns = non_spine_skills(m)
    moved = {
        s: {
            "group": g,
            "old_invoke": f"hs:{s}",
            "new_invoke": f"hs-{g}:{s}",
            "old_dir": f"harness/plugins/hs/skills/{s}",
            "new_dir": f"harness/plugins/hs-{g}/skills/{s}",
        }
        for s, g in ns.items()
    }
    return {
        "generated_by": "migrate_decomposition.py",
        "spine": sorted(spine_skills(m)),
        "moved": moved,
    }


# ------------------------------------------------------------------------- run

def run_migrate(
    root: Path | str = _DEFAULT_ROOT,
    *,
    dry_run: bool = False,
    do_check: bool = False,
    map_path: Path | None = None,
    write_rename_map: bool = True,
) -> int:
    root = Path(root)
    map_path = Path(map_path) if map_path else root / "harness/data/decomposition-map.yaml"
    m = load_map(map_path)
    ns = non_spine_skills(m)

    if do_check:
        inv_re, pth_re = _check_res(ns) if ns else (None, None)
        dangling: list[str] = []
        for p in iter_text_files(root):
            try:
                txt = p.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            if inv_re is None:
                continue
            for m in inv_re.finditer(txt):
                dangling.append(f"{p.relative_to(root)}: invoke {m.group(0)}")
            for m in pth_re.finditer(txt):
                dangling.append(f"{p.relative_to(root)}: path {m.group(0)}")
        if dangling:
            print(f"DANGLING ({len(dangling)}) old-form refs:", file=sys.stderr)
            for d in dangling[:50]:
                print(f"  {d}", file=sys.stderr)
            return 1
        print("check: 0 dangling old-form refs")
        return 0

    if dry_run:
        moves = plan_moves(root, ns)
        changed = 0
        for p in iter_text_files(root):
            try:
                txt = p.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            if rewrite_text(txt, ns) != txt:
                changed += 1
        print(f"dry-run: {len(moves)} dir moves, {changed} files would be rewritten")
        for src, dst in moves:
            print(f"  move {src.relative_to(root)} -> {dst.relative_to(root)}")
        return 0

    # real run: move dirs first so moved SKILL.md files are rewritten in place
    move_skill_dirs(root, ns)
    for p in iter_text_files(root):
        try:
            txt = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        new = rewrite_text(txt, ns)
        if new != txt:
            p.write_text(new)

    if write_rename_map:
        out = root / "harness/data/decomposition-rename-map.json"
        out.write_text(json.dumps(build_rename_map(m), indent=2, sort_keys=True) + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="decomposition migrate engine")
    ap.add_argument("--root", default=str(_DEFAULT_ROOT))
    ap.add_argument("--map", dest="map_path", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="scan for surviving old-form refs; exit!=0 if any")
    ap.add_argument("--no-rename-map", action="store_true")
    a = ap.parse_args(argv)
    return run_migrate(
        root=a.root,
        dry_run=a.dry_run,
        do_check=a.check,
        map_path=a.map_path,
        write_rename_map=not a.no_rename_map,
    )


if __name__ == "__main__":
    raise SystemExit(main())
