"""test_critique_gate.py — critique-consensus artifact gate policy.

The critique skill in gate mode writes a machine-readable verdict to
plans/<active>/artifacts/critique-consensus.json. Its verdict policy mirrors
review-decision: a hard stage passes ONLY on verdict exactly PASS —
PASS_WITH_RISK is a conscious soft-accept, BLOCKED means stop.

Enforcement is decoupled into stage-policy and SHIPS OFF: the default
harness/data/stage-policy.yaml lists critique-consensus at NO stage, so a fresh
(spine-only) install is never surprise-blocked by an artifact whose producer
(hs-think:critique) is an opt-in plugin. Turning it on is a tracked one-line
stage-policy edit; the per-mechanism unit tests below opt in via a temp policy
(HARNESS_STAGE_POLICY). The default posture is locked by
TestShippedPolicyDoesNotDefaultGateCritique. This is a PRESENCE gate — it proves
the critique ran, not who ran it.
"""
import json
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parent.parent
_SCRIPTS = _HARNESS / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import artifact_check as ac  # noqa: E402

_SCHEMA = _HARNESS / "schemas" / "artifact-critique-consensus.json"


def _mk_plan(root: Path, name: str = "260615-2132-feature-x") -> Path:
    d = root / "plans" / name
    d.mkdir(parents=True)
    (d / "plan.md").write_text(
        "---\ntitle: %s\nstatus: in_progress\n---\n\n# %s\n" % (name, name),
        encoding="utf-8",
    )
    return d


def _consensus(plan_dir: Path, *, verdict="PASS", drop=None):
    rec = {
        "verdict": verdict,
        "reviewer": "user:critique",
        "role": "critique",
        "rationale": "no blocker survived consolidation",
        "ts": "2026-06-15T21:32:00+07:00",
    }
    for k in (drop or []):
        rec.pop(k)
    a = plan_dir / "artifacts"
    a.mkdir(exist_ok=True)
    (a / "critique-consensus.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_ACTIVE_PLAN", raising=False)
    # A temp policy where a hard stage requires critique-consensus — opting the
    # gate IN, since the shipped policy leaves it OFF.
    policy = tmp_path / "critique-policy.yaml"
    policy.write_text(
        "stages:\n"
        "  push:\n"
        "    hard: true\n"
        "    require_plan: true\n"
        "    requires: [critique-consensus]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESS_STAGE_POLICY", str(policy))
    return tmp_path


class TestSchema:
    def test_schema_parses_and_declares_required_and_verdict_enum(self):
        spec = json.loads(_SCHEMA.read_text(encoding="utf-8"))
        for field in ("verdict", "reviewer", "role", "rationale", "ts"):
            assert field in spec["required"], "missing required field %s" % field
        assert spec["properties"]["verdict"]["enum"] == [
            "PASS", "PASS_WITH_RISK", "BLOCKED"]


class TestCritiqueConsensusGate:
    def test_missing_artifact_blocks_naming_kind_and_path(self, root):
        d = _mk_plan(root)
        reason = ac.check_stage("push", root)
        assert reason is not None
        assert "critique-consensus" in reason
        assert str(d / "artifacts") in reason

    def test_pass_passes(self, root):
        d = _mk_plan(root)
        _consensus(d, verdict="PASS")
        assert ac.check_stage("push", root) is None

    def test_blocked_verdict_blocks(self, root):
        d = _mk_plan(root)
        _consensus(d, verdict="BLOCKED")
        reason = ac.check_stage("push", root)
        assert reason is not None and "BLOCKED" in reason

    def test_pass_with_risk_is_not_enough(self, root):
        d = _mk_plan(root)
        _consensus(d, verdict="PASS_WITH_RISK")
        reason = ac.check_stage("push", root)
        assert reason is not None and "PASS_WITH_RISK" in reason

    def test_missing_required_field_blocks_naming_field(self, root):
        d = _mk_plan(root)
        _consensus(d, drop=["ts"])
        reason = ac.check_stage("push", root)
        assert reason is not None and "ts" in reason


class TestShippedPolicyDoesNotDefaultGateCritique:
    """critique-consensus enforcement ships OFF: the default policy lists it at
    NO stage, so a fresh spine-only install (where the producer hs-think:critique
    is an opt-in plugin) can ship/PR. Opting in is a tracked one-line stage-policy
    edit, exercised by the HARNESS_STAGE_POLICY unit tests above."""

    def test_no_stage_requires_critique_by_default(self, monkeypatch):
        monkeypatch.delenv("HARNESS_STAGE_POLICY", raising=False)
        policy = ac.load_policy()["stages"]
        for stage in policy:
            assert "critique-consensus" not in (policy[stage].get("requires") or []), (
                "stage %r must not require critique-consensus by default — it "
                "ships OFF; its producer hs-think:critique is an opt-in plugin, so "
                "a default install could never satisfy it" % stage)
