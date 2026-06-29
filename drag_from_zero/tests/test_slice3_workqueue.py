"""Slice 3a — pausable work-queue + true mid-run agent injection.

The orchestrator now pauses when a delegation targets a role nobody fills. An
agent injected *while the run is paused* picks up the parked subtask and the run
resumes. All of this stays deterministic on FakeLLM.
"""
from dragzero import Agent, EventType, FakeLLM, Orchestrator, Roster, reduce


def _delegate(target, subtask, nxt=None):
    return {
        "plan": {"steps": [{"id": "s1", "description": f"delegate to {target}"}], "next": nxt},
        "decision": {"mode": "delegate", "target": target, "subtask": subtask},
    }


def _solo(nxt=None):
    return {"plan": {"steps": [{"id": "s1", "description": "do it"}], "next": nxt}, "decision": {"mode": "solo"}}


def _planner_delegates_to(role, subtask):
    return FakeLLM(lambda ctx: _delegate(role, subtask) if ctx["role"] == "planner" else _solo())


# the run parks (does not crash, does not mis-route) when the target is missing
def test_run_pauses_when_target_agent_is_missing():
    llm = _planner_delegates_to("reviewer", "review the diff")
    orch = Orchestrator(Roster([Agent("a1", "planner", llm)]))
    orch.start("ship the patch")
    orch.run_until_idle()

    assert EventType.TASK_WAITING in orch.log.types()
    assert orch.waiting_count() == 1
    assert EventType.TASK_COMPLETED not in orch.log.types()  # root cannot finish yet
    root, _ = reduce(orch.log.events())
    assert root.status == "delegated"
    assert root.children[0].status == "waiting"
    assert root.children[0].blocked_on == "reviewer"


# inject the missing role mid-run -> it answers the parked task, run completes
def test_injecting_agent_mid_run_resumes_and_answers():
    llm = _planner_delegates_to("reviewer", "review the diff")
    orch = Orchestrator(Roster([Agent("a1", "planner", llm)]))
    orch.start("ship the patch")
    orch.run_until_idle()  # parks on missing reviewer

    orch.join_agent(Agent("a2", "reviewer", llm))
    assert EventType.AGENT_JOINED in orch.log.types()
    assert orch.waiting_count() == 0
    orch.run_until_idle()  # resumes

    root, _ = reduce(orch.log.events())
    assert root.status == "done"
    child = root.children[0]
    assert child.status == "done"
    assert child.agent_id == "a2"  # answered by the live-injected agent


# injecting the wrong role leaves the task parked; the right role unblocks it
def test_injecting_wrong_role_keeps_task_parked():
    llm = _planner_delegates_to("reviewer", "review the diff")
    orch = Orchestrator(Roster([Agent("a1", "planner", llm)]))
    orch.start("ship")
    orch.run_until_idle()

    orch.join_agent(Agent("a9", "tester", llm))  # wrong role
    assert orch.waiting_count() == 1
    assert EventType.TASK_COMPLETED not in orch.log.types()

    orch.join_agent(Agent("a2", "reviewer", llm))  # right role
    assert orch.waiting_count() == 0
    orch.run_until_idle()
    root, _ = reduce(orch.log.events())
    assert root.status == "done"


# the convenience resume flag runs to completion in one call
def test_join_agent_resume_flag_runs_to_completion():
    llm = _planner_delegates_to("reviewer", "review the diff")
    orch = Orchestrator(Roster([Agent("a1", "planner", llm)]))
    orch.start("ship")
    orch.run_until_idle()

    orch.join_agent(Agent("a2", "reviewer", llm), resume=True)
    root, _ = reduce(orch.log.events())
    assert root.status == "done"


# the event trace tells the pause -> join -> resume story in order
def test_event_order_shows_pause_join_resume():
    llm = _planner_delegates_to("reviewer", "review the diff")
    orch = Orchestrator(Roster([Agent("a1", "planner", llm)]))
    orch.start("ship")
    orch.run_until_idle()
    orch.join_agent(Agent("a2", "reviewer", llm))
    orch.run_until_idle()

    seq = [e.type for e in orch.log.events()]
    i_wait = seq.index(EventType.TASK_WAITING)
    i_join = seq.index(EventType.AGENT_JOINED)
    i_first_done = min(i for i, e in enumerate(seq) if e == EventType.TASK_COMPLETED)
    assert i_wait < i_join < i_first_done  # nothing finished before the injection


# with the target present, run() behaves exactly like Slice 1 (no pausing)
def test_run_compat_when_no_pausing():
    llm = _planner_delegates_to("researcher", "find sources")
    orch = Orchestrator(Roster([Agent("a1", "planner", llm), Agent("a2", "researcher", llm)]))
    log = orch.run("write report")

    assert EventType.TASK_WAITING not in log.types()
    root, _ = reduce(log.events())
    assert root.status == "done"
    assert root.children[0].agent_id == "a2"
