"""test_agent_explore_access.py — advisory agents can fan out read-only Explore.

Advisory/synthesis agents that hold NO subagent-spawn tool (no plain `Task`) get the
SCOPED, read-only `Task(Explore)` so they can fan out searches without gaining the
ability to spawn mutating subagents. Agents that already have plain `Task` already
reach Explore and are left unchanged.

Two classes are deliberately EXCLUDED:
- git-manager — its role is staging/commit from an existing diff, so a codebase-search
  fan-out is dead surface (YAGNI).
- the adversarial verifiers red-teamer / independent-revalidator — they must re-derive
  from PRIMARY evidence first-hand, never delegating reading to a search agent
  (enforced separately in test_agents_rules_git.py; mirrored here so the two lists
  cannot drift).
"""
import re
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "plugins" / "hs" / "agents"

# advisory/synthesis agents with no plain Task that should expose the scoped Explore
_NEED_EXPLORE = [
    "critique-consolidator", "docs-manager", "journal-writer", "project-manager",
]
# agents deliberately NOT granted Explore (narrow role / first-hand reading)
_EXCLUDED = ["git-manager", "red-teamer", "independent-revalidator"]


def _tools_line(name):
    body = (_AGENTS / (name + ".md")).read_text(encoding="utf-8")
    m = re.search(r"(?im)^tools:.*$", body)
    return m.group(0) if m else ""


def test_advisory_agents_expose_scoped_explore():
    for name in _NEED_EXPLORE:
        line = _tools_line(name)
        assert "Task(Explore)" in line, "%s missing Task(Explore): %s" % (name, line)


def test_scoped_not_plain_task_for_advisory():
    # the grant must stay SCOPED — an advisory agent must not gain plain `Task`
    for name in _NEED_EXPLORE:
        line = _tools_line(name)
        # strip the scoped form, then no bare ", Task" / "Task," token may remain
        stripped = line.replace("Task(Explore)", "")
        assert not re.search(r"(?<![A-Za-z])Task(?![A-Za-z(])", stripped), \
            "%s gained plain Task (must stay Explore-only): %s" % (name, line)


def test_excluded_agents_have_no_explore():
    for name in _EXCLUDED:
        assert "Task(Explore)" not in _tools_line(name), \
            "%s must not gain Task(Explore)" % name
