"""Slice D1 — input triage + task-box materialization.

The entry worker reads raw input and classifies it: a plain question yields an
answer; a task materializes a {goal, done_when} box and STOPS (no execution).
The worker PROPOSES; CODE adjudicates the done_when (forgery → reject). Additive:
start()/run()/_solve_gated are untouched, so the existing suite stays green.

Deterministic on FakeLLM — the triage payload is scripted, never inferred.
"""
from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.contracts import TriageResult
from dragzero.events import EventType
from dragzero.read_model import TaskBox, reduce_inbox

FE = lambda art: {"check": "file_exists", "artifact": art}  # noqa: E731


def _triage(payload):
    """A FakeLLM that answers the triage request with a fixed payload."""
    return FakeLLM(lambda ctx: payload)


def _orch(payload, agents=None):
    """Orchestrator over a one-worker roster scripted to return `payload` on triage."""
    roster = Roster(agents if agents is not None else [Agent("w", "worker", _triage(payload))])
    return Orchestrator(roster)


# events that prove the slice EXECUTED a task — must never appear on a materialize-only path
_EXECUTION_EVENTS = (EventType.LEAF_VERIFIED, EventType.SUBTASK_SPAWNED,
                     EventType.DECOMPOSITION_PROPOSED, EventType.TASK_STARTED)


# ── Phase 1: the triage seam (Agent.triage on FakeLLM) ────────────────────────
def test_triage_answer():
    agent = Agent("w", "worker", _triage({"triage": {"kind": "answer", "text": "42"}}))
    r = agent.triage("what is 6*7?")
    assert isinstance(r, TriageResult) and r.kind == "answer" and r.text == "42"


def test_triage_task():
    agent = Agent("w", "worker", _triage(
        {"triage": {"kind": "task", "goal": "fix login", "done_when": [FE("login.py")]}}))
    r = agent.triage("the login button is broken, fix it")
    assert r.kind == "task" and r.goal == "fix login" and r.done_when == [FE("login.py")]


def test_triage_tolerant_default():  # empty/garbage reply must not crash — fall back to answer
    agent = Agent("w", "worker", _triage({}))
    r = agent.triage("hello")
    assert r.kind == "answer"


def test_triage_missing_keys():  # task with no goal/done_when → safe defaults, no KeyError
    agent = Agent("w", "worker", _triage({"triage": {"kind": "task"}}))
    r = agent.triage("do the thing")
    assert r.kind == "task" and r.goal is None and r.done_when == []


# ── Phase 2: Orchestrator.submit — classify → emit → STOP (the heart) ──────────
def test_submit_answer_path():
    orch = _orch({"triage": {"kind": "answer", "text": "Paris"}})
    r = orch.submit("what is the capital of France?")
    types = orch.log.types()
    assert r.kind == "answer"
    ic = orch.log.of_type(EventType.INPUT_CLASSIFIED)
    assert len(ic) == 1 and ic[0].payload["kind"] == "answer"
    assert orch.log.of_type(EventType.ANSWER_PRODUCED)[0].payload["text"] == "Paris"
    assert EventType.TASK_BOX_CREATED not in types


def test_submit_task_materializes_box():
    orch = _orch({"triage": {"kind": "task", "goal": "fix login", "done_when": [FE("login.py")]}})
    r = orch.submit("login is broken")
    assert r.kind == "task"
    assert orch.log.of_type(EventType.INPUT_CLASSIFIED)[0].payload["kind"] == "task"
    box = orch.log.of_type(EventType.TASK_BOX_CREATED)
    assert len(box) == 1
    assert box[0].payload["goal"] == "fix login" and box[0].payload["done_when"] == [FE("login.py")]
    assert not orch.log.of_type(EventType.TASK_BOX_REJECTED)


def test_submit_task_does_not_execute():  # LAW 3 — materialize STOPS, never runs the task
    orch = _orch({"triage": {"kind": "task", "goal": "ship it", "done_when": [FE("out.txt")]}})
    orch.submit("build the thing")
    types = orch.log.types()
    assert EventType.TASK_BOX_CREATED in types
    for ev in _EXECUTION_EVENTS:
        assert ev not in types, f"materialize path must not execute: saw {ev}"


def test_submit_forged_done_when_rejected():  # LAW 1 — a verdict-shaped key is forgery → reject
    forged = [{"check": "file_exists", "artifact": "x.txt", "passed": True}]
    orch = _orch({"triage": {"kind": "task", "goal": "cheat", "done_when": forged}})
    orch.submit("pretend this passed")
    rej = orch.log.of_type(EventType.TASK_BOX_REJECTED)
    assert len(rej) == 1 and rej[0].payload["goal"] == "cheat" and "verdict" in rej[0].payload["reason"].lower()
    assert not orch.log.of_type(EventType.TASK_BOX_CREATED)


def test_submit_empty_done_when_allowed():  # done_when=[] → unverified box, NOT a rejection
    orch = _orch({"triage": {"kind": "task", "goal": "vague goal", "done_when": []}})
    orch.submit("do something, criteria TBD")
    assert orch.log.of_type(EventType.TASK_BOX_CREATED)[0].payload["done_when"] == []
    assert not orch.log.of_type(EventType.TASK_BOX_REJECTED)


def test_submit_no_agent():  # empty roster → TASK_FAILED, never a crash
    orch = _orch({"triage": {"kind": "answer", "text": "x"}}, agents=[])
    r = orch.submit("anyone there?")
    fails = orch.log.of_type(EventType.TASK_FAILED)
    assert len(fails) == 1 and "no agent" in fails[0].payload["error"]
    assert r.kind == "answer" and not orch.log.of_type(EventType.TASK_BOX_CREATED)


# ── Phase 3: the inbox projection (reduce_inbox folds the 4 events) ────────────
def test_inbox_projection_answers():
    orch = _orch({"triage": {"kind": "answer", "text": "Paris"}})
    orch.submit("q1")
    orch.submit("q2")
    view = reduce_inbox(orch.log.events())
    assert view["answers"] == ["Paris", "Paris"] and view["task_boxes"] == []


def test_inbox_projection_task_box():
    orch = _orch({"triage": {"kind": "task", "goal": "fix login", "done_when": [FE("login.py")]}})
    orch.submit("login broken")
    view = reduce_inbox(orch.log.events())
    assert view["answers"] == []
    assert view["task_boxes"] == [TaskBox("fix login", [FE("login.py")], status="materialized")]


def test_inbox_empty_done_when_unverified():
    orch = _orch({"triage": {"kind": "task", "goal": "vague", "done_when": []}})
    orch.submit("criteria TBD")
    box = reduce_inbox(orch.log.events())["task_boxes"][0]
    assert box.status == "unverified" and box.done_when == []


def test_inbox_rejected():
    forged = [{"check": "file_exists", "artifact": "x.txt", "passed": True}]
    orch = _orch({"triage": {"kind": "task", "goal": "cheat", "done_when": forged}})
    orch.submit("forge a pass")
    box = reduce_inbox(orch.log.events())["task_boxes"][0]
    assert box.status == "rejected" and box.goal == "cheat" and box.reason


def test_inbox_pure_fold():  # same events folded twice → identical view (no hidden state)
    orch = _orch({"triage": {"kind": "task", "goal": "g", "done_when": [FE("a.txt")]}})
    orch.submit("t1")
    orch.submit("t2")
    events = orch.log.events()
    assert reduce_inbox(events) == reduce_inbox(events)
