#!/usr/bin/env python3
"""decision_register — the Decision Register: the authoritative, append-only
home for explicit architecture/process rulings (`DEC-<n>`).

A decision is recorded when a binding call is made that later work must not
re-litigate. The register kills re-litigation: the next time the same tension
surfaces, read the register FIRST and surface the prior ruling ("DEC-n decided
X because … — keep or supersede?") instead of re-debating.

Script-vs-LLM split: this script owns the deterministic structural work —
allocate the next monotonic id, validate the `^DEC-\\d+$` grammar + record
shape, append WITHOUT overwriting prior records, parse + list. The caller owns
the human RATIONALE prose passed in as `--rationale`.

Storage: `docs/decisions.md` (visible, committed). Each ruling is one record
block: a `---`-fenced YAML mini-frontmatter (id/status/date/affects/
supersedes) + a `## DEC-<n> — <title>` heading + rationale, newest-last. The
write resolves through fs_guard zone "docs" so a register write can never
escape the docs boundary.

ID grammar: `^DEC-\\d+$`, monotonic max+1 regardless of status — a superseded
DEC still counts toward the max, so ids are never reused. BOTH append paths
(--append with an explicit id, --append-alloc) run inside the register lock:
two concurrent agents on one machine cannot overwrite each other's appends
(see register_store for the degraded-lock posture on platforms without flock).

CLI:
    decision_register.py --root <dir> --alloc-id
    decision_register.py --root <dir> --append --id DEC-2 --title "..." \\
        --rationale "..." [--affects PRD-X] [--supersedes DEC-1]
    decision_register.py --root <dir> --append-alloc --title ... --rationale ...
    decision_register.py --root <dir> --list   # active records as JSON
"""

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import fs_guard  # noqa: E402
from register_store import (  # noqa: E402
    RECORD_RE as _RECORD_RE, escape_injection, register_lock,
    sanitize_field, scan_record_ids,
)

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.append(str(_HOOKS_DIR))
import hook_runtime  # noqa: E402

# Windows consoles may default to a legacy codepage; UTF-8 JSON output must
# not crash there. reconfigure exists on 3.7+; guard for exotic stdouts.
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")


# This register's own heading anchor: a rationale line that is a bare `---`
# fence would split decisions.md into a phantom record; a `## DEC-<n>` line
# could smuggle a fake heading. Both are neutralized on write.
_INJ_DEC_HEADING_RE = re.compile(r"(?m)^(##\s+DEC-)")

# ID grammar: DEC- + digits, nothing else. Parent-free, globally monotonic.
DECISION_ID_RE = re.compile(r"^DEC-\d+$")

# Record template inline (one register, one shape — no template file to drift).
# A register record is machine-written state, so it carries actor + ts like the
# other stores (actor via resolve_actor, ts a UTC isoformat instant).
_RECORD_TEMPLATE = """---
id: {id}
status: {status}
date: {date}
actor: {actor}
ts: {ts}
{affects_line}{supersedes_line}---

## {id} — {title}

{rationale}
"""


class DecisionError(ValueError):
    """Raised on a grammar/shape/uniqueness violation (surfaced as a JSON
    finding by the CLI; raised directly for library callers)."""


def sanitize_rationale(rationale: str) -> str:
    """Neutralize record-fence / DEC-heading injection in the multiline
    rationale, preserving the text."""
    return escape_injection(rationale, _INJ_DEC_HEADING_RE)


def _decisions_path(root) -> Path:
    return Path(root) / "docs" / "decisions.md"


def _lock_path(root) -> Path:
    return Path(root) / "docs" / ".decision_register.lock"


@contextlib.contextmanager
def _register_lock(root):
    """alloc-id + append as ONE critical section over this register's lock
    file (closes the looped-alloc TOCTOU window; also serializes plain
    appends so concurrent agents cannot drop each other's records)."""
    with register_lock(_lock_path(root)):
        yield


def parse_decisions(root) -> List[Dict[str, Any]]:
    """Every record (active AND superseded), in file order. Missing file →
    empty list. A record with unparseable YAML or a malformed id is skipped
    (fail-soft — one corrupt block never sinks --list)."""
    path = _decisions_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return []

    records: List[Dict[str, Any]] = []
    for m in _RECORD_RE.finditer(text):
        try:
            fm = yaml.safe_load(m.group("fm")) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        dec_id = str(fm.get("id", "")).strip()
        if not DECISION_ID_RE.match(dec_id):
            continue
        rec: Dict[str, Any] = {
            "id": dec_id,
            "status": str(fm.get("status", "active")).strip() or "active",
            "date": str(fm.get("date", "")).strip(),
            "actor": str(fm.get("actor", "")).strip(),
            "ts": str(fm.get("ts", "")).strip(),
        }
        for opt in ("affects", "supersedes"):
            val = fm.get(opt)
            rec[opt] = str(val).strip() if val not in (None, "") else ""
        rec["title"] = _title_from_body(m.group("body"), dec_id)
        records.append(rec)
    return records


def _title_from_body(body: str, dec_id: str) -> str:
    m = re.search(r"^##\s+%s\s*[—-]\s*(?P<title>.+?)\s*$" % re.escape(dec_id),
                  body, re.MULTILINE)
    return m.group("title").strip() if m else ""


def list_active(root) -> List[Dict[str, Any]]:
    """Records with `status: active` only — the rulings still in force."""
    return [r for r in parse_decisions(root) if r["status"] == "active"]


def alloc_id(root) -> str:
    """Next free `DEC-<n>` = max-existing + 1 (DEC-1 on an empty register).
    Scans RAW `id:` lines so a corrupt-but-id-bearing block still reserves its
    number — a later repair can never collide with a meanwhile-allocated id."""
    used = []
    for dec_id in _scan_all_ids(root):
        m = re.match(r"^DEC-(\d+)$", dec_id)
        if m:
            used.append(int(m.group(1)))
    return "DEC-%d" % ((max(used) + 1) if used else 1)


def _scan_all_ids(root) -> List[str]:
    path = _decisions_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return []
    return scan_record_ids(text)


def _render_record(dec_id, title, rationale, date, affects, supersedes, status,
                   actor, ts) -> str:
    """Fill the record template, emitting the optional link lines ONLY when present
    so an absent affects/supersedes never leaves a bare `affects:` key — and the strip
    never touches the rationale body, which may legitimately contain such a line.

    `affects` is free text, so it is rendered as a JSON-quoted scalar (valid
    YAML): an embedded `key: value` fragment stays INSIDE the string instead
    of becoming a second frontmatter key or breaking the YAML parse.
    `supersedes` needs no quoting — it is regex-validated to `DEC-\\d+`.
    `actor`/`ts` are machine-resolved (resolve_actor + UTC isoformat) and are
    JSON-quoted so a colon in the actor (`user:x@host`) can never split the
    frontmatter into a second key."""
    # Build the optional link lines conditionally — an absent field emits NOTHING, so
    # there is never an empty `affects:`/`supersedes:` line to strip back out. This keeps
    # the strip from ever touching the rationale body, which may legitimately contain a
    # line like `affects:` (a decision discussing the field).
    affects_line = ("affects: %s\n" % json.dumps(affects, ensure_ascii=False)) if affects else ""
    supersedes_line = ("supersedes: %s\n" % supersedes) if supersedes else ""
    out = _RECORD_TEMPLATE.format(
        id=dec_id, status=status, date=date,
        actor=json.dumps(actor, ensure_ascii=False),
        ts=json.dumps(ts, ensure_ascii=False),
        affects_line=affects_line, supersedes_line=supersedes_line,
        title=title, rationale=rationale.strip(),
    )
    return out.strip() + "\n"


def append_decision(
    root,
    dec_id: str,
    title: str,
    rationale: str,
    affects: str = "",
    supersedes: str = "",
    date: Optional[str] = None,
    status: str = "active",
) -> Path:
    """Validate + append one record. Append-only: prior records untouched.
    Raises DecisionError on malformed/duplicate id or dangling supersedes.

    NOT self-locking: this is a read-modify-write over the whole file, so
    concurrent callers can drop each other's records. The CLI paths and
    append_alloc() hold the register lock around it; a library caller must
    do the same (wrap in `with register_lock(...)`).

    Injection escape covers ALL caller-supplied text: the multiline rationale
    keeps its line breaks (anchors escaped); the single-line title/affects/
    supersedes have newlines collapsed so they cannot open a phantom record
    or smuggle extra frontmatter keys."""
    if not DECISION_ID_RE.match(dec_id):
        raise DecisionError(
            "decision id %r does not match the grammar %s" % (dec_id, DECISION_ID_RE.pattern)
        )
    if not title.strip():
        raise DecisionError("a decision needs a non-empty title")
    if not rationale.strip():
        raise DecisionError("a decision needs a non-empty rationale (the WHY)")
    if supersedes and not DECISION_ID_RE.match(supersedes):
        raise DecisionError(
            "supersedes %r is not a valid decision id (%s)" % (supersedes, DECISION_ID_RE.pattern)
        )

    existing = parse_decisions(root)
    existing_ids = {r["id"] for r in existing}
    if dec_id in existing_ids:
        raise DecisionError(
            "%s already exists in the register; the register is append-only "
            "(use a fresh --alloc-id, and `supersedes:` to retire the old one)" % dec_id
        )
    if supersedes and supersedes not in existing_ids:
        raise DecisionError(
            "supersedes %s but that id is not in the register" % supersedes
        )

    record = _render_record(
        dec_id,
        sanitize_field(title, _INJ_DEC_HEADING_RE),
        sanitize_rationale(rationale),
        date or dt.date.today().isoformat(),
        sanitize_field(affects, _INJ_DEC_HEADING_RE),
        supersedes, status,
        actor=hook_runtime.resolve_actor(),
        ts=dt.datetime.now(dt.timezone.utc).isoformat(),
    )

    path = _decisions_path(root)
    # Containment helper: resolve + contain BEFORE any mkdir/write so a
    # tampered path can never place the register outside the docs zone.
    fs_guard.assert_under(path, "docs", root=root)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        prior = path.read_text(encoding="utf-8")
        sep = "" if prior.endswith("\n\n") else ("\n" if prior.endswith("\n") else "\n\n")
        new_text = prior + sep + record
    else:
        new_text = "# Decision Register\n\n" + record

    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_text)
    return path


def _supersede_in_place(root, dec_id: str) -> bool:
    """Flip an existing active record to `status: superseded`. The ONE
    in-place edit the register makes — only the `status:` line of the retired
    record, never its prose. Returns True if a record was flipped."""
    path = _decisions_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return False

    flipped = {"hit": False}

    def _flip(m):
        fm = m.group("fm")
        try:
            data = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            return m.group(0)
        if isinstance(data, dict) and str(data.get("id", "")).strip() == dec_id:
            new_fm, n = re.subn(r"^status:\s*\S+\s*$", "status: superseded",
                                fm, count=1, flags=re.MULTILINE)
            if n == 0:
                # No status: line to substitute (hand-edited record) —
                # reporting a flip here would leave the old ruling silently
                # active while the caller believes it retired.
                return m.group(0)
            flipped["hit"] = True
            # _RECORD_RE consumes the closing-fence newline AND the blank line
            # after it; reinsert the blank line so a canonical file round-trips
            # byte-stably (---\n\n## DEC-n, not ---\n## DEC-n).
            return "---\n%s\n---\n\n%s" % (new_fm, m.group("body").lstrip(chr(10)))
        return m.group(0)

    new_text = _RECORD_RE.sub(_flip, text)
    if flipped["hit"]:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
    return flipped["hit"]


def _can_supersede(root, dec_id: str) -> bool:
    """Dry-run feasibility of _supersede_in_place: does a record with this id
    exist AND carry a flippable `status:` line? Used to gate the append BEFORE
    writing the new record, so a supersede that cannot land never leaves a
    second active ruling on disk: this check gates the append, so the later
    flip cannot fail after the new record is written."""
    path = _decisions_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return False
    for m in _RECORD_RE.finditer(text):
        fm = m.group("fm")
        try:
            data = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and str(data.get("id", "")).strip() == dec_id:
            return re.search(r"^status:\s*\S+\s*$", fm, flags=re.MULTILINE) is not None
    return False


def append_alloc(
    root,
    title: str,
    rationale: str,
    affects: str = "",
    supersedes: str = "",
    date: Optional[str] = None,
    status: str = "active",
    dec_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one record in ONE locked critical section — the SINGLE home for
    the alloc/append/supersede-flip atomicity rule shared by both CLI write
    modes. `dec_id=None` allocates the next monotonic id INSIDE the lock (the
    --append-alloc path); an explicit `dec_id` is the --append path. Either way
    the alloc + append + flip run under one register lock, so two concurrent
    agents cannot overwrite each other's records, and a supersede that cannot
    land never leaves a second active ruling.

    On a dup-id race append_decision raises and the CLI surfaces a JSON finding
    — never a silently dropped ruling."""
    with _register_lock(root):
        # Gate the append on supersede feasibility FIRST: if the target cannot
        # be retired (missing record / no status: line), refuse before writing
        # the new ruling — otherwise a failed flip would leave two active
        # rulings on disk. The feasibility check gates the write, so the later
        # flip cannot strand a second active ruling.
        if supersedes and not _can_supersede(root, supersedes):
            raise DecisionError(
                "cannot retire %s (no record with a status: line to flip); "
                "refusing to append a ruling that would leave two active "
                "rulings — resolve %s by hand" % (supersedes, supersedes)
            )
        dec_id = dec_id or alloc_id(root)
        path = append_decision(
            root, dec_id=dec_id, title=title, rationale=rationale,
            affects=affects, supersedes=supersedes, date=date, status=status,
        )
        if supersedes and not _supersede_in_place(root, supersedes):
            raise DecisionError(
                "appended %s but could not retire %s; the register would have "
                "two active rulings — resolve %s by hand" % (
                    dec_id, supersedes, supersedes)
            )
    return {"id": dec_id,
            "path": str(Path(path).relative_to(Path(root).resolve())),
            "written": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--alloc-id", action="store_true",
                      help="print the next free DEC-<n>")
    mode.add_argument("--append", action="store_true",
                      help="append a decision record (explicit or alloc'd id)")
    mode.add_argument("--append-alloc", action="store_true",
                      help="atomic: alloc the next id AND append, locked")
    mode.add_argument("--list", action="store_true",
                      help="print active decisions as JSON")
    ap.add_argument("--id", help="decision id (with --append); default = alloc")
    ap.add_argument("--title")
    ap.add_argument("--rationale")
    ap.add_argument("--affects", default="")
    ap.add_argument("--supersedes", default="")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    try:
        if args.alloc_id:
            print(json.dumps({"id": alloc_id(root)}, ensure_ascii=False))
            return 0
        if args.list:
            print(json.dumps({"active": list_active(root)}, indent=2,
                             ensure_ascii=False))
            return 0
        if args.append_alloc:
            result = append_alloc(
                root, title=args.title or "", rationale=args.rationale or "",
                affects=args.affects, supersedes=args.supersedes,
            )
            print(json.dumps(result, ensure_ascii=False))
            return 0
        # --append: the explicit-id path delegates to the SAME locked critical
        # section (append_alloc) — one home for the alloc/append/supersede-flip
        # atomicity. The two write modes differ ONLY in whether the id is given:
        # an explicit --id is passed through; an absent --id allocs inside the
        # lock exactly like --append-alloc. So two concurrent appends still
        # serialize on the register lock, and a rejected supersede still leaves
        # the register byte-untouched (never zero-active + phantom-retired).
        result = append_alloc(
            root, title=args.title or "", rationale=args.rationale or "",
            affects=args.affects, supersedes=args.supersedes, dec_id=args.id,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 — surface as finding
        # Analytical-script contract: a bad input surfaces as a JSON finding
        # on stdout + exit 0, never a bare traceback.
        print(json.dumps(
            {"error": "invalid_input", "message": str(exc), "written": False},
            ensure_ascii=False,
        ))
        return 0


if __name__ == "__main__":
    sys.exit(main())
