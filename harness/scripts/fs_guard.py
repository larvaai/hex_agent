#!/usr/bin/env python3
"""fs_guard — script-path containment helper for harness script writes.

A harness script that resolves its target through `assert_under(path, zone)`
BEFORE opening the file cannot write outside the zone's declared root(s):
`..` traversal, symlink escape, and prefix look-alikes (`docs-extra`) are all
defeated by resolve-then-contain. The zone table is DATA-DRIVEN from
harness/data/ownership.yaml — adding a zone is a config edit, not a code edit.

Honesty caveat (carried from the source corpus, mirrors the helper's real
reach): this is a SCRIPT-path guard ONLY. It raises before a script write
lands outside its zone. It CANNOT stop a raw LLM `Write`, nor an LLM composing
a body directly to disk — those are governed by the prose contract + the
review/CI invariants, not by this assert. It is the harness disciplining its
own scripts, nothing more.

A missing or malformed ownership.yaml fails LOUD at import time: a guard that
silently degrades to "allow everything" protects nothing. Compliance hooks
importing this module turn that ImportError-time crash into exit 2 + guidance
via their fail-closed wrapper.
"""

import os
from pathlib import Path

_OWNERSHIP_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "ownership.yaml"


class FenceError(Exception):
    """Raised when a script-driven write would land outside its zone root(s)."""


def _ownership_path() -> Path:
    raw = os.environ.get("HARNESS_OWNERSHIP_FILE")
    return Path(raw) if raw else _OWNERSHIP_DEFAULT


def _load_zones() -> dict:
    """zone name → list of repo-root-relative root strings. Fails LOUD."""
    import yaml  # lazy so the error message below owns the missing-dep case too

    p = _ownership_path()
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(
            "fs_guard: ownership file missing at %s — the zone table is the "
            "guard's spine; restore harness/data/ownership.yaml" % p
        )
    zones = (raw or {}).get("zones") if isinstance(raw, dict) else None
    if not isinstance(zones, dict) or not zones:
        raise RuntimeError(
            "fs_guard: ownership file %s is malformed — expected a top-level "
            "`zones:` mapping of zone -> [roots]" % p
        )
    table = {}
    for zone, roots in zones.items():
        if isinstance(roots, str):
            roots = [roots]
        if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
            raise RuntimeError(
                "fs_guard: zone %r in %s must map to a list of path strings" % (zone, p)
            )
        table[str(zone)] = [r.strip() for r in roots if r.strip()]
    return table


# Loaded at import: a broken table must surface immediately, not at first write.
ZONES = _load_zones()


def allowed_roots(zone: str, root) -> list:
    """Resolved allowed write roots for `zone` under repo `root`.

    Zone roots are declared repo-relative; a declared root that resolves
    OUTSIDE the repo root (absolute path — pathlib drops `base` when joining
    one — or `../` traversal) would silently widen the fence to anywhere on
    the filesystem, so it raises instead of being honored."""
    if zone not in ZONES:
        raise FenceError(
            "unknown zone %r; known zones: %s" % (zone, sorted(ZONES))
        )
    base = Path(root).resolve()
    out = []
    for r in ZONES[zone]:
        resolved = (base / r).resolve()
        if resolved != base and not resolved.is_relative_to(base):
            raise FenceError(
                "zone %r declares root %r which resolves outside the repo "
                "root %s — zone roots must stay repo-relative; fix "
                "harness/data/ownership.yaml" % (zone, r, base)
            )
        out.append(resolved)
    return out


def assert_under(path, zone: str, root=None) -> Path:
    """Return the resolved `path` if contained under one of `zone`'s roots,
    else raise FenceError. Raises BEFORE any write, so a blocked target never
    touches disk.

    `path` may be relative to `root` or absolute; both are resolved
    (collapsing `..`, following symlinks on existing components). The boundary
    directory itself counts as in-fence. `root` defaults to harness_paths.root().
    """
    if root is None:
        import harness_paths
        root = harness_paths.root()
    roots = allowed_roots(zone, root)

    target = Path(path)
    if not target.is_absolute():
        target = Path(root) / target
    resolved = target.resolve(strict=False)

    for r in roots:
        if resolved == r or resolved.is_relative_to(r):
            return resolved

    pretty = ", ".join(str(r) for r in roots)
    raise FenceError(
        "refusing to write outside the %r zone: %s is not under any of [%s]"
        % (zone, resolved, pretty)
    )
