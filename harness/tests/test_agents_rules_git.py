"""test_agents_rules_git.py — P8 absorptions: agent uplift, entry-workflow rule, git merge-pr.

Three independent absorptions from an upstream kit, each landed the DRY way:

  1. the upstream full-stack developer agent was NOT duplicated (the harness developer
     agent already owns the scoped-slice TDD role, and agents are global) — instead its
     production-grade behavioral checklist was merged into the developer agent;
  2. the two agents whose explicit mandate is broad search (researcher, code-reviewer)
     gained read-only Explore delegation; the adversarial verifiers deliberately did not
     (their value is first-hand reading);
  3. the entry-workflow routing rule is ported and routed from CLAUDE.md, and the git
     skill documents a merge-pr subcommand distinct from branch-merge / create-pr.
"""
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _ROOT / "harness" / "plugins" / "hs" / "agents"
_GIT = _ROOT / "harness" / "plugins" / "hs" / "skills" / "git" / "SKILL.md"
_RULE = _ROOT / "harness" / "rules" / "primary-workflow.md"
_CLAUDE = _ROOT / "CLAUDE.md"

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _frontmatter(p):
    import yaml
    m = _FM.match(p.read_text(encoding="utf-8"))
    assert m, "%s has no frontmatter" % p
    return yaml.safe_load(m.group(1))


def test_all_agents_have_valid_frontmatter():
    for a in _AGENTS.glob("*.md"):
        fm = _frontmatter(a)
        assert fm.get("name"), "%s missing name" % a.name
        assert fm.get("description"), "%s missing description" % a.name


def test_developer_absorbed_production_checklist():
    body = (_AGENTS / "developer.md").read_text(encoding="utf-8").lower()
    # the merged checklist items (brand-free), not a duplicated agent
    for item in ("error handling", "input validation", "type safety"):
        assert item in body, "developer agent missing merged checklist item: %s" % item


def test_no_duplicate_fullstack_agent():
    # the upstream agent must not be re-created as a separate file (DRY)
    assert not (_AGENTS / "fullstack-developer.md").is_file()


def test_search_agents_gained_explore_delegation():
    for name in ("researcher", "code-reviewer"):
        tools = str(_frontmatter(_AGENTS / ("%s.md" % name)).get("tools", ""))
        assert "Task(Explore)" in tools, "%s did not gain Task(Explore)" % name


def test_adversarial_verifiers_excluded_from_explore():
    for name in ("red-teamer", "independent-revalidator"):
        tools = str(_frontmatter(_AGENTS / ("%s.md" % name)).get("tools", ""))
        assert "Task(Explore)" not in tools, "%s should keep first-hand reading" % name


def test_primary_workflow_rule_ported_and_routed():
    assert _RULE.is_file(), "harness/rules/primary-workflow.md missing"
    body = _RULE.read_text(encoding="utf-8")
    banned_path = ".claude/" + "skills/"  # assembled so this guard holds no banned literal
    assert "/ck:" not in body and banned_path not in body, "rule not de-branded"
    assert "primary-workflow" in _CLAUDE.read_text(encoding="utf-8"), "rule not routed in CLAUDE.md"


def test_git_skill_documents_merge_pr():
    body = _GIT.read_text(encoding="utf-8")
    assert "merge-pr" in body, "git skill does not document the merge-pr subcommand"
