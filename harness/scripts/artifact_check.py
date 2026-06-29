#!/usr/bin/env python3
"""artifact_check.py — artifact presence gate + active-plan resolution.

check_stage(stage, root) returns None (pass) or a BLOCK REASON string — the
core contract run_compliance_hook expects, so the gate hook stays a thin
shell around this module.

Policy is data-driven from harness/data/stage-policy.yaml (override:
HARNESS_STAGE_POLICY env). A missing/malformed policy raises — the compliance
wrapper turns that into exit 2 + guidance (a gate without its policy must not
silently pass).

HONESTY: this is a PRESENCE gate. It proves the step RAN — the
artifact exists, parses, and carries the required fields — it does NOT verify
WHO ran it. Actor fields are attribution, never authorization. The
plan-approval kind adds a role-CONSISTENCY check (reviewer in the tracked
roster, normalized distinct from the author) plus a normalized plan-dir hash:
that raises the price of an agent approving its own plan, it still does not
authenticate anyone — actor strings stay spoofable by design.

Artifacts (machine-written JSON) live at:
    plans/<active-plan>/artifacts/<kind>.json
Active plan resolution: HARNESS_ACTIVE_PLAN env (path or bare dir name under
plans/) > newest plans/*/plan.md with `status: in_progress` frontmatter.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_POLICY_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "stage-policy.yaml"

# Minimal required-fields contract per artifact kind (no jsonschema dep —
# presence + shape only; richer JSON-schemas in harness/schemas/ document the
# full shape for humans and future schema validators).
_REQUIRED_FIELDS = {
    "verification": ("stage", "plan", "actor", "ts", "checks", "verdict"),
    "review-decision": ("verdict", "reviewer", "role", "rationale"),
    "critique-consensus": ("verdict", "reviewer", "role", "rationale", "ts"),
    "plan-approval": ("schema", "plan", "plan_hash", "author", "reviewer",
                      "verdict", "rationale", "ts"),
}

# Cache keyed by policy path: one parse per file per process, and an env
# override pointing elsewhere (tests, odd layouts) naturally misses the cache.
_policy_cache = {}

# When a review artifact is MISSING (no review happened yet), the block reason
# resurfaces the Plannotator review option — the reliable backstop so the
# offer is never silently dropped if the skill forgot to make it at the gate.
# Scoped to the missing case: a present-but-failing artifact is a content
# problem, not a "go review" nudge.
_REVIEW_KINDS = ("plan-approval", "review-decision", "verification")
_PLANNOTATOR_HINT = (
    " — or invite a reviewer via [Review directly (Plannotator) / Approve / "
    "Reject]; see harness/rules/plannotator-review-gates.md"
)


def _policy_path() -> Path:
    raw = os.environ.get("HARNESS_STAGE_POLICY")
    return Path(raw) if raw else _POLICY_DEFAULT


def load_policy() -> dict:
    """Parse stage-policy.yaml once per path per process. Raises LOUD on a
    missing or malformed file — the gate's policy is its spine, never
    default-to-pass."""
    p = _policy_path()
    key = str(p)
    if key in _policy_cache:
        return _policy_cache[key]
    import yaml

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(
            "stage policy missing at %s — restore THAT file. Its path comes from "
            "$HARNESS_STAGE_POLICY when that env var is set (e.g. a gitignored "
            ".harness-dev/ dev override), otherwise the shipped "
            "harness/data/stage-policy.yaml. Restoring the shipped default does "
            "not help while the env var points elsewhere." % p
        )
    stages = (raw or {}).get("stages") if isinstance(raw, dict) else None
    if not isinstance(stages, dict) or not stages:
        raise RuntimeError(
            "stage policy %s is malformed — expected a top-level `stages:` mapping" % p
        )
    _policy_cache[key] = {"stages": stages}
    return _policy_cache[key]


# The frontmatter block: opening `---` at byte 0, body, closing `---`/`...`
# on its own line. status is read ONLY from inside this block — a
# `status: in_progress` quoted in the plan body (docs, code examples) must
# never make that plan active.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)^(?:---|\.\.\.)\s*$",
                             re.MULTILINE | re.DOTALL)
_STATUS_RE = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)


def _frontmatter_status(text):
    fm = _FRONTMATTER_RE.match(text)
    if not fm:
        return None
    m = _STATUS_RE.search(fm.group(1))
    return m.group(1) if m else None


def resolve_active_plan(root):
    """The active plan dir, or None.

    HARNESS_ACTIVE_PLAN wins: an absolute/relative path, or a bare dir name
    under plans/. Fallback: newest (by dir name — timestamped) plans/*/plan.md
    whose frontmatter says `status: in_progress`."""
    root = Path(root)
    raw = os.environ.get("HARNESS_ACTIVE_PLAN")
    if raw:
        cand = Path(raw)
        if not cand.is_absolute():
            under_plans = root / "plans" / raw
            cand = under_plans if under_plans.is_dir() else root / raw
        return cand if cand.is_dir() else None

    plans = root / "plans"
    if not plans.is_dir():
        return None
    for d in sorted((x for x in plans.iterdir() if x.is_dir()),
                    key=lambda x: x.name, reverse=True):
        pm = d / "plan.md"
        if not pm.is_file():
            continue
        try:
            status = _frontmatter_status(pm.read_text(encoding="utf-8"))
        except OSError:
            continue
        if status and status.strip("'\"").replace("-", "_") == "in_progress":
            return d
    return None


def _load_artifact(plan_dir: Path, kind: str):
    """(record, problem). Missing file → (None, 'missing'); bad JSON/shape →
    (None, description); ok → (dict, None)."""
    p = plan_dir / "artifacts" / ("%s.json" % kind)
    if not p.is_file():
        return None, "missing"
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return None, "unreadable (%s)" % e
    if not isinstance(rec, dict):
        return None, "not a JSON object"
    return rec, None


def _check_artifact(plan_dir: Path, kind: str, root=None):
    """None when the artifact satisfies the presence + verdict policy, else
    an actionable reason naming the artifact, the field, and the fix path."""
    where = plan_dir / "artifacts"
    rec, problem = _load_artifact(plan_dir, kind)
    if rec is None:
        hint = _PLANNOTATOR_HINT if kind in _REVIEW_KINDS else ""
        if kind == "plan-approval":
            return (
                "artifact 'plan-approval' %s — a rostered reviewer writes it "
                "via: python3 harness/scripts/plan_approval.py --plan %s "
                "--verdict APPROVED --rationale '...' (the CLI enforces the "
                "role rule before writing)%s" % (problem, plan_dir, hint)
            )
        if kind == "critique-consensus":
            return (
                "artifact 'critique-consensus' %s — run the critique in GATE mode "
                "to produce it: /hs-think:critique --gate (writes %s/critique-consensus"
                ".json with the consolidated machine verdict; a hard stage passes "
                "only on verdict PASS). Plain /hs-think:critique is advisory and writes "
                "no gate artifact." % (problem, where)
            )
        return (
            "artifact %r %s — create %s/%s.json (see harness/schemas/)%s"
            % (kind, problem, where, kind, hint)
        )
    missing = [f for f in _REQUIRED_FIELDS.get(kind, ()) if f not in rec]
    if missing:
        return (
            "artifact %r at %s/%s.json is missing required field(s): %s"
            % (kind, where, kind, ", ".join(missing))
        )
    if kind == "verification":
        checks = rec.get("checks")
        if not isinstance(checks, list) or not checks:
            return ("artifact 'verification' has no checks — at least one "
                    "named check is required")
        # PASS-allowlist, not a FAIL-denylist: per-check status is a closed enum
        # {PASS,FAIL,SKIP} (schema), so block unless every check is explicitly
        # PASS or SKIP. A crashed verifier writing ERROR/TIMEOUT, a missing
        # status, a typo, or a non-dict entry then fails CLOSED (fail-open here
        # would let a broken verifier pass a hard stage).
        bad = [c.get("name", "?") if isinstance(c, dict) else "?"
               for c in checks
               if not isinstance(c, dict) or c.get("status") not in ("PASS", "SKIP")]
        if bad:
            return ("verification has non-passing check(s): %s — every check must "
                    "be PASS or SKIP (a FAILed, ERRORed, or missing status fails "
                    "closed). Fix and re-run before this stage" % ", ".join(bad))
        # The verifier's overall verdict is honored alongside per-check
        # status: BLOCKED can carry a reason no single check expresses
        # (e.g. the suite could not run at all, every check SKIPped).
        if rec.get("verdict") == "BLOCKED":
            return ("verification verdict is BLOCKED — the verifier stopped "
                    "this stage even though no named check FAILed; resolve "
                    "the blocker and re-run verification")
    if kind == "review-decision":
        verdict = rec.get("verdict")
        if verdict != "PASS":
            return (
                "review-decision verdict is %r but a hard stage needs exactly "
                "PASS (PASS_WITH_RISK is a conscious soft-accept, not a ship "
                "license; BLOCKED means stop)" % verdict
            )
    if kind == "critique-consensus":
        verdict = rec.get("verdict")
        if verdict != "PASS":
            return (
                "critique-consensus verdict is %r but a hard stage needs exactly "
                "PASS (PASS_WITH_RISK is a conscious soft-accept; BLOCKED means "
                "stop)" % verdict
            )
    if kind == "plan-approval":
        return _check_plan_approval(plan_dir, rec, root)
    return None


def _check_plan_approval(plan_dir: Path, rec: dict, root):
    """Role-consistency + anti-drift validation of a present, well-shaped
    plan-approval record. Local file reads only — the gate path stays
    network-free."""
    import plan_approval as pa

    if rec.get("verdict") != "APPROVED":
        return (
            "plan-approval verdict is %r — the plan must be APPROVED by a "
            "rostered reviewer before this stage (re-run plan_approval.py "
            "after the concerns are addressed)" % rec.get("verdict")
        )

    if root is None:
        import harness_paths
        root = harness_paths.root()
    try:
        import team_config
        team = team_config.load_team(
            path=Path(root) / "harness" / "data" / "team.yaml")
    except Exception as e:
        return (
            "plan-approval cannot be validated: %s — fix `reviewers: [...]` "
            "in harness/data/team.yaml. In an installed repo that file is "
            "config-edit-gated in-session: edit it with a normal editor "
            "outside the agent session (the diff stays visible in git)" % e
        )
    reason = pa.check_role(rec.get("reviewer", ""), rec.get("author", ""), team)
    if reason:
        return "plan-approval is invalid: %s" % reason

    current = pa.plan_hash(plan_dir)
    if rec.get("plan_hash") != current:
        recorded = rec.get("file_hashes") or {}
        now = pa.file_hashes(plan_dir)
        drifted = sorted(
            set(k for k in now if now.get(k) != recorded.get(k))
            | set(k for k in recorded if k not in now))
        return (
            "plan content changed after approval (drifted: %s) — the plan "
            "body must be re-approved: a rostered reviewer "
            "re-runs plan_approval.py. Frontmatter status and the plan.md "
            "Phases table are exempt; any body edit re-opens approval — "
            "that friction is the anti-drift working, not a bug"
            % (", ".join(drifted) or "unknown — re-run plan_approval.py")
        )
    return None


def check_stage(stage, root):
    """None = pass; string = block reason. Soft/unknown stages never block."""
    policy = load_policy()["stages"].get(stage)
    if not isinstance(policy, dict) or not policy.get("hard"):
        return None

    if policy.get("require_plan", True):
        plan_dir = resolve_active_plan(root)
        if plan_dir is None:
            return (
                "hard stage %r needs an active plan but none resolved. Three "
                "exits: (1) create a plan under plans/ with `status: "
                "in_progress` frontmatter; (2) set HARNESS_ACTIVE_PLAN to the "
                "plan dir; (3) set `require_plan: false` for this stage in "
                "harness/data/stage-policy.yaml (tracked in git)" % stage
            )
    else:
        plan_dir = resolve_active_plan(root)

    for kind in policy.get("requires") or []:
        if plan_dir is None:
            return ("hard stage %r requires artifact %r but no active plan "
                    "dir is resolvable to hold it" % (stage, kind))
        reason = _check_artifact(plan_dir, kind, root=root)
        if reason:
            return reason
    return None
