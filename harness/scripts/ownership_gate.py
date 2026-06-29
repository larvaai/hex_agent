#!/usr/bin/env python3
"""ownership_gate.py — declared-file-ownership engine + CLI.

The harness already carries the prose convention (in the team role reference):
each work-unit declares the file globs it may touch, no editing overlap, and an
ownership violation must STOP. Nothing enforced it. This gate gives that
convention deterministic teeth in two layers:

  * overlap   — pairwise advisory report. Two units whose declared file sets (or
                identical raw glob strings) collide are surfaced so a human can
                resequence the work. Advisory by design: the schedule call stays
                with people (the chosen model is convention + reconciliation, not
                RBAC), so `overlap` exits 0. `--strict` opts into exit 2.
  * reconcile — aggregate fail-closed check. Every changed file in the diff must
                be covered by some unit's declared globs; an unowned changed file
                is under-declaration → exit 2 with an actionable reason. This is
                the violation the convention says must STOP.

Reuse, not new abstractions: the loader mirrors team_config.load_team (resolve
off __file__, typed error naming file + key); identity via
hook_runtime.resolve_actor (attribution, not authentication); every run appends
to the same audit trace as the rest of the harness.

Documented cap (no silent truncation): `overlap` detects a collision only when
two units share a real on-disk file OR declare the identical glob string. Two
DIFFERENT patterns that would both match a not-yet-created file are not caught
until that file exists. Stated again in the `overlap` report footer.
"""

import argparse
import fnmatch
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.append(str(_HOOKS_DIR))
import hook_runtime  # noqa: E402
import trace_log  # noqa: E402

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import guard_policy  # noqa: E402

_OWNERSHIP_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "work-ownership.yaml"

_OVERLAP_CAP_NOTE = (
    "overlap detects same-string globs or shared on-disk files only; two "
    "different patterns matching a not-yet-created file are not caught until "
    "that file exists"
)


class OwnershipConfigError(Exception):
    """Raised when the ownership manifest is missing or malformed. Message names
    the file and the offending key so the fix is a config edit, not a debug
    session."""


# ------------------------------------------------------------ load_ownership ---

def load_ownership(path=None) -> dict:
    """Parse work-ownership.yaml → {units: [{id, role?, globs:[str]}]}.

    Missing file / non-mapping document / `units` not a list / a unit missing a
    non-empty `id` or `globs:[str]` / duplicate id all raise OwnershipConfigError
    naming the file and the offending key.
    """
    import yaml  # lazy: keep importable without PyYAML until actually used

    p = Path(path) if path else _OWNERSHIP_DEFAULT
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise OwnershipConfigError(
            "ownership manifest missing at %s — create it with at least:\n"
            "  units:\n    - id: example\n      globs: [\"harness/scripts/x_*.py\"]"
            % p
        )
    if not isinstance(raw, dict):
        raise OwnershipConfigError(
            "ownership manifest %s is malformed — expected a YAML mapping with a "
            "`units` list" % p
        )

    units_raw = raw.get("units")
    if not isinstance(units_raw, list):
        raise OwnershipConfigError(
            "key `units` in %s must be a list of work-units" % p
        )

    seen = set()
    units = []
    for idx, u in enumerate(units_raw):
        where = "units[%d]" % idx
        if not isinstance(u, dict):
            raise OwnershipConfigError(
                "%s in %s must be a mapping with `id` and `globs`" % (where, p)
            )
        uid = u.get("id")
        if not isinstance(uid, str) or not uid.strip():
            raise OwnershipConfigError(
                "%s in %s is missing a non-empty `id`" % (where, p)
            )
        if uid in seen:
            raise OwnershipConfigError(
                "duplicate unit `id` %r in %s — each work-unit id must be unique"
                % (uid, p)
            )
        seen.add(uid)
        globs = u.get("globs")
        if not isinstance(globs, list) or not globs or not all(
                isinstance(g, str) and g.strip() for g in globs):
            raise OwnershipConfigError(
                "unit %r in %s must have `globs` as a non-empty list of glob "
                "strings" % (uid, p)
            )
        unit = {"id": uid.strip(), "globs": [g.strip() for g in globs]}
        role = u.get("role")
        if isinstance(role, str) and role.strip():
            unit["role"] = role.strip()
        owner = u.get("owner")
        if isinstance(owner, str) and owner.strip():
            unit["owner"] = owner.strip()
        units.append(unit)

    return {"units": units}


# --------------------------------------------------------------- matching ---

def match_any(path, globs) -> bool:
    """True if `path` matches any glob. fnmatch semantics: `*` spans `/`, so a
    pattern like `dir/*` owns the whole subtree under dir/ (documented)."""
    return any(fnmatch.fnmatch(path, g) for g in globs)


def expand(globs, root) -> set:
    """Expand globs against the working tree at `root`, returning repo-relative
    POSIX paths of real files. `**` is honored (recursive=True). A hit whose
    RESOLVED path escapes `root` (reached via a symlink) is skipped — it is not a
    file physically in the repo, so attributing it to an owned path would reason
    over content the repo does not actually contain."""
    root = Path(root)
    rr = root.resolve()
    out = set()
    for pat in globs:
        for hit in glob.glob(str(root / pat), recursive=True):
            hp = Path(hit)
            if not hp.is_file():
                continue
            try:
                hp.resolve().relative_to(rr)  # containment: real path under root
            except ValueError:
                continue  # symlink-escaped — not in the repo
            out.add(hp.relative_to(root).as_posix())
    return out


def compute_overlap(units, root) -> list:
    """Pairwise overlaps between units. A pair overlaps when their expanded
    file-sets intersect OR their raw glob strings intersect (the latter catches
    "both declared the same pattern" before the file exists). Deterministic,
    sorted output: pairs in input order, shared lists sorted."""
    expanded = {u["id"]: expand(u["globs"], root) for u in units}
    raw = {u["id"]: set(u["globs"]) for u in units}
    results = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            a, b = units[i]["id"], units[j]["id"]
            shared = sorted(expanded[a] & expanded[b])
            shared_globs = sorted(raw[a] & raw[b])
            if shared or shared_globs:
                results.append({
                    "a": a, "b": b,
                    "shared": shared,
                    "shared_globs": shared_globs,
                })
    return results


def reconcile(changed_files, units):
    """Aggregate check: returns None if every changed file is covered by some
    unit's globs; otherwise a block-reason string listing each unowned file."""
    all_globs = [g for u in units for g in u["globs"]]
    unowned = sorted(f for f in changed_files if not match_any(f, all_globs))
    if not unowned:
        return None
    return (
        "ownership violation: %d changed file(s) declared by no work-unit — "
        "declare them in the ownership manifest before changing them:\n  %s"
        % (len(unowned), "\n  ".join(unowned))
    )


def reconcile_actor(changed_files, units, actor):
    """Per-actor poaching check: returns None when `actor` may touch every
    changed file, otherwise a block-reason naming each file that lies in
    ANOTHER declared owner's lane.

    Only declared owners are policed: an actor that owns no unit is ungoverned
    (returns None), so a manifest with no `owner:` fields — or a contributor
    not yet assigned a lane — stays permissive. The agent suffix collapses to
    the person (a persona of the same human is not a separate owner). A file in
    NO owner's lane is reconcile()'s under-declaration job, not a poach."""
    from plan_approval import normalize_actor

    me = normalize_actor(actor)
    owned = {}  # owner -> [globs]
    for u in units:
        owner = u.get("owner")
        if not owner:
            continue
        owned.setdefault(normalize_actor(owner), []).extend(u["globs"])
    if me not in owned:
        return None  # actor owns nothing → not policed
    my_globs = owned[me]

    poached = {}  # file -> owner whose lane it falls in
    for f in sorted(set(changed_files)):
        if match_any(f, my_globs):
            continue  # in my own lane
        for owner, globs in owned.items():
            if owner != me and match_any(f, globs):
                poached[f] = owner
                break
    if not poached:
        return None
    listing = "\n  ".join("%s (owner %s)" % (f, poached[f])
                          for f in sorted(poached))
    return (
        "ownership violation: %d changed file(s) in another owner's declared "
        "lane — coordinate a handoff before touching them:\n  %s"
        % (len(poached), listing)
    )


# --------------------------------------------------------------------- CLI ---

def _changed_from_git() -> list:
    """Collect changed paths from the working tree + index (uncommitted +
    staged). Best-effort: a git failure yields an empty list."""
    paths = set()
    for extra in (["HEAD"], ["--cached"]):
        try:
            out = subprocess.run(
                ["git", "diff", "--name-only"] + extra,
                capture_output=True, text=True, timeout=30)
        except Exception:  # noqa: BLE001 — no git / not a repo → nothing to add
            continue
        if out.returncode == 0:
            paths.update(l.strip() for l in out.stdout.splitlines() if l.strip())
    return sorted(paths)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Declared-file-ownership gate (overlap report + diff "
                    "reconciliation).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ov = sub.add_parser(
        "overlap", help="advisory report of units declaring colliding files")
    p_ov.add_argument("--manifest", required=True)
    p_ov.add_argument("--root", default=".",
                      help="working-tree root for glob expansion (default: .)")
    p_ov.add_argument("--strict", action="store_true",
                      help="exit 2 if any overlap is found (default: exit 0)")

    p_rec = sub.add_parser(
        "reconcile", help="fail-closed: every changed file must be declared")
    p_rec.add_argument("--manifest", required=True)
    p_rec.add_argument("--changed", nargs="*", default=None,
                       help="explicit changed paths to reconcile")
    p_rec.add_argument("--changed-from-git", action="store_true",
                       help="collect changed paths via git diff (working + index)")

    args = ap.parse_args(argv)

    try:
        cfg = load_ownership(args.manifest)
    except OwnershipConfigError as e:
        sys.stderr.write(str(e) + "\n")
        return 2
    units = cfg["units"]

    if args.cmd == "overlap":
        overlaps = compute_overlap(units, args.root)
        print(json.dumps(
            {"overlaps": overlaps, "cap": _OVERLAP_CAP_NOTE},
            ensure_ascii=False))
        trace_log.append_event(
            "ownership_gate", "overlap_report", actor=hook_runtime.resolve_actor(),
            status="BLOCKED" if (args.strict and overlaps) else "PASS",
            note="%d overlap(s)" % len(overlaps))
        if args.strict and overlaps:
            return 2
        return 0

    # reconcile
    if args.changed_from_git:
        changed = _changed_from_git()
    else:
        changed = args.changed or []
    actor = hook_runtime.resolve_actor()
    reason = reconcile(changed, units)
    # Funnel the reason through the unified posture: block returns it (we
    # write + exit 2), warn/off downgrade to advisory/silent (gate handles the
    # stderr + audit, we exit 0). reason=None is a genuine pass.
    gated = guard_policy.gate(
        "ownership_reconcile", reason, hook="ownership_gate", actor=actor)
    if gated:
        trace_log.append_event(
            "ownership_gate", "reconcile_block", actor=actor,
            status="BLOCKED", note=gated)
        sys.stderr.write(gated + "\n")
        return 2
    if reason is None:
        trace_log.append_event(
            "ownership_gate", "reconcile_pass", actor=actor,
            status="PASS", note="%d changed file(s) all declared" % len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
