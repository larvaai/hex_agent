"""test_plan_approval.py — role-consistency check on attribution + the
normalized plan-dir hash behind the plan-approval artifact.

This is NOT authentication: actor strings are env-derived and spoofable by
design. The check raises the price of self-approval (reviewer must be in the
tracked roster and a different person than the author, with `/agent:*`
personas collapsing to their user), it does not prove identity.

The hash is over NORMALIZED plan content: YAML frontmatter is stripped from
every file and the `## Phases` section is stripped from plan.md, because the
cook workflow legitimately mutates exactly those two regions after approval.
Hash-the-bytes would go stale on every run and train reviewers to
rubber-stamp; the body — the thing approval is about — stays pinned.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import plan_approval as pa  # noqa: E402


def _mk_plan(root: Path, name="260612-0900-w2-thing", author=None):
    d = root / "plans" / name
    d.mkdir(parents=True)
    fm_author = ("author: %s\n" % author) if author else ""
    (d / "plan.md").write_text(
        "---\ntitle: %s\nstatus: pending\n%s---\n\n# Thing\n\nBody intent.\n\n"
        "## Phases\n\n| Phase | Status |\n|---|---|\n| 1 | Pending |\n\n"
        "## Acceptance\n\n- works\n" % (name, fm_author),
        encoding="utf-8")
    (d / "phase-01-build.md").write_text(
        "---\nphase: 1\nstatus: pending\n---\n\n# Phase 1\n\nDo the thing.\n",
        encoding="utf-8")
    (d / "phase-02-test.md").write_text(
        "---\nphase: 2\nstatus: pending\n---\n\n# Phase 2\n\nProve it.\n",
        encoding="utf-8")
    return d


def _mk_team(root: Path, reviewers=("user:rev@x",), allow_self_review=False):
    d = root / "harness" / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "team.yaml").write_text(
        "reviewers: [%s]\nallow_self_review: %s\nclaims: {lease_s: 14400}\n"
        % (", ".join('"%s"' % r for r in reviewers),
           "true" if allow_self_review else "false"),
        encoding="utf-8")


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_ROOT", str(tmp_path))
    monkeypatch.setenv("HARNESS_STATE_DIR", str(tmp_path / "state"))
    _mk_team(tmp_path)
    return tmp_path


# ---------- normalize ----------

class TestNormalizeActor:
    def test_agent_suffix_is_cut(self):
        assert pa.normalize_actor("user:a@x/agent:reviewer") == "user:a@x"

    def test_plain_user_unchanged(self):
        assert pa.normalize_actor("user:a@x") == "user:a@x"

    def test_ci_unchanged(self):
        assert pa.normalize_actor("ci") == "ci"

    def test_two_personas_of_one_user_collapse_to_same(self):
        a = pa.normalize_actor("user:a@x/agent:planner")
        b = pa.normalize_actor("user:a@x/agent:reviewer")
        assert a == b


# ---------- role rule (4 quadrants × solo mode) ----------

class TestRoleRule:
    TEAM = {"reviewers": ["user:rev@x"], "allow_self_review": False,
            "claims": {"lease_s": 14400}}

    def test_in_roster_and_distinct_passes(self):
        assert pa.check_role("user:rev@x", "user:auth@x", self.TEAM) is None

    def test_in_roster_but_same_person_fails(self):
        reason = pa.check_role("user:rev@x", "user:rev@x", self.TEAM)
        assert reason is not None and "self" in reason.lower()

    def test_not_in_roster_fails_naming_roster_file(self):
        reason = pa.check_role("user:other@x", "user:auth@x", self.TEAM)
        assert reason is not None and "team.yaml" in reason

    def test_not_in_roster_and_same_person_fails(self):
        team = {"reviewers": [], "allow_self_review": False}
        assert pa.check_role("user:a@x", "user:a@x", team) is not None

    def test_personas_of_same_user_cannot_cross_approve(self):
        team = {"reviewers": ["user:a@x"], "allow_self_review": False}
        reason = pa.check_role("user:a@x/agent:reviewer",
                               "user:a@x/agent:planner", team)
        assert reason is not None and "self" in reason.lower()

    def test_reviewer_with_agent_suffix_matches_bare_roster_entry(self):
        assert pa.check_role("user:rev@x/agent:r", "user:auth@x", self.TEAM) is None

    def test_case_variant_cannot_self_approve(self):
        # reviewer email is derived live from git config (often mixed-case) while
        # the author was recorded in another case — the same human must NOT slip
        # past the self-review block on a casing difference.
        team = {"reviewers": ["user:bob@x.com"], "allow_self_review": False}
        reason = pa.check_role("user:BOB@x.com", "user:bob@x.com", team)
        assert reason is not None and "self" in reason.lower()

    def test_whitespace_variant_cannot_self_approve(self):
        team = {"reviewers": ["user:bob@x.com"], "allow_self_review": False}
        reason = pa.check_role("user:bob@x.com ", "user:bob@x.com", team)
        assert reason is not None and "self" in reason.lower()

    def test_roster_membership_is_case_insensitive(self):
        # a case-variant rostered reviewer (vs a distinct author) is still rostered
        team = {"reviewers": ["user:bob@x.com"], "allow_self_review": False}
        assert pa.check_role("user:BOB@x.com", "user:alice@x.com", team) is None

    def test_solo_mode_allows_self_but_still_requires_roster(self):
        team = {"reviewers": ["user:a@x"], "allow_self_review": True}
        assert pa.check_role("user:a@x", "user:a@x", team) is None
        team2 = {"reviewers": [], "allow_self_review": True}
        assert pa.check_role("user:a@x", "user:a@x", team2) is not None


# ---------- normalized plan-dir hash ----------

class TestPlanHash:
    def test_hash_is_12_hex(self, root):
        d = _mk_plan(root)
        h = pa.plan_hash(d)
        assert len(h) == 12 and int(h, 16) >= 0

    def test_frontmatter_status_flip_does_not_change_hash(self, root):
        d = _mk_plan(root)
        before = pa.plan_hash(d)
        for f in (d / "plan.md", d / "phase-01-build.md"):
            f.write_text(f.read_text(encoding="utf-8").replace(
                "status: pending", "status: in_progress"), encoding="utf-8")
        assert pa.plan_hash(d) == before

    def test_phases_table_edit_in_plan_md_does_not_change_hash(self, root):
        d = _mk_plan(root)
        before = pa.plan_hash(d)
        pm = d / "plan.md"
        pm.write_text(pm.read_text(encoding="utf-8").replace(
            "| 1 | Pending |", "| 1 | Completed ✅ |\n| 2 | In progress |"),
            encoding="utf-8")
        assert pa.plan_hash(d) == before

    def test_body_edit_in_plan_md_changes_hash(self, root):
        d = _mk_plan(root)
        before = pa.plan_hash(d)
        pm = d / "plan.md"
        pm.write_text(pm.read_text(encoding="utf-8").replace(
            "Body intent.", "Body intent CHANGED."), encoding="utf-8")
        assert pa.plan_hash(d) != before

    def test_body_edit_in_phase_file_changes_hash(self, root):
        d = _mk_plan(root)
        before = pa.plan_hash(d)
        p1 = d / "phase-01-build.md"
        p1.write_text(p1.read_text(encoding="utf-8").replace(
            "Do the thing.", "Do a different thing."), encoding="utf-8")
        assert pa.plan_hash(d) != before

    def test_new_phase_file_changes_hash(self, root):
        d = _mk_plan(root)
        before = pa.plan_hash(d)
        (d / "phase-03-extra.md").write_text(
            "---\nphase: 3\n---\n\n# Phase 3\n\nNew scope.\n", encoding="utf-8")
        assert pa.plan_hash(d) != before

    def test_phases_section_outside_plan_md_is_not_stripped(self, root):
        # Only plan.md owns a legitimately-mutating ## Phases section; the
        # same heading inside a phase file is body and stays pinned.
        d = _mk_plan(root)
        p1 = d / "phase-01-build.md"
        p1.write_text(p1.read_text(encoding="utf-8")
                      + "\n## Phases\n\nnarrative\n", encoding="utf-8")
        before = pa.plan_hash(d)
        p1.write_text(p1.read_text(encoding="utf-8").replace(
            "narrative", "narrative CHANGED"), encoding="utf-8")
        assert pa.plan_hash(d) != before

    def test_file_hashes_names_each_file(self, root):
        d = _mk_plan(root)
        fh = pa.file_hashes(d)
        assert set(fh) == {"plan.md", "phase-01-build.md", "phase-02-test.md"}
        assert all(len(v) == 12 for v in fh.values())


# ---------- write_approval (lib) ----------

class TestWriteApproval:
    def test_writes_schema_v1_artifact_with_hash_and_trace(self, root, monkeypatch):
        monkeypatch.setenv("HARNESS_USER", "rev@x")
        d = _mk_plan(root, author="user:auth@x")
        out = pa.write_approval(d, verdict="APPROVED", rationale="solid")
        assert out["ok"], out
        rec = json.loads((d / "artifacts" / "plan-approval.json").read_text(
            encoding="utf-8"))
        assert rec["schema"] == "plan-approval/v1"
        assert rec["plan"] == d.name
        assert rec["plan_hash"] == pa.plan_hash(d)
        assert rec["author"] == "user:auth@x"
        assert rec["reviewer"].startswith("user:rev@x")
        assert rec["verdict"] == "APPROVED"
        assert rec["rationale"] == "solid"
        assert "ts" in rec
        assert set(rec["file_hashes"]) == set(pa.file_hashes(d))
        trace = "".join(p.read_text(encoding="utf-8") for p in
                        (root / "state" / "trace").glob("trace-*.jsonl"))
        assert "plan_approval" in trace

    def test_refuses_to_write_when_rule_fails(self, root, monkeypatch):
        monkeypatch.setenv("HARNESS_USER", "auth@x")  # reviewer == author
        d = _mk_plan(root, author="user:auth@x")
        out = pa.write_approval(d, verdict="APPROVED", rationale="lgtm")
        assert out["ok"] is False
        assert not (d / "artifacts" / "plan-approval.json").exists()

    def test_author_resolution_falls_back_to_explicit_arg(self, root, monkeypatch):
        monkeypatch.setenv("HARNESS_USER", "rev@x")
        d = _mk_plan(root)  # no author frontmatter
        out = pa.write_approval(d, verdict="APPROVED", rationale="r")
        assert out["ok"] is False and "--author" in out["error"]
        out2 = pa.write_approval(d, verdict="APPROVED", rationale="r",
                                 author="user:auth@x")
        assert out2["ok"]

    def test_never_writes_with_empty_author(self, root, monkeypatch):
        monkeypatch.setenv("HARNESS_USER", "rev@x")
        d = _mk_plan(root)
        out = pa.write_approval(d, verdict="APPROVED", rationale="r", author="")
        assert out["ok"] is False
        assert not (d / "artifacts" / "plan-approval.json").exists()


# ---------- CLI ----------

class TestCLI:
    def _env(self, root, user="rev@x"):
        env = dict(os.environ)
        env["HARNESS_ROOT"] = str(root)
        env["HARNESS_STATE_DIR"] = str(root / "state")
        env["HARNESS_USER"] = user
        env.pop("HARNESS_AGENT", None)
        return env

    def test_cli_approves_and_exits_zero(self, root):
        d = _mk_plan(root, author="user:auth@x")
        out = subprocess.run(
            [sys.executable, str(_SCRIPTS / "plan_approval.py"),
             "--plan", str(d), "--verdict", "APPROVED",
             "--rationale", "reviewed end to end"],
            capture_output=True, text=True, env=self._env(root), timeout=30)
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout)["ok"]
        assert (d / "artifacts" / "plan-approval.json").exists()

    def test_cli_rejects_self_review_nonzero_no_artifact(self, root):
        d = _mk_plan(root, author="user:rev@x")  # author == roster reviewer
        out = subprocess.run(
            [sys.executable, str(_SCRIPTS / "plan_approval.py"),
             "--plan", str(d), "--verdict", "APPROVED", "--rationale", "x"],
            capture_output=True, text=True, env=self._env(root), timeout=30)
        assert out.returncode != 0
        result = json.loads(out.stdout)
        assert result["ok"] is False
        assert "allow_self_review" in result["error"]
        assert not (d / "artifacts" / "plan-approval.json").exists()
