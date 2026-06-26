"""reduce() fold completeness: one EventType -> one exact TaskNode mutation.

Hand-built event lists only (never the Orchestrator). Each EventType is pinned to
the precise field it writes, plus empty-input, determinism, and prefix-subset.
"""
from dragzero import TaskNode, reduce
from dragzero.events import Event, EventType


def _root(task_id="root", desc="build it"):
    return Event(EventType.ROOT_TASK_CREATED, task_id=task_id, payload={"description": desc})


# --- empty input -------------------------------------------------------------

def test_empty_yields_none_and_empty_dict():
    root, nodes = reduce([])
    assert root is None
    assert nodes == {}


# --- ROOT_TASK_CREATED -------------------------------------------------------

def test_root_task_created_makes_root_with_no_parent():
    root, nodes = reduce([_root("r", "ship report")])
    assert isinstance(root, TaskNode)
    assert root.id == "r"
    assert root.description == "ship report"
    assert root.parent_id is None
    assert nodes == {"r": root}


# --- SUBTASK_SPAWNED ---------------------------------------------------------

def test_subtask_spawned_appends_child_to_parent():
    evts = [
        _root("r"),
        Event(EventType.SUBTASK_SPAWNED, task_id="c1", agent_id="a2",
              payload={"parent": "r", "subtask": "find sources"}),
    ]
    root, nodes = reduce(evts)
    assert len(root.children) == 1
    child = root.children[0]
    assert child is nodes["c1"]
    assert child.description == "find sources"
    assert child.parent_id == "r"
    assert child.agent_id == "a2"


# --- TASK_WAITING ------------------------------------------------------------

def test_task_waiting_sets_status_and_blocked_on():
    evts = [
        _root("r"),
        Event(EventType.TASK_WAITING, task_id="r", payload={"target": "researcher"}),
    ]
    root, _ = reduce(evts)
    assert root.status == "waiting"
    assert root.blocked_on == "researcher"


# --- TOOL_RESULT -------------------------------------------------------------

def test_tool_result_appends_tool_record():
    evts = [
        _root("r"),
        Event(EventType.TOOL_RESULT, task_id="r", payload={"tool": "grep", "ok": True}),
    ]
    root, _ = reduce(evts)
    assert root.tools == [{"tool": "grep", "ok": True}]


# --- TASK_STARTED ------------------------------------------------------------

def test_task_started_sets_running_and_agent():
    evts = [
        _root("r"),
        Event(EventType.TASK_STARTED, task_id="r", agent_id="a1"),
    ]
    root, _ = reduce(evts)
    assert root.status == "running"
    assert root.agent_id == "a1"


# --- PLAN_PRODUCED -----------------------------------------------------------

def test_plan_produced_sets_next_step():
    evts = [
        _root("r"),
        Event(EventType.PLAN_PRODUCED, task_id="r", payload={"plan": {"next": "hand to researcher"}}),
    ]
    root, _ = reduce(evts)
    assert root.next_step == "hand to researcher"


# --- DELEGATION_DECIDED ------------------------------------------------------

def test_delegation_decided_delegate_sets_delegated():
    evts = [
        _root("r"),
        Event(EventType.DELEGATION_DECIDED, task_id="r", payload={"decision": {"mode": "delegate"}}),
    ]
    root, _ = reduce(evts)
    assert root.status == "delegated"


# --- terminal statuses -------------------------------------------------------

def test_task_completed_sets_done():
    root, _ = reduce([_root("r"), Event(EventType.TASK_COMPLETED, task_id="r")])
    assert root.status == "done"


def test_task_failed_sets_failed():
    root, _ = reduce([_root("r"), Event(EventType.TASK_FAILED, task_id="r")])
    assert root.status == "failed"


def test_hook_blocked_sets_blocked():
    root, _ = reduce([_root("r"), Event(EventType.HOOK_BLOCKED, task_id="r")])
    assert root.status == "blocked"


def test_budget_exceeded_sets_halted():
    root, _ = reduce([_root("r"), Event(EventType.BUDGET_EXCEEDED, task_id="r")])
    assert root.status == "halted"


# --- determinism & prefix-subset --------------------------------------------

def _rich_log():
    return [
        _root("r", "top"),
        Event(EventType.TASK_STARTED, task_id="r", agent_id="a1"),
        Event(EventType.PLAN_PRODUCED, task_id="r", payload={"plan": {"next": "split"}}),
        Event(EventType.SUBTASK_SPAWNED, task_id="c1", agent_id="a2",
              payload={"parent": "r", "subtask": "leg one"}),
        Event(EventType.SUBTASK_SPAWNED, task_id="c2", agent_id="a3",
              payload={"parent": "r", "subtask": "leg two"}),
        Event(EventType.TASK_COMPLETED, task_id="r"),
    ]


def test_reduce_is_deterministic():
    evts = _rich_log()
    assert set(reduce(evts)[1]) == set(reduce(evts)[1])


def test_every_prefix_node_set_is_subset_of_full():
    evts = _rich_log()
    _, full = reduce(evts)
    full_ids = set(full)
    for i in range(len(evts)):
        _, partial = reduce(evts[: i + 1])
        assert set(partial).issubset(full_ids)
