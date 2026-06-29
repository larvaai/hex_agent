#!/usr/bin/env python3
"""scaffold_standards — write a TBD skeleton for a free-form standards doc.

The installer never fabricates standards (authoring them is the org's job); this
is the OPT-IN helper a deployer runs to get a structured starting point for the
two prose docs that hs:plan and hs:cook read before working:

    harness/standards/system-architecture.md
    harness/standards/code-standards.md

The skeleton is all section headers + explicit `TBD` markers — valid markdown
that says nothing until a human fills it. The write goes through the standards
fs_guard zone (so the script cannot land a file outside harness/standards/), and
an already-authored file is never clobbered without --force.

CLI:
    scaffold_standards.py --type system-architecture|code-standards
        [--root <project-dir>] [--force] [--print]
"""

import argparse
import sys
from pathlib import Path

from encoding_utils import configure_utf8_console
from fs_guard import FenceError, assert_under

configure_utf8_console()

# Content already authored (more than a placeholder) is never overwritten without
# --force. Mirrors the installer's "thin standards" threshold.
_THIN = 40

_HEADER = (
    "# %s\n\n"
    "> TBD — replace every section below with your project's reality. hs:plan\n"
    "> and hs:cook READ this file before working, so keep it accurate and short;\n"
    "> a long file is loaded by many skills and is easy to skim past.\n\n")

_SECTIONS = {
    "system-architecture": (
        "System Architecture",
        [
            ("Overview", "one paragraph: what the system does and its shape."),
            ("Components", "the major modules/services and each one's job."),
            ("Data flow", "how a request or job moves through the components; "
                          "where state lives."),
            ("External dependencies", "datastores, third-party APIs, queues, "
                                      "and how they are reached."),
            ("Boundaries & trust", "trust boundaries, auth surfaces, what is "
                                   "internal versus exposed."),
            ("Key decisions", "the load-bearing architectural decisions and "
                              "their rationale."),
            ("Constraints & non-goals", "what the architecture deliberately "
                                        "does NOT do."),
        ],
    ),
    "code-standards": (
        "Code Standards",
        [
            ("Languages & conventions", "languages in use and the naming/style "
                                        "rules per language."),
            ("Project layout", "where code, tests, config, and docs live."),
            ("Testing", "the test framework, what must be covered, and the "
                        "red→green expectation."),
            ("Error handling & logging", "how errors are raised, surfaced, and "
                                         "logged."),
            ("Security & secrets", "secret handling, input validation, and the "
                                   "dependency policy."),
            ("Commits & review", "commit format, branch policy, and review or "
                                 "approval expectations."),
        ],
    ),
}


def render(kind: str) -> str:
    """The TBD skeleton markdown for `kind`."""
    title, sections = _SECTIONS[kind]
    body = "".join(
        "## %s\nTBD — %s\n\n" % (name, hint) for name, hint in sections)
    return _HEADER % title + body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write a TBD skeleton for a free-form standards doc.")
    ap.add_argument("--type", required=True, choices=sorted(_SECTIONS),
                    help="which standards doc to scaffold")
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an already-authored file")
    ap.add_argument("--print", dest="to_stdout", action="store_true",
                    help="print the skeleton, write nothing")
    args = ap.parse_args(argv)

    content = render(args.type)
    if args.to_stdout:
        sys.stdout.write(content)
        return 0

    root = Path(args.root).resolve()
    rel = "harness/standards/%s.md" % args.type
    target = root / rel
    if (target.exists()
            and len(target.read_text(encoding="utf-8").strip()) > _THIN
            and not args.force):
        sys.stderr.write(
            "scaffold_standards: %s already has content — refusing to clobber "
            "it. Edit it directly, or pass --force to overwrite.\n" % rel)
        return 1

    try:
        safe = assert_under(target, "standards", root=root)
    except FenceError as e:
        sys.stderr.write("scaffold_standards: %s\n" % e)
        return 2

    safe.parent.mkdir(parents=True, exist_ok=True)
    safe.write_text(content, encoding="utf-8")
    sys.stderr.write(
        "scaffold_standards: wrote %s — fill in the TBD sections.\n" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
