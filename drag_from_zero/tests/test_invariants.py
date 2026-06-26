"""Harness invariants on a deterministic FakeLLM.

These do NOT test "the agent answers well" (that is semantic eval — a later,
non-deterministic slice). They pin the harness: delegation emits an event and
grows the tree, the view is a pure projection, budget halts when registered,
hooks can block, empty registries pass through, and agents can join mid-session.
"""
from dragzero import (
    Agent,
    Budget,
    EventType,
    FakeLLM,
    HookRegistry,
    Orchestrator,
    Roster,
    reduce,
    render_tree,
)


def _delegate(target, subtask, nxt=None):
    return {
        "plan": {"steps": [{"id": "s1", "description": f"delegate to {target}"}], "next": nxt},
        "decision": {"mode": "delegate", "target": target, "subtask": subtask},
    }


def _solo(nxt=None):
    return {
        "plan": {"steps": [{"id": "s1", "description": "do it"}], "next": nxt},
        "decision": {"mode": "solo"},
    }


def _two_agent(responder, **kw):
    llm = FakeLLM(responder)
    return Orchestrator(Roster([Agent("a1", "planner", llm), Agent("a2", "researcher", llm)]), **kw)


def _chain_orchestrator(**kw):
    """planner -> delegate researcher -> delegate writer -> solo. Three plan calls."""
    def responder(ctx):
        role = ctx["role"]
        if role == "planner":
            return _delegate("researcher", "find sources", nxt="hand to researcher")
        if role == "researcher":
            return _delegate("writer", "draft section", nxt="hand to writer")
        return _solo()
    llm = FakeLLM(responder)
    roster = Roster([
        Agent("a1", "planner", llm),
        Agent("a2", "researcher", llm),
        Agent("a3", "writer", llm),
    ])
    return Orchestrator(roster, **kw)


# 1 — delegation is visible: it emits an event and grows a child node.
def test_delegate_emits_event_and_grows_tree():
    orch = _two_agent(lambda ctx: _delegate("researcher", "find sources") if ctx["role"] == "planner" else _solo())
    log = orch.run("write report")

    assert EventType.DELEGATION_DECIDED in log.types()
    decision = log.of_type(EventType.DELEGATION_DECIDED)[0].payload["decision"]
    assert decision["mode"] == "delegate"
    assert EventType.SUBTASK_SPAWNED in log.types()

    root, _ = reduce(log.events())
    assert len(root.children) == 1
    assert root.children[0].description == "find sources"
    assert root.children[0].agent_id == "a2"


# 2 — solo emits no delegation and no child node.
def test_solo_does_not_grow_tree():
    orch = _two_agent(lambda ctx: _solo())
    log = orch.run("answer question")

    assert EventType.SUBTASK_SPAWNED not in log.types()
    root, _ = reduce(log.events())
    assert root.children == []
    assert root.status == "done"


# 3 — the live view is a pure projection of the event log.
def test_live_view_is_pure_projection():
    orch = _two_agent(lambda ctx: _delegate("researcher", "find sources") if ctx["role"] == "planner" else _solo())
    events = orch.run("write report").events()

    # deterministic: same events -> identical render
    assert render_tree(reduce(events)[0]) == render_tree(reduce(events)[0])

    # the view invents nothing: node count == created tasks (root + subtasks)
    _, nodes = reduce(events)
    created = 1 + sum(1 for e in events if e.type == EventType.SUBTASK_SPAWNED)
    assert len(nodes) == created

    # any prefix yields a subset of the final nodes — no node appears from nowhere
    for i in range(len(events)):
        _, partial = reduce(events[: i + 1])
        assert set(partial).issubset(set(nodes))


# 4 — budget halts the run once a limit is registered.
def test_budget_halts_when_registered():
    orch = _chain_orchestrator(budget=Budget(limit=2))
    log = orch.run("deep task")

    assert EventType.BUDGET_EXCEEDED in log.types()
    assert len(log.of_type(EventType.TASK_STARTED)) == 2  # halted before the 3rd plan
    assert orch.budget.used == 2
    assert EventType.TASK_COMPLETED not in log.types()  # nothing finished before the halt


# 5 — budget is disabled by default; the same chain runs to completion.
def test_budget_disabled_by_default():
    orch = _chain_orchestrator()
    log = orch.run("deep task")

    assert EventType.BUDGET_EXCEEDED not in log.types()
    assert len(log.of_type(EventType.PLAN_PRODUCED)) == 3
    root, _ = reduce(log.events())
    assert root.status == "done"


# 6 — a registered hook can block delegation.
def test_hook_can_block_delegation():
    hooks = HookRegistry()
    hooks.register("pre_delegate", lambda ctx: "policy: delegation disabled")
    orch = _two_agent(
        lambda ctx: _delegate("researcher", "find sources") if ctx["role"] == "planner" else _solo(),
        hooks=hooks,
    )
    log = orch.run("write report")

    assert EventType.HOOK_BLOCKED in log.types()
    assert EventType.SUBTASK_SPAWNED not in log.types()
    root, _ = reduce(log.events())
    assert root.children == []
    assert root.status == "done"  # solo fallback


# 7 — empty registries are pure pass-through.
def test_empty_registries_pass_through():
    orch = _two_agent(lambda ctx: _solo())
    log = orch.run("simple")

    assert EventType.HOOK_BLOCKED not in log.types()
    root, _ = reduce(log.events())
    assert root.status == "done"


# 8 — an agent injected mid-session emits agent_joined and becomes routable.
def test_agent_joined_mid_session():
    llm = FakeLLM(lambda ctx: _delegate("researcher", "find sources") if ctx["role"] == "planner" else _solo())
    orch = Orchestrator(Roster([Agent("a1", "planner", llm)]))  # researcher absent at start

    orch.join_agent(Agent("a2", "researcher", llm))
    assert EventType.AGENT_JOINED in orch.log.types()
    assert orch.roster.by_role_or_id("researcher") is not None

    log = orch.run("write report")
    spawned = log.of_type(EventType.SUBTASK_SPAWNED)
    assert len(spawned) == 1
    assert spawned[0].agent_id == "a2"  # routed to the live-injected agent
