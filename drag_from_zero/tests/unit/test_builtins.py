"""Built-in hook + routing-rule catalogs — block reasons, keyword/always factories."""
import pytest

from dragzero import Task
from dragzero.builtins import BUILTIN_HOOKS, BUILTIN_RULES


# --- hooks: fn(ctx) -> Optional[block_reason] ---
def test_deny_delegation_block_reason():
    assert BUILTIN_HOOKS["deny_delegation"](object()) == "policy: delegation disabled"


def test_deny_all_block_reason():
    assert BUILTIN_HOOKS["deny_all"](object()) == "policy: blocked by hook"


# --- rules: factory(config) -> rule(task) -> Optional[role_or_id] ---
def test_by_keyword_matches_case_insensitive():
    rule = BUILTIN_RULES["by_keyword"]({"keyword": "deploy", "role": "devops"})
    task = Task(id="t", description="please DEPLOY now")
    assert rule(task) == "devops"


def test_by_keyword_no_match_returns_none():
    rule = BUILTIN_RULES["by_keyword"]({"keyword": "deploy", "role": "devops"})
    task = Task(id="t", description="just write some docs")
    assert rule(task) is None


def test_by_keyword_missing_role_returns_none():
    rule = BUILTIN_RULES["by_keyword"]({"keyword": "deploy"})
    task = Task(id="t", description="please DEPLOY now")
    assert rule(task) is None


def test_always_returns_role_for_any_task():
    rule = BUILTIN_RULES["always"]({"role": "ops"})
    assert rule(Task(id="t", description="anything at all")) == "ops"
    assert rule(Task(id="t2", description="")) == "ops"
