#!/usr/bin/env python3
"""scaffold.py — deterministic plan/report skeletons from harness/templates/.

hs:plan and hs:cook expect a fixed plan shape (frontmatter + phases + acceptance
+ rollback) and a fixed report shape. This helper stamps that shape out of the
template files under harness/templates/ so the boilerplate — and especially the
machine-owned provenance frontmatter (harness_version / kit_digest /
schema_version) — is never hand-typed and never stale.

Three pieces, each small and testable:
  - render(template, subs):    {{TOKEN}} substitution, pure text.
  - unfilled_tokens(text):     the {{TOKEN}}s a render left behind (drift catch).
  - scaffold_plan / scaffold_report: build the dir/file, stamp via artifact_stamp.

Containment: a plan/report lands ONLY under <root>/plans/. There is no path
argument to climb out of — the only caller-supplied path component is the slug,
and validate_slug() rejects anything but a lowercase kebab token BEFORE any
directory is created, so `../` / a slash / an absolute path can never escape.

CLI:
    scaffold.py plan   --slug S --title T [--mode hard|fast] [--no-tdd]
        [--phases a,b,c] [--id YYMMDD-HHMM] [--root .] [--force] [--print]
    scaffold.py report --slug S --type research --title T
        [--id YYMMDD-HHMM] [--root .] [--force] [--print]
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import artifact_stamp  # noqa: E402 — reuse the canonical provenance stamper (DRY)
import harness_release  # noqa: E402

_TEMPLATES = ("plan-template.md", "phase-template.md", "report-template.md")
_TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
# Lowercase kebab only: a slug is a single path segment, never a route out.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def render(template: str, subs: dict) -> str:
    """Replace every ``{{KEY}}`` for which ``subs`` has KEY. Unknown tokens are
    left intact so ``unfilled_tokens`` can flag them — a render never silently
    drops a placeholder it could not fill."""
    out = template
    for key, val in subs.items():
        out = out.replace("{{%s}}" % key, str(val))
    return out


def unfilled_tokens(text: str) -> list:
    """The ``{{TOKEN}}`` names still present, in first-seen order, deduped."""
    seen = []
    for m in _TOKEN_RE.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def validate_slug(slug: str) -> str:
    """Return ``slug`` if it is a lowercase-kebab single segment, else raise.
    The single gate that keeps a write inside plans/."""
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise ValueError(
            "invalid slug %r — use lowercase letters, digits and single dashes "
            "(e.g. 'my-feature'); no slashes, spaces, dots or '..'." % (slug,))
    return slug


def _read_template(root: Path, name: str) -> str:
    p = Path(root) / "harness" / "templates" / name
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            "scaffold: template %s missing under %s/harness/templates/ — the "
            "templates ship with the harness; run verify_install." % (name, root))


def _release(root: Path):
    rel = harness_release.read_release(Path(root))
    return rel.get("harness_version", ""), rel.get("kit_digest", "")


def _stamp(text: str, root: Path) -> str:
    ver, dig = _release(root)
    return artifact_stamp.stamp_markdown(text, ver, dig)


def _title_case(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split("-"))


def _plan_text(root: Path, plan_id: str, slug: str, title: str, mode: str,
               tdd: bool, phases: list, branch: str, created: str) -> str:
    """The stamped plan.md text for these inputs — shared by the writer
    (scaffold_plan) and the CLI --print path so neither drifts from the other."""
    phases_yaml = "\n".join(
        "  - phase-%d-%s.md" % (i, name) for i, name in enumerate(phases, 1))
    phases_table = "\n".join(
        ["| # | Theme | Phụ thuộc | Cỡ |", "|---|---|---|---|"]
        + ["| %d | %s | TBD | TBD |" % (i, _title_case(name))
           for i, name in enumerate(phases, 1)])
    text = render(_read_template(root, "plan-template.md"), {
        "ID": "%s-%s" % (plan_id, slug), "TITLE": title, "MODE": mode,
        "TDD": "true" if tdd else "false", "BRANCH": branch, "CREATED": created,
        "PHASES_YAML": phases_yaml, "PHASES_TABLE": phases_table,
    })
    return _stamp(text, root)


def _report_text(root: Path, report_id: str, slug: str, rtype: str, title: str,
                 created: str) -> str:
    text = render(_read_template(root, "report-template.md"), {
        "TITLE": title, "ID": "%s-%s" % (report_id, slug),
        "TYPE": rtype, "CREATED": created,
    })
    return _stamp(text, root)


def scaffold_plan(root, plan_id: str, slug: str, title: str, mode: str = "hard",
                  tdd: bool = True, phases=None, branch: str = "TBD",
                  created: str = "TBD", force: bool = False) -> Path:
    """Create ``<root>/plans/<plan_id>-<slug>/`` with plan.md + one phase file
    per phase. Returns the plan directory. Refuses to clobber an existing
    plan.md without ``force``."""
    validate_slug(slug)
    phases = list(phases) if phases else ["main"]
    root = Path(root)
    plan_dir = root / "plans" / ("%s-%s" % (plan_id, slug))
    plan_md = plan_dir / "plan.md"
    if plan_md.exists() and not force:
        raise FileExistsError(
            "scaffold: %s already exists — pass force=True to overwrite." % plan_md)

    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_md.write_text(
        _plan_text(root, plan_id, slug, title, mode, tdd, phases, branch, created),
        encoding="utf-8")

    phase_tpl = _read_template(root, "phase-template.md")
    for i, name in enumerate(phases, 1):
        phase_text = render(phase_tpl, {
            "NUM": str(i), "PHASE_TITLE": _title_case(name),
            "PLAN_ID": "%s-%s" % (plan_id, slug), "CREATED": created,
        })
        (plan_dir / ("phase-%d-%s.md" % (i, name))).write_text(
            _stamp(phase_text, root), encoding="utf-8")
    return plan_dir


def scaffold_report(root, report_id: str, slug: str, rtype: str, title: str,
                    created: str = "TBD", force: bool = False) -> Path:
    """Create ``<root>/plans/reports/<rtype>-<report_id>-<slug>-report.md``."""
    validate_slug(slug)
    validate_slug(rtype)
    root = Path(root)
    out = (root / "plans" / "reports"
           / ("%s-%s-%s-report.md" % (rtype, report_id, slug)))
    if out.exists() and not force:
        raise FileExistsError(
            "scaffold: %s already exists — pass force=True to overwrite." % out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_report_text(root, report_id, slug, rtype, title, created),
                   encoding="utf-8")
    return out


def _now_id() -> str:
    """YYMMDD-HHMM local — the plan/report id stem. Imported lazily so the pure
    render/scaffold functions stay clock-free and deterministic for tests."""
    from datetime import datetime
    return datetime.now().strftime("%y%m%d-%H%M")


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Scaffold a plan or report skeleton under plans/.")
    sub = ap.add_subparsers(dest="kind", required=True)

    p = sub.add_parser("plan", help="scaffold a plan dir (plan.md + phases)")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--mode", default="hard", choices=["hard", "fast"])
    p.add_argument("--no-tdd", dest="tdd", action="store_false")
    p.add_argument("--phases", default="main",
                   help="comma-separated phase names (default: main)")
    p.add_argument("--id", dest="ident", default=None)
    p.add_argument("--branch", default="TBD")
    p.add_argument("--root", default=".")
    p.add_argument("--force", action="store_true")
    p.add_argument("--print", dest="to_stdout", action="store_true",
                   help="print plan.md, write nothing")

    r = sub.add_parser("report", help="scaffold a report file")
    r.add_argument("--slug", required=True)
    r.add_argument("--type", dest="rtype", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--id", dest="ident", default=None)
    r.add_argument("--root", default=".")
    r.add_argument("--force", action="store_true")
    r.add_argument("--print", dest="to_stdout", action="store_true")

    args = ap.parse_args(argv)
    ident = args.ident or _now_id()

    try:
        if args.kind == "plan":
            phases = [s.strip() for s in args.phases.split(",") if s.strip()]
            for s in phases:
                validate_slug(s)
            if args.to_stdout:
                validate_slug(args.slug)
                sys.stdout.write(_plan_text(
                    Path(args.root), ident, args.slug, args.title, args.mode,
                    args.tdd, phases or ["main"], args.branch, _today()))
                return 0
            d = scaffold_plan(
                root=args.root, plan_id=ident, slug=args.slug, title=args.title,
                mode=args.mode, tdd=args.tdd, phases=phases, branch=args.branch,
                created=_today(), force=args.force)
            sys.stderr.write("scaffold: wrote %s\n" % d)
            return 0

        # report
        if args.to_stdout:
            validate_slug(args.slug)
            validate_slug(args.rtype)
            sys.stdout.write(_report_text(
                Path(args.root), ident, args.slug, args.rtype, args.title,
                _today()))
            return 0
        out = scaffold_report(
            root=args.root, report_id=ident, slug=args.slug, rtype=args.rtype,
            title=args.title, created=_today(), force=args.force)
        sys.stderr.write("scaffold: wrote %s\n" % out)
        return 0
    except (ValueError, FileExistsError, FileNotFoundError) as e:
        sys.stderr.write("scaffold: %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
