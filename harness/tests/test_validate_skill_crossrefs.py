"""Tests for harness skill cross-reference and workflow-chain validator.

Covers:
- Valid refs resolve without error
- Broken refs (/hs-x:ghost) are detected
- Orphan skills (no inbound / outbound edges) are detected
- Present chain edges pass; missing ones are reported
- Code-fence refs are excluded
- Self-references are ignored
- Both /hs:<skill> and /hs-<group>:<skill> namespaces match
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts dir is importable
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import validate_skill_crossrefs as vsc  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_skill(root: Path, plugin: str, skill_dir: str, name: str, body: str) -> Path:
    """Create a fake plugin/skill/SKILL.md under root."""
    d = root / plugin / "skills" / skill_dir
    d.mkdir(parents=True, exist_ok=True)
    content = (
        f"---\nname: {name}\ndescription: fake\nuser-invocable: true\n---\n\n"
        + body
    )
    (d / "SKILL.md").write_text(content, encoding="utf-8")
    return d


def _build_tree(tmp_path: Path) -> Path:
    """
    Build a minimal multi-plugin skills tree:

      hs/skills/plan       name: hs:plan       refs -> hs:cook
      hs/skills/cook       name: hs:cook        refs -> hs-think:brainstorm, hs:code-review
      hs-think/skills/brainstorm  name: hs-think:brainstorm  (no outbound refs)
      hs/skills/orphan     name: hs:orphan      (no refs in or out)
      hs/skills/broken     name: hs:broken      refs -> /hs-x:ghost (nonexistent)
    """
    _make_skill(tmp_path, "hs", "plan", "hs:plan",
                "After deciding, use /hs:cook to implement.\n")
    _make_skill(tmp_path, "hs", "cook", "hs:cook",
                "Call /hs-think:brainstorm for ideas, then /hs:code-review.\n")
    _make_skill(tmp_path, "hs-think", "brainstorm", "hs-think:brainstorm",
                "Pure ideation, no further refs.\n")
    _make_skill(tmp_path, "hs", "orphan", "hs:orphan",
                "This skill is standalone.\n")
    _make_skill(tmp_path, "hs", "broken", "hs:broken",
                "See /hs-x:ghost for help.\n")
    return tmp_path


# ── tests ────────────────────────────────────────────────────────────────────

class TestScanAllSkills:
    def test_collects_all_plugins(self, tmp_path):
        _build_tree(tmp_path)
        skills = vsc.scan_all_skills(tmp_path)
        names = {d["name"] for d in skills.values()}
        assert "hs:plan" in names
        assert "hs:cook" in names
        assert "hs-think:brainstorm" in names

    def test_spine_ref_detected(self, tmp_path):
        """plan body contains /hs:cook — must appear in body_refs."""
        _build_tree(tmp_path)
        skills = vsc.scan_all_skills(tmp_path)
        plan_entry = next(d for d in skills.values() if d["name"] == "hs:plan")
        assert "hs:cook" in plan_entry["body_refs"]

    def test_namespaced_ref_detected(self, tmp_path):
        """/hs-think:brainstorm in cook body must be captured."""
        _build_tree(tmp_path)
        skills = vsc.scan_all_skills(tmp_path)
        cook_entry = next(d for d in skills.values() if d["name"] == "hs:cook")
        assert "hs-think:brainstorm" in cook_entry["body_refs"]

    def test_code_fence_refs_excluded(self, tmp_path):
        """Refs inside ``` fences must not appear in body_refs."""
        _make_skill(tmp_path, "hs", "fenced", "hs:fenced",
                    "Normal text.\n\n```\n/hs:cook should not match\n```\n")
        skills = vsc.scan_all_skills(tmp_path)
        fenced = next(d for d in skills.values() if d["name"] == "hs:fenced")
        assert "hs:cook" not in fenced["body_refs"]

    def test_self_reference_ignored(self, tmp_path):
        """A skill that references itself must not produce a self-edge."""
        _make_skill(tmp_path, "hs", "self-ref", "hs:self-ref",
                    "Calls /hs:self-ref recursively.\n")
        skills = vsc.scan_all_skills(tmp_path)
        sr = next(d for d in skills.values() if d["name"] == "hs:self-ref")
        assert "hs:self-ref" not in sr["body_refs"]

    def test_skip_dirs_respected(self, tmp_path):
        """Skills inside SKIP_DIRS are not included."""
        skip_dir = tmp_path / "hs" / "skills" / "_shared"
        skip_dir.mkdir(parents=True, exist_ok=True)
        (skip_dir / "SKILL.md").write_text(
            "---\nname: hs:should-skip\ndescription: x\nuser-invocable: true\n---\nHello.\n",
            encoding="utf-8",
        )
        skills = vsc.scan_all_skills(tmp_path)
        names = {d["name"] for d in skills.values()}
        assert "hs:should-skip" not in names


class TestBuildReferenceGraph:
    def test_valid_edge_present(self, tmp_path):
        """plan -> cook edge must appear in graph edges."""
        _build_tree(tmp_path)
        skills = vsc.scan_all_skills(tmp_path)
        graph = vsc.build_reference_graph(skills)
        # At least one skill points to hs:cook
        all_targets = {t for targets in graph["edges"].values() for t in targets}
        assert "hs:cook" in all_targets

    def test_broken_ref_detected(self, tmp_path):
        """/hs-x:ghost is not a known skill — must appear in broken list."""
        _build_tree(tmp_path)
        skills = vsc.scan_all_skills(tmp_path)
        graph = vsc.build_reference_graph(skills)
        broken_refs = [ref for _, ref in graph["broken"]]
        assert "hs-x:ghost" in broken_refs

    def test_orphan_detected(self, tmp_path):
        """hs:orphan has no inbound or outbound edges — must be in orphans."""
        _build_tree(tmp_path)
        skills = vsc.scan_all_skills(tmp_path)
        graph = vsc.build_reference_graph(skills)
        # orphan skill name is in orphans list
        assert "hs:orphan" in graph["orphans"]

    def test_no_false_broken_for_valid_ref(self, tmp_path):
        """hs:cook is a real skill — must not appear as broken ref."""
        _build_tree(tmp_path)
        skills = vsc.scan_all_skills(tmp_path)
        graph = vsc.build_reference_graph(skills)
        broken_refs = [ref for _, ref in graph["broken"]]
        assert "hs:cook" not in broken_refs


class TestCheckExpectedWorkflows:
    def test_missing_chain_edge_reported(self, tmp_path):
        """A chain pair not connected by any edge must be reported as missing."""
        # Only build plan and cook — no code-review or ship
        _make_skill(tmp_path, "hs", "plan", "hs:plan",
                    "Use /hs:cook next.\n")
        _make_skill(tmp_path, "hs", "cook", "hs:cook",
                    "Implementation only.\n")  # no ref to code-review
        skills = vsc.scan_all_skills(tmp_path)
        graph = vsc.build_reference_graph(skills)
        missing = vsc.check_expected_workflows(graph, skills)
        chain_pairs = [(m["from"], m["to"]) for m in missing]
        # development chain: cook -> code-review is missing
        assert ("hs:cook", "hs:code-review") in chain_pairs

    def test_present_chain_edge_not_reported(self, tmp_path):
        """plan -> cook edge is present — must NOT appear in missing."""
        _make_skill(tmp_path, "hs", "plan", "hs:plan",
                    "Use /hs:cook to implement.\n")
        _make_skill(tmp_path, "hs", "cook", "hs:cook",
                    "Implementation done.\n")
        skills = vsc.scan_all_skills(tmp_path)
        graph = vsc.build_reference_graph(skills)
        missing = vsc.check_expected_workflows(graph, skills)
        chain_pairs = [(m["from"], m["to"]) for m in missing]
        assert ("hs:plan", "hs:cook") not in chain_pairs

    def test_investigation_chain_missing_brainstorm(self, tmp_path):
        """scout + debug without brainstorm must flag scout:debug->debug:brainstorm gap."""
        _make_skill(tmp_path, "hs", "scout", "hs:scout",
                    "Explore with /hs:debug.\n")
        _make_skill(tmp_path, "hs", "debug", "hs:debug",
                    "Diagnose issue.\n")  # no ref to brainstorm
        skills = vsc.scan_all_skills(tmp_path)
        graph = vsc.build_reference_graph(skills)
        missing = vsc.check_expected_workflows(graph, skills)
        chain_pairs = [(m["from"], m["to"]) for m in missing]
        assert ("hs:debug", "hs-think:brainstorm") in chain_pairs
