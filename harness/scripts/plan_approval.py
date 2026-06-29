#!/usr/bin/env python3
"""plan_approval.py — write the plan-approval artifact (role-checked).

Role-consistency check on ATTRIBUTION — not authentication. Actor strings
are env-derived and spoofable by design; this check raises the PRICE of
"agent writes its own PASS" (the reviewer must be in the tracked roster and
normalize to a different user than the author), it does not prove identity.
normalize_actor collapses `user:<u>/agent:<a>` personas to `user:<u>` so two
personas of one person cannot cross-approve.

plan_hash pins the plan's NORMALIZED content: YAML frontmatter is stripped
from every file and the `## Phases` section is stripped from plan.md before
hashing. Those are exactly the two regions the cook workflow legitimately
mutates after approval (status flips, phase table updates) — hashing them
verbatim would go stale on every run and train reviewers to rubber-stamp.
Trade-off, on purpose: status metadata is not drift-guarded; the body (the
thing approval is about) is. Any other edit ⇒ re-approve.

The artifact is the only in-session write path for plans/*/artifacts/
plan-approval.json (the file sits on the write-guard list in installed
repos), and this CLI refuses to write the moment the role rule fails.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import fs_guard  # noqa: E402
import harness_paths  # noqa: E402
import team_config  # noqa: E402

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.append(str(_HOOKS_DIR))
import hook_runtime  # noqa: E402
import trace_log  # noqa: E402

SCHEMA = "plan-approval/v1"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?^(?:---|\.\.\.)\s*$\n?",
                             re.MULTILINE | re.DOTALL)
_PHASES_SECTION_RE = re.compile(r"(?ms)^## Phases\s*$.*?(?=^## |\Z)")


# -------------------------------------------------------------- normalize ---

def normalize_actor(actor) -> str:
    """`user:<u>/agent:<a>` → `user:<u>`, then casefold + strip — the agent
    suffix is a persona of the same person, and so are case/whitespace variants
    of the same identity (a git email is commonly mixed-case). Comparing the
    normalized form is what makes `reviewer != author` hold against a casing
    difference, so the self-review block cannot be sidestepped by approving from
    `BOB@x.com` what `bob@x.com` authored. (the normalization extends bare
    agent-suffix stripping with case + whitespace insensitivity.)"""
    return str(actor).split("/agent:")[0].strip().casefold()


def check_role(reviewer, author, team) -> "str | None":
    """None when the role rule holds, else an actionable reason.

    Rule: normalize(reviewer) ∈ normalized roster, and (unless solo mode
    allow_self_review is on) normalize(reviewer) ≠ normalize(author)."""
    nr, na = normalize_actor(reviewer), normalize_actor(author)
    roster = {normalize_actor(r) for r in team.get("reviewers", [])}
    if nr not in roster:
        return (
            "reviewer %s is not in the reviewers roster — add them to "
            "`reviewers:` in harness/data/team.yaml (tracked in git)" % nr)
    if nr == na and not team.get("allow_self_review", False):
        return (
            "reviewer and author are the same person (%s) after the agent "
            "suffix is normalized away — self-approval is blocked. A second "
            "rostered reviewer must approve, or flip `allow_self_review: "
            "true` in harness/data/team.yaml (solo mode, tracked in git)" % nr)
    return None


# ------------------------------------------------------- normalized hashes ---

def _plan_files(plan_dir: Path):
    plan_dir = Path(plan_dir)
    files = [plan_dir / "plan.md"]
    files += sorted(plan_dir.glob("phase-*.md"))
    return [f for f in files if f.is_file()]


def _normalized_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = _FRONTMATTER_RE.sub("", text, count=1)
    if path.name == "plan.md":
        # Only plan.md owns a legitimately-mutating `## Phases` section;
        # the same heading in a phase file is body and stays pinned.
        text = _PHASES_SECTION_RE.sub("", text, count=1)
    return text


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def file_hashes(plan_dir) -> dict:
    """filename → sha256-12hex of that file's normalized content. Lets the
    gate name exactly WHICH file drifted after approval."""
    return {f.name: _digest(_normalized_text(f)) for f in _plan_files(plan_dir)}


def plan_hash(plan_dir) -> str:
    """sha256-12hex over the whole normalized plan dir (plan.md + phase-*.md,
    sorted by name, filename-delimited so renames change the hash too)."""
    h = hashlib.sha256()
    for f in _plan_files(plan_dir):
        h.update(f.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(_normalized_text(f).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:12]


# ----------------------------------------------------------------- author ---

_AUTHOR_FM_RE = re.compile(r"^author:\s*(.+?)\s*$", re.MULTILINE)


def _author_from_trace(plan_name) -> "str | None":
    """Best-effort: actor of a plan-creation trace event for this plan."""
    try:
        trace_dir = harness_paths.trace_dir()
        for f in sorted(trace_dir.glob("trace-*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("event") == "plan_created" \
                        and rec.get("target") == plan_name:
                    return rec.get("actor")
    except OSError:
        pass
    return None


def _resolve_author(plan_dir: Path) -> "str | None":
    """Trace event (if a plan_created event exists) → plan.md frontmatter
    `author:` → None (caller must demand --author; guessing an author would
    let the role check pass against the wrong person)."""
    author = _author_from_trace(plan_dir.name)
    if author:
        return author
    pm = plan_dir / "plan.md"
    try:
        fm = _FRONTMATTER_RE.match(pm.read_text(encoding="utf-8"))
    except OSError:
        return None
    if fm:
        m = _AUTHOR_FM_RE.search(fm.group(0))
        if m:
            return m.group(1)
    return None


# ------------------------------------------------------------------ write ---

def write_approval(plan_dir, verdict, rationale, author=None,
                   reviewer=None) -> dict:
    """Validate the role rule, then write plans/<plan>/artifacts/
    plan-approval.json. Refuses (no write at all) the moment any rule fails."""
    plan_dir = Path(plan_dir)
    if not (plan_dir / "plan.md").is_file():
        return {"ok": False,
                "error": "no plan.md in %s — point --plan at a plan dir"
                         % plan_dir}
    if verdict not in ("APPROVED", "REJECTED"):
        return {"ok": False,
                "error": "verdict must be APPROVED or REJECTED (got %r)"
                         % verdict}
    if not (rationale or "").strip():
        return {"ok": False, "error": "a non-empty --rationale is required"}

    reviewer = reviewer or hook_runtime.resolve_actor()
    author = (author or "").strip() or _resolve_author(plan_dir)
    if not author:
        return {"ok": False,
                "error": "cannot resolve the plan author (no creation trace "
                         "event, no `author:` frontmatter in plan.md) — pass "
                         "--author user:<who> explicitly; refusing to write "
                         "an approval with an empty author"}

    root = harness_paths.root()
    try:
        team = team_config.load_team(
            path=root / "harness" / "data" / "team.yaml")
    except team_config.TeamConfigError as e:
        return {"ok": False, "error": str(e)}
    reason = check_role(reviewer, author, team)
    if reason:
        return {"ok": False, "error": reason}

    rec = {
        "schema": SCHEMA,
        "plan": plan_dir.name,
        "plan_hash": plan_hash(plan_dir),
        "file_hashes": file_hashes(plan_dir),
        "author": author,
        "reviewer": reviewer,
        "verdict": verdict,
        "rationale": rationale,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    target = plan_dir / "artifacts" / "plan-approval.json"
    fs_guard.assert_under(target, "plans", root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    trace_log.append_event("plan_approval", "approval_written",
                           actor=reviewer, target=plan_dir.name,
                           status=verdict,
                           note="plan_hash=%s author=%s" % (
                               rec["plan_hash"], author))
    return {"ok": True, "artifact": str(target), "record": rec}


# -------------------------------------------------------------------- CLI ---

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write the role-checked plan-approval artifact.")
    ap.add_argument("--plan", required=True,
                    help="plan dir (path, or bare name under plans/)")
    ap.add_argument("--verdict", required=True,
                    choices=("APPROVED", "REJECTED"))
    ap.add_argument("--rationale", required=True)
    ap.add_argument("--author", default=None,
                    help="plan author (only needed when neither trace nor "
                         "plan.md frontmatter records one)")
    args = ap.parse_args(argv)

    plan_dir = Path(args.plan)
    if not plan_dir.is_dir():
        under_plans = harness_paths.root() / "plans" / args.plan
        if under_plans.is_dir():
            plan_dir = under_plans

    result = write_approval(plan_dir, verdict=args.verdict,
                            rationale=args.rationale, author=args.author)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
