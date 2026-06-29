"""test_cook_gate_mapping.py — the cook/plan gate model is machinery, not prose.

An upstream kit expressed its execution gates as prose XML markers in one skill. The
harness instead enforces the same intent through real machinery split across plan and
cook. This guard proves the merge held:

  1. cook and plan still pass the structure checker (no regression from the merge),
  2. every gate mechanism the model relies on is a real file on disk (no prose-only
     block the runtime cannot enforce),
  3. cook keeps its HARNESS_AUTONOMY pause cadence (the merge added no always-block that
     would override autonomy), and
  4. the two genuine enrichments landed: plan pins the concrete requirements set before
     decomposing, and cook's end-of-phase check walks callers of changed functions.
"""
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SKILLS = _ROOT / "harness" / "plugins" / "hs" / "skills"


def _structure_hard_zero(skill):
    out = subprocess.run(
        [sys.executable, str(_ROOT / "harness" / "scripts" / "check_skill_structure.py"),
         str(_SKILLS / skill)],
        capture_output=True, text=True,
    )
    return '"hard": 0' in out.stdout, out.stdout


def test_cook_and_plan_structure_clean():
    for skill in ("cook", "plan"):
        ok, detail = _structure_hard_zero(skill)
        assert ok, "%s structure regressed:\n%s" % (skill, detail)


def test_every_gate_mechanism_is_a_real_file():
    # each HS mechanism the gate model names must exist — no prose-only gate
    mechanisms = [
        "harness/hooks/gate_stage.py",            # the presence gate at hard stages
        "harness/scripts/artifact_check.py",      # verification.json schema helper
        "harness/scripts/autonomy_policy.py",     # HARNESS_AUTONOMY pause resolver
        "harness/scripts/plan_approval.py",       # human plan-approval record
        "harness/data/stage-policy.yaml",         # require_plan policy
        "harness/plugins/hs/skills/cook/references/verify-before-done.md",
    ]
    missing = [m for m in mechanisms if not (_ROOT / m).is_file()]
    assert not missing, "gate mechanisms missing (would make the gate prose-only): %s" % missing


def test_cook_keeps_autonomy_cadence():
    body = (_SKILLS / "cook" / "SKILL.md").read_text(encoding="utf-8")
    assert "HARNESS_AUTONOMY" in body
    for level in ("ask_all", "god"):
        assert level in body, "autonomy level %s dropped from cook" % level


def test_plan_pins_concrete_requirements():
    # marker absorbed: plan must enumerate the requirements to pin before decomposing
    body = (_SKILLS / "plan" / "SKILL.md").read_text(encoding="utf-8").lower()
    for need in ("expected output", "acceptance", "scope boundary", "constraint", "touchpoint"):
        assert need in body, "plan does not pin requirement: %s" % need


def test_cook_verify_walks_callers():
    # marker absorbed: side-effect check must reach callers of changed functions
    drawer = (_SKILLS / "cook" / "references" / "verify-before-done.md").read_text(encoding="utf-8").lower()
    assert "caller" in drawer, "verify-before-done does not walk callers of changed functions"
