"""test_artifact_check.py — artifact presence gate + active-plan resolution.

Policy is data-driven from harness/data/stage-policy.yaml (stage → hard,
requires, require_plan default true). Hard stage with no resolvable plan →
block with a reason offering ALL THREE exits (create a plan / set
HARNESS_ACTIVE_PLAN / set require_plan: false). Artifacts live at
plans/<active>/artifacts/<kind>.json; validation is a minimal required-fields
check (no jsonschema dep). Hard-stage verdict policy: verification has no
FAILed check; review-decision verdict must be exactly PASS (PASS_WITH_RISK is
not enough to ship).

This is a PRESENCE gate: it proves the step ran, not who ran it.
"""
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import artifact_check as ac  # noqa: E402


def _mk_plan(root: Path, name: str, status: str = "in_progress") -> Path:
    d = root / "plans" / name
    d.mkdir(parents=True)
    (d / "plan.md").write_text(
        "---\ntitle: %s\nstatus: %s\n---\n\n# %s\n" % (name, status, name),
        encoding="utf-8",
    )
    return d


def _verification(plan_dir: Path, *, verdict="PASS", checks=None, drop=None):
    rec = {
        "stage": "push", "plan": plan_dir.name, "actor": "user:alice",
        "ts": "2026-06-12T08:00:00+07:00",
        "checks": checks if checks is not None else [
            {"name": "pytest", "status": "PASS"}],
        "verdict": verdict,
    }
    for k in (drop or []):
        rec.pop(k)
    a = plan_dir / "artifacts"
    a.mkdir(exist_ok=True)
    (a / "verification.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


def _review(plan_dir: Path, *, verdict="PASS", drop=None):
    rec = {"verdict": verdict, "reviewer": "user:bob", "role": "reviewer",
           "rationale": "looks correct"}
    for k in (drop or []):
        rec.pop(k)
    a = plan_dir / "artifacts"
    a.mkdir(exist_ok=True)
    (a / "review-decision.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


def _critique(plan_dir: Path, *, verdict="PASS", drop=None):
    rec = {"verdict": verdict, "reviewer": "user:critique", "role": "critique",
           "rationale": "no blocker survived consolidation",
           "ts": "2026-06-12T08:00:00+07:00"}
    for k in (drop or []):
        rec.pop(k)
    a = plan_dir / "artifacts"
    a.mkdir(exist_ok=True)
    (a / "critique-consensus.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_ACTIVE_PLAN", raising=False)
    monkeypatch.delenv("HARNESS_STAGE_POLICY", raising=False)
    return tmp_path


class TestResolveActivePlan:
    def test_env_override_wins(self, root, monkeypatch):
        d = _mk_plan(root, "260612-0800-feature-x")
        _mk_plan(root, "260612-0900-feature-y")  # newer, but env wins
        monkeypatch.setenv("HARNESS_ACTIVE_PLAN", str(d))
        assert ac.resolve_active_plan(root) == d

    def test_env_accepts_bare_dir_name_under_plans(self, root, monkeypatch):
        d = _mk_plan(root, "260612-0800-feature-x")
        monkeypatch.setenv("HARNESS_ACTIVE_PLAN", "260612-0800-feature-x")
        assert ac.resolve_active_plan(root) == d

    def test_newest_in_progress_plan_wins(self, root):
        _mk_plan(root, "260611-0900-older")
        newer = _mk_plan(root, "260612-0900-newer")
        _mk_plan(root, "260612-9999-completed", status="completed")
        assert ac.resolve_active_plan(root) == newer

    def test_no_plans_resolves_none(self, root):
        assert ac.resolve_active_plan(root) is None

    def test_plan_without_in_progress_status_skipped(self, root):
        _mk_plan(root, "260612-0800-done", status="completed")
        assert ac.resolve_active_plan(root) is None

    def test_hyphen_status_resolves_active(self, root):
        # Skills document `status: in-progress` (hyphen); it must resolve, else a
        # legit in-progress plan blocks every hard stage.
        d = _mk_plan(root, "260612-0800-hyphen", status="in-progress")
        assert ac.resolve_active_plan(root) == d

    def test_quoted_status_resolves_active(self, root):
        # `status: "in_progress"` is valid YAML and must resolve too.
        d = _mk_plan(root, "260612-0800-quoted", status='"in_progress"')
        assert ac.resolve_active_plan(root) == d

    def test_status_in_body_code_block_is_not_frontmatter(self, root):
        # A plan.md whose FRONTMATTER has no status but whose body quotes
        # `status: in_progress` (docs, example snippet) must not be picked up
        # as the active plan.
        d = root / "plans" / "260612-9999-doc-plan"
        d.mkdir(parents=True)
        (d / "plan.md").write_text(
            "---\ntitle: doc\n---\n\n# Doc\n\nExample:\n\n"
            "```\nstatus: in_progress\n```\n",
            encoding="utf-8",
        )
        assert ac.resolve_active_plan(root) is None

    def test_body_status_does_not_shadow_frontmatter_status(self, root):
        # Frontmatter says completed; a body line says in_progress. The
        # frontmatter value is the only one that counts.
        d = root / "plans" / "260612-9998-finished"
        d.mkdir(parents=True)
        (d / "plan.md").write_text(
            "---\ntitle: x\nstatus: completed\n---\n\n"
            "Earlier this plan was `status: in_progress`.\n"
            "status: in_progress\n",
            encoding="utf-8",
        )
        assert ac.resolve_active_plan(root) is None

    def test_plan_without_frontmatter_at_all_skipped(self, root):
        d = root / "plans" / "260612-9997-bare"
        d.mkdir(parents=True)
        (d / "plan.md").write_text(
            "# Bare\n\nstatus: in_progress\n", encoding="utf-8")
        assert ac.resolve_active_plan(root) is None


class TestCheckStageSoft:
    def test_soft_stage_passes_with_nothing(self, root):
        assert ac.check_stage("commit", root) is None

    def test_unknown_stage_passes(self, root):
        assert ac.check_stage("not-a-stage", root) is None


class TestCheckStageRequirePlan:
    def test_hard_stage_no_plan_blocks_with_three_exits(self, root):
        reason = ac.check_stage("push", root)
        assert reason is not None
        assert "HARNESS_ACTIVE_PLAN" in reason
        assert "require_plan" in reason
        assert "plan" in reason.lower()  # "create a plan" guidance

    def test_require_plan_false_skips_plan_requirement(self, root, monkeypatch):
        policy = root / "policy.yaml"
        policy.write_text(
            "stages:\n  push:\n    hard: true\n    require_plan: false\n"
            "    requires: []\n", encoding="utf-8")
        monkeypatch.setenv("HARNESS_STAGE_POLICY", str(policy))
        assert ac.check_stage("push", root) is None


class TestCheckStageArtifacts:
    def test_missing_verification_blocks_naming_artifact_and_path(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        reason = ac.check_stage("push", root)
        assert "verification" in reason
        assert str(d / "artifacts") in reason  # tells WHERE to create it

    def test_complete_verification_passes_push(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        assert ac.check_stage("push", root) is None

    def test_missing_required_field_blocks_naming_field(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, drop=["actor"])
        reason = ac.check_stage("push", root)
        assert reason is not None and "actor" in reason

    def test_malformed_json_blocks(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        a = d / "artifacts"
        a.mkdir()
        (a / "verification.json").write_text("{not json", encoding="utf-8")
        reason = ac.check_stage("push", root)
        assert reason is not None and "verification" in reason

    def test_failed_check_blocks_naming_the_check(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, checks=[{"name": "pytest", "status": "FAIL"}])
        reason = ac.check_stage("push", root)
        assert reason is not None and "pytest" in reason

    def test_unknown_check_status_fails_closed(self, root):
        # per-check status is a closed enum {PASS,FAIL,SKIP}; anything else
        # (a crashed verifier writing ERROR/TIMEOUT, a typo) must fail CLOSED,
        # not slip through as "not FAIL → pass".
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, checks=[{"name": "pytest", "status": "ERROR"}])
        reason = ac.check_stage("push", root)
        assert reason is not None and "pytest" in reason

    def test_missing_check_status_fails_closed(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, checks=[{"name": "pytest"}])  # no status field
        assert ac.check_stage("push", root) is not None

    def test_skip_check_still_passes(self, root):
        # SKIP is a valid non-failure per the schema → must not block
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, checks=[{"name": "pytest", "status": "PASS"},
                                 {"name": "lint", "status": "SKIP"}])
        assert ac.check_stage("push", root) is None

    def test_blocked_verification_verdict_blocks_even_with_passing_checks(self, root):
        # The verifier's own overall verdict is honored: BLOCKED stops the
        # stage even when every named check passed (the verdict can carry a
        # reason no single check expresses).
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, verdict="BLOCKED",
                      checks=[{"name": "pytest", "status": "PASS"}])
        reason = ac.check_stage("push", root)
        assert reason is not None and "BLOCKED" in reason

    def test_pass_with_risk_verification_still_passes_push(self, root):
        # PASS_WITH_RISK on the VERIFICATION artifact is a conscious
        # soft-accept and does not block (review-decision is the artifact
        # that demands exactly PASS).
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, verdict="PASS_WITH_RISK")
        assert ac.check_stage("push", root) is None

    def test_pr_requires_review_decision_too(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        reason = ac.check_stage("pr", root)
        assert reason is not None and "review-decision" in reason

    def test_pr_with_pass_review_passes(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        _review(d)
        _mk_team(root)
        _approve(d, root)
        _critique(d)
        assert ac.check_stage("pr", root) is None

    def test_pass_with_risk_review_is_not_enough_for_hard_stage(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        _review(d, verdict="PASS_WITH_RISK")
        reason = ac.check_stage("pr", root)
        assert reason is not None
        assert "PASS_WITH_RISK" in reason  # names what it got vs what it needs

    def test_blocked_review_blocks(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        _review(d, verdict="BLOCKED")
        assert ac.check_stage("pr", root) is not None


def _mk_team(root: Path, reviewers=("user:bob",), allow_self_review=False):
    d = root / "harness" / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "team.yaml").write_text(
        "reviewers: [%s]\nallow_self_review: %s\nclaims: {lease_s: 14400}\n"
        % (", ".join('"%s"' % r for r in reviewers),
           "true" if allow_self_review else "false"),
        encoding="utf-8")


def _approve(plan_dir: Path, root: Path, *, reviewer="user:bob",
             author="user:alice", verdict="APPROVED", stale_hash=False,
             drop=None):
    import plan_approval as pa
    rec = {
        "schema": "plan-approval/v1", "plan": plan_dir.name,
        "plan_hash": "0" * 12 if stale_hash else pa.plan_hash(plan_dir),
        "author": author, "reviewer": reviewer, "verdict": verdict,
        "rationale": "reviewed", "ts": "2026-06-12T08:00:00+07:00",
    }
    if not stale_hash:
        rec["file_hashes"] = pa.file_hashes(plan_dir)
    for k in (drop or []):
        rec.pop(k)
    a = plan_dir / "artifacts"
    a.mkdir(exist_ok=True)
    (a / "plan-approval.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


class TestPlanApprovalGate:
    """pr/ship/deploy demand a valid plan-approval; push must NOT change."""

    def _ready(self, root, **team_kw):
        d = _mk_plan(root, "260612-0800-feature-x")
        (d / "plan.md").write_text(
            "---\ntitle: x\nstatus: in_progress\n---\n\n# X\n\nIntent.\n\n"
            "## Phases\n\n| 1 | Pending |\n\n## Notes\n\n- n1\n",
            encoding="utf-8")
        (d / "phase-01-build.md").write_text(
            "---\nphase: 1\nstatus: pending\n---\n\n# P1\n\nfirst phase body\n",
            encoding="utf-8")
        _verification(d)
        _review(d)
        _mk_team(root, **team_kw)
        _critique(d)
        return d

    def test_push_does_not_require_plan_approval(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        assert ac.check_stage("push", root) is None

    def test_pr_missing_plan_approval_blocks_naming_cli(self, root):
        self._ready(root)
        reason = ac.check_stage("pr", root)
        assert reason is not None and "plan-approval" in reason
        assert "plan_approval.py" in reason  # points at the writing CLI

    def test_pr_with_valid_approval_passes(self, root):
        d = self._ready(root)
        _approve(d, root)
        assert ac.check_stage("pr", root) is None

    def test_ship_and_deploy_also_require_it(self, root):
        d = self._ready(root)
        for stage in ("ship", "deploy"):
            reason = ac.check_stage(stage, root)
            assert reason is not None and "plan-approval" in reason
        _approve(d, root)
        for stage in ("ship", "deploy"):
            assert ac.check_stage(stage, root) is None

    def test_rejected_verdict_blocks(self, root):
        d = self._ready(root)
        _approve(d, root, verdict="REJECTED")
        reason = ac.check_stage("pr", root)
        assert reason is not None and "REJECTED" in reason

    def test_missing_required_field_blocks_naming_field(self, root):
        d = self._ready(root)
        _approve(d, root, drop=["plan_hash"])
        reason = ac.check_stage("pr", root)
        assert reason is not None and "plan_hash" in reason

    def test_reviewer_not_in_roster_blocks_actionably(self, root):
        d = self._ready(root, reviewers=("user:someone-else",))
        _approve(d, root, reviewer="user:bob")
        reason = ac.check_stage("pr", root)
        assert reason is not None and "team.yaml" in reason

    def test_self_review_blocks_even_via_agent_personas(self, root):
        d = self._ready(root, reviewers=("user:alice",))
        _approve(d, root, reviewer="user:alice/agent:reviewer",
                 author="user:alice/agent:planner")
        reason = ac.check_stage("pr", root)
        assert reason is not None and "self" in reason.lower()

    def test_solo_mode_lets_rostered_self_review_pass(self, root):
        d = self._ready(root, reviewers=("user:alice",),
                        allow_self_review=True)
        _approve(d, root, reviewer="user:alice", author="user:alice")
        assert ac.check_stage("pr", root) is None

    def test_body_edit_after_approval_blocks_naming_changed_file(self, root):
        d = self._ready(root)
        _approve(d, root)
        p1 = d / "phase-01-build.md"
        p1.write_text(p1.read_text(encoding="utf-8").replace(
            "first phase body", "DIFFERENT body"), encoding="utf-8")
        reason = ac.check_stage("pr", root)
        assert reason is not None
        assert "phase-01-build.md" in reason  # names the drifted file
        assert "duyệt lại" in reason or "re-approve" in reason

    def test_frontmatter_and_phases_table_edits_do_not_block(self, root, monkeypatch):
        # The cook workflow legitimately mutates frontmatter status and the
        # plan.md Phases table after approval — the normalized hash must
        # carve exactly those out. (Status flips also change which plan is
        # ACTIVE, so the plan is pinned via env here — the gate question
        # under test is the hash, not plan resolution.)
        d = self._ready(root)
        _approve(d, root)
        monkeypatch.setenv("HARNESS_ACTIVE_PLAN", str(d))
        pm = d / "plan.md"
        pm.write_text(pm.read_text(encoding="utf-8").replace(
            "status: in_progress", "status: completed"), encoding="utf-8")
        p1 = d / "phase-01-build.md"
        p1.write_text(p1.read_text(encoding="utf-8").replace(
            "status: pending", "status: completed"), encoding="utf-8")
        pm2 = pm.read_text(encoding="utf-8").replace(
            "| 1 | Pending |", "| 1 | Completed |\n| 2 | New row |")
        pm.write_text(pm2, encoding="utf-8")
        assert ac.check_stage("pr", root) is None

    def test_stale_hash_blocks_with_reapprove_guidance(self, root):
        d = self._ready(root)
        _approve(d, root, stale_hash=True)
        reason = ac.check_stage("pr", root)
        assert reason is not None and "plan_approval.py" in reason

    def test_missing_team_yaml_blocks_with_break_glass_path(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        _review(d)
        _approve(d, root)  # roster file intentionally absent
        reason = ac.check_stage("pr", root)
        assert reason is not None
        assert "reviewers" in reason and "team.yaml" in reason
        # Gate A's remediation target is itself write-guarded in an
        # installed repo: the reason must name the break-glass route.
        assert "editor" in reason.lower()

    def test_malformed_team_yaml_blocks_actionably(self, root):
        d = self._ready(root)
        _approve(d, root)
        (root / "harness" / "data" / "team.yaml").write_text(
            "reviewers: notalist\n", encoding="utf-8")
        reason = ac.check_stage("pr", root)
        assert reason is not None and "team.yaml" in reason


class TestPlannotatorReviewHint:
    """A MISSING review artifact resurfaces the Plannotator review option in
    the block reason — the reliable backstop so the option is never silently
    forgotten when the LLM skips offering it at the gate."""

    _MARK = "Plannotator"
    _RULE = "plannotator-review-gates.md"

    def test_missing_verification_reason_offers_plannotator(self, root):
        _mk_plan(root, "260612-0800-feature-x")
        reason = ac.check_stage("push", root)
        assert self._MARK in reason and self._RULE in reason

    def test_missing_review_decision_reason_offers_plannotator(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        reason = ac.check_stage("pr", root)
        assert "review-decision" in reason
        assert self._MARK in reason and self._RULE in reason

    def test_missing_plan_approval_reason_offers_plannotator(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d)
        _review(d)
        reason = ac.check_stage("pr", root)
        assert "plan-approval" in reason
        assert self._MARK in reason and self._RULE in reason

    def test_present_but_failing_artifact_keeps_reason_clean(self, root):
        # The hint is for the MISSING case (no review happened yet). A present
        # artifact with a bad verdict is a content problem, not a "go review"
        # nudge — it must not carry the offer.
        d = _mk_plan(root, "260612-0800-feature-x")
        _verification(d, verdict="BLOCKED")
        reason = ac.check_stage("push", root)
        assert self._MARK not in reason


class TestCritiqueGateHint:
    """A stage requiring critique-consensus but missing it must name the exact
    command that produces the artifact (/hs-think:critique --gate) — not just 'create
    the json'. Mirrors plan-approval, which already names plan_approval.py."""

    def test_missing_critique_consensus_names_the_gate_command(self, root):
        d = _mk_plan(root, "260612-0800-feature-x")
        reason = ac._check_artifact(d, "critique-consensus", root)
        assert "critique-consensus" in reason
        assert "hs-think:critique" in reason and "--gate" in reason

    def test_present_failing_critique_consensus_is_a_content_problem(self, root):
        # present-but-BLOCKED is a verdict problem, not a "go run it" nudge —
        # it must NOT carry the run-the-gate command hint.
        d = _mk_plan(root, "260612-0800-feature-x")
        _critique(d, verdict="BLOCKED")
        reason = ac._check_artifact(d, "critique-consensus", root)
        assert "verdict" in reason
        assert "--gate" not in reason


class TestPolicyLoad:
    def test_missing_policy_file_raises_loud(self, root, monkeypatch):
        monkeypatch.setenv("HARNESS_STAGE_POLICY", str(root / "nope.yaml"))
        with pytest.raises(Exception) as exc:
            ac.check_stage("push", root)
        msg = str(exc.value)
        assert "policy" in msg.lower()
        assert str(root / "nope.yaml") in msg          # names the RESOLVED path
        # remediation must point at the env override, not blindly the shipped
        # default — restoring harness/data/ does nothing while the env var points
        # elsewhere (the .harness-dev/ dev-override trap).
        assert "HARNESS_STAGE_POLICY" in msg

    def test_default_policy_declares_all_detector_stages(self):
        policy = ac.load_policy()
        for stage in ("commit", "push", "pr", "ship", "deploy"):
            assert stage in policy["stages"]
