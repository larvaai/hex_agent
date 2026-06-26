"""E2E: 'the event log is the only truth' as a projection round-trip invariant.

A real deterministic scenario (planner delegates to a coder who goes solo)
produces an event log; build_graph (the UI projection) and reduce (the read-model
fold) must agree on the tree it encodes — node set, every event accounted for,
fold determinism, prefix monotonicity, and edge/parent-link parity.
"""
from dragzero import Agent, EventType, FakeLLM, Orchestrator, Roster, reduce
from dragzero.server import build_graph, translate_event

# translate_event maps only the UI-relevant subset; the rest are deliberately
# dropped (the read-model carries them, the UI vocabulary does not).
KNOWN_DROPPED = {
    EventType.ROOT_TASK_CREATED,
    EventType.PLAN_PRODUCED,
    EventType.DELEGATION_DECIDED,
    EventType.TOOL_RESULT,
    EventType.AGENT_JOINED,
    EventType.AGENT_LEFT,
}


def _responder(ctx):
    """Planner delegates to a coder; the coder goes solo (terminal, no tools)."""
    if ctx["role"] == "planner":
        return {
            "plan": {"steps": [], "next": None},
            "decision": {"mode": "delegate", "target": "coder", "subtask": "write the module"},
        }
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _run_scenario():
    llm = FakeLLM(_responder)
    roster = Roster([Agent("planner", "planner", llm), Agent("coder", "coder", llm)])
    orch = Orchestrator(roster)
    orch.start("build a thing", agent=roster.by_role_or_id("planner"))
    orch.run_until_idle()
    return orch.log


def test_node_set_parity():
    """build_graph and reduce encode the exact same set of node ids."""
    log = _run_scenario()
    graph_ids = {n["id"] for n in build_graph(log)["nodes"]}
    fold_ids = set(reduce(log.events())[1].keys())
    assert graph_ids == fold_ids == {"t1", "t2"}


def test_every_event_is_translated_or_known_dropped():
    """No event is silently lost: each either translates to a frame or is in the dropped set."""
    log = _run_scenario()
    for ev in log.events():
        assert translate_event(ev) or ev.type in KNOWN_DROPPED, ev.type
    # the scenario actually exercises both sides of the partition (not vacuously true)
    types = set(log.types())
    assert types & KNOWN_DROPPED  # at least one dropped type present
    assert any(translate_event(ev) for ev in log.events())  # at least one translated


def test_fold_is_deterministic():
    """reduce is a pure fold: same events in -> structurally identical tree out."""
    evts = _run_scenario().events()
    root_a, nodes_a = reduce(evts)
    root_b, nodes_b = reduce(evts)
    assert nodes_a.keys() == nodes_b.keys()
    for nid in nodes_a:
        a, b = nodes_a[nid], nodes_b[nid]
        assert (a.id, a.parent_id, a.status, a.agent_id) == (b.id, b.parent_id, b.status, b.agent_id)
        assert [c.id for c in a.children] == [c.id for c in b.children]
    assert root_a.id == root_b.id


def test_prefix_node_set_is_monotone_subset():
    """Every prefix of the log folds to a node-set contained in the full node-set."""
    evts = _run_scenario().events()
    full = set(reduce(evts)[1].keys())
    prev_size = -1
    for k in range(len(evts) + 1):
        prefix_nodes = set(reduce(evts[:k])[1].keys())
        assert prefix_nodes <= full          # never invents a node the full log lacks
        assert len(prefix_nodes) >= prev_size  # node set only grows as events accrue
        prev_size = len(prefix_nodes)
    assert prev_size == len(full)  # the longest prefix == the whole log


def test_every_edge_is_a_real_parent_child_link():
    """Each build_graph edge mirrors a genuine parent_id link in the folded tree."""
    log = _run_scenario()
    graph = build_graph(log)
    _, nodes = reduce(log.events())
    assert graph["edges"]  # the scenario did spawn a child, so there is at least one edge
    for edge in graph["edges"]:
        assert edge["kind"] == "child"
        child = nodes[edge["target"]]
        assert child.parent_id == edge["source"]
        # and the parent really lists this child (link is bidirectional in the tree)
        assert edge["target"] in [c.id for c in nodes[edge["source"]].children]
    # parity the other way: every real parent link appears as exactly one edge
    real_links = {(n.parent_id, n.id) for n in nodes.values() if n.parent_id}
    edge_links = {(e["source"], e["target"]) for e in graph["edges"]}
    assert edge_links == real_links
