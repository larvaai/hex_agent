#!/usr/bin/env python3
"""team_config.py — loader for harness/data/team.yaml (reviewers + claims).

One shared loader so the roster and claim parameters are read identically by
every consumer: claims (claims.lease_s now), plan-approval role check
(reviewers / allow_self_review later).

DELIBERATELY no env override: team.yaml is gate input — the roster decides who
may approve a plan. The only load path is the tracked file next to the repo's
data dir (resolved off __file__, never CWD), so changing the roster always
means a git-visible diff and the pre-push env scrub has nothing to chase.
Callers that need a different file (tests) pass `path=` explicitly.
"""

import sys
from pathlib import Path

_TEAM_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "team.yaml"

DEFAULT_LEASE_S = 14400  # 4h


class TeamConfigError(Exception):
    """Raised when team.yaml is missing or malformed. Message names the file
    and the offending key so the fix is a config edit, not a debug session."""


def load_team(path=None) -> dict:
    """Parse team.yaml → {reviewers, allow_self_review, claims:{lease_s}}.

    Missing file / non-mapping document / wrong-typed keys raise
    TeamConfigError naming file + key. A missing claims.lease_s falls back to
    DEFAULT_LEASE_S with a stderr warning (a roster without tuning is usable;
    a roster file that cannot be parsed is not).
    """
    import yaml  # lazy: keep importable without PyYAML until actually used

    p = Path(path) if path else _TEAM_DEFAULT
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TeamConfigError(
            "team config missing at %s — create it with at least:\n"
            "  reviewers: []\n  allow_self_review: false\n"
            "  claims: {lease_s: %d}" % (p, DEFAULT_LEASE_S)
        )
    if not isinstance(raw, dict):
        raise TeamConfigError(
            "team config %s is malformed — expected a YAML mapping with keys "
            "`reviewers`, `allow_self_review`, `claims`" % p
        )

    reviewers = raw.get("reviewers", [])
    if not isinstance(reviewers, list) or not all(
            isinstance(r, str) for r in reviewers):
        raise TeamConfigError(
            "key `reviewers` in %s must be a list of strings "
            "(e.g. [\"user:a@x.com\"])" % p
        )

    allow_self = raw.get("allow_self_review", False)
    if not isinstance(allow_self, bool):
        raise TeamConfigError(
            "key `allow_self_review` in %s must be true or false" % p
        )

    claims_raw = raw.get("claims")
    claims_cfg = claims_raw if isinstance(claims_raw, dict) else {}
    lease = claims_cfg.get("lease_s")
    if lease is None:
        sys.stderr.write(
            "[team_config] %s has no claims.lease_s — using default %d s\n"
            % (p, DEFAULT_LEASE_S)
        )
        lease = DEFAULT_LEASE_S
    if not isinstance(lease, int) or isinstance(lease, bool) or lease <= 0:
        raise TeamConfigError(
            "key `claims.lease_s` in %s must be a positive integer of "
            "seconds (got %r)" % (p, lease)
        )

    return {
        "reviewers": [r.strip() for r in reviewers],
        "allow_self_review": allow_self,
        "claims": {"lease_s": lease},
    }


def lease_s(path=None) -> int:
    """Convenience: the configured claim lease in seconds."""
    return load_team(path=path)["claims"]["lease_s"]


def _normalize_reviewers(items) -> list:
    """Prefix a bare email with `user:` and drop blanks. Mirrors the installer's
    normalize so a roster set here and one set at install render identically."""
    out = []
    for raw in items:
        s = str(raw).strip()
        if not s:
            continue
        out.append(s if ":" in s else "user:%s" % s)
    return out


def _preserved_header(path: Path) -> str:
    """Leading comment/blank header kept across a CLI write (shared extractor in
    config_io). Missing file → a minimal header."""
    import config_io
    return config_io.leading_comment_block(
        path, "# team.yaml — reviewer roster + claim params.\n")


def _trace_change(target: str, note: str) -> None:
    """Best-effort audit line (actor + ts) for a roster/claims edit — team.yaml
    is gate config, so a change is recorded like guard_config's. Fail-open: a
    missing trace primitive never blocks the write."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
        import hook_runtime
        import trace_log
        trace_log.append_event("team_config", "team_config_changed",
                               actor=hook_runtime.resolve_actor(),
                               target=target, note=note)
    except Exception:  # noqa: BLE001 — audit is best-effort, never fatal
        pass


def save_team(updates: dict, path=None) -> Path:
    """Validate + write team.yaml, merging ``updates`` over current values.

    Accepts ONLY `reviewers` (list/str — normalized to user:<email>) and
    `lease_s` (positive int). `allow_self_review` is REFUSED: turning solo-mode
    on is a posture decision that must be a deliberate, git-visible hand edit
    (the plan-approval role check is the backstop), never a setup one-liner. The
    current allow_self_review value is preserved untouched. Raises
    TeamConfigError BEFORE any write on an unknown key / bad value."""
    p = Path(path) if path else _TEAM_DEFAULT
    current = load_team(path=p)  # validates the existing file first

    if "allow_self_review" in updates:
        raise TeamConfigError(
            "allow_self_review is a posture decision — edit team.yaml by hand so "
            "the flip is a visible git diff (the plan-approval role check is the "
            "backstop). This writer sets only reviewers and lease_s.")
    unknown = set(updates) - {"reviewers", "lease_s"}
    if unknown:
        raise TeamConfigError(
            "unknown team knob(s) %s — valid: reviewers, lease_s"
            % ", ".join(sorted(unknown)))

    reviewers = current["reviewers"]
    if "reviewers" in updates:
        raw = updates["reviewers"]
        items = raw if isinstance(raw, list) else [raw]
        reviewers = _normalize_reviewers(items)
    # A quote / newline / control char in a reviewer value would corrupt the
    # YAML (or inject a key) and silently disable the approval gate. Reject it
    # before any write — the roster must round-trip cleanly.
    for r in reviewers:
        if '"' in r or "\n" in r or "\r" in r or any(ord(c) < 32 for c in r):
            raise TeamConfigError(
                "reviewer %r contains a quote/newline/control char — refused "
                "(it would corrupt team.yaml and disable the gate)" % r)

    lease = current["claims"]["lease_s"]
    if "lease_s" in updates:
        lease = updates["lease_s"]
        if not isinstance(lease, int) or isinstance(lease, bool) or lease <= 0:
            raise TeamConfigError(
                "lease_s must be a positive integer of seconds (got %r)" % lease)

    # json.dumps yields a valid YAML flow list with proper escaping (no hand
    # quoting that breaks on a special char) — and the values are validated above.
    import json as _json
    rev_yaml = _json.dumps(reviewers)
    body = "\n".join([
        "reviewers: %s" % rev_yaml,
        "allow_self_review: %s" % ("true" if current["allow_self_review"] else "false"),
        "claims:",
        "  lease_s: %d" % lease,
    ])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_preserved_header(p) + body + "\n", encoding="utf-8")
    _trace_change("team.yaml", "reviewers=%d lease_s=%d" % (len(reviewers), lease))
    return p


def main(argv=None) -> int:
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="read/write team.yaml (roster + claim lease)")
    ap.add_argument("--file", default=None,
                    help="explicit team.yaml path (default: shipped tracked file)")
    ap.add_argument("--set", dest="sets", action="append", metavar="KEY=VALUE",
                    help="write reviewers=<csv> or lease_s=<int> (repeatable). "
                         "allow_self_review is intentionally NOT settable here.")
    args = ap.parse_args(argv)
    path = args.file
    if not args.sets:
        import json
        print(json.dumps(load_team(path=path), indent=2, ensure_ascii=False))
        return 0
    updates = {}
    for pair in args.sets:
        if "=" not in pair:
            sys.stderr.write("--set expects KEY=VALUE, got %r\n" % pair)
            return 2
        key, value = pair.split("=", 1)
        if key == "reviewers":
            updates["reviewers"] = [v for v in value.split(",") if v.strip()]
        elif key == "lease_s":
            if not value.lstrip("-").isdigit():
                sys.stderr.write("lease_s must be an integer (got %r)\n" % value)
                return 2
            updates["lease_s"] = int(value)
        elif key == "allow_self_review":
            sys.stderr.write(
                "refused: allow_self_review is a posture decision — edit "
                "team.yaml by hand (the diff is the audit).\n")
            return 2
        else:
            sys.stderr.write("unknown team knob %r (valid: reviewers, lease_s)\n" % key)
            return 2
    try:
        p = save_team(updates, path=path)
    except TeamConfigError as e:
        sys.stderr.write("TeamConfigError: %s\n" % e)
        return 1
    print("saved team → %s" % p)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
