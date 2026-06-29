"""Gap 1 — disk is the only truth. The ledger survives a crash; resume = re-read + fold.

Pins: append-only JSONL round-trips through the EventType enum; a torn tail line (a crash
half-write) is dropped, not fatal; and an orchestration replayed from disk reduces to a tree
identical to the live one — state lives on disk, not in the process.
"""
from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools
from dragzero.events import Event, EventLog, EventType
from dragzero.ledger import Ledger, event_from_dict, event_to_dict
from dragzero.read_model import reduce


def _snap(log):
    """A structural fingerprint of the reduced tree — ids, status, parent, children order."""
    _, nodes = reduce(log.events())
    return {nid: (n.status, n.parent_id, [c.id for c in n.children]) for nid, n in nodes.items()}


def _responder(ctx):
    role, obs = ctx["role"], ctx["observations"]
    if role == "planner":
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": "coder", "subtask": "x"}}
    if role == "coder":
        if not obs:
            return {"action": {"type": "tool", "tool": "write_file", "args": {"path": "o.txt", "content": "hi"}}}
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def test_event_dict_round_trips_through_enum():
    e = Event(EventType.TOOL_CALLED, seq=4, task_id="t2", agent_id="coder", payload={"tool": "write_file"})
    back = event_from_dict(event_to_dict(e))
    assert back == e and back.type is EventType.TOOL_CALLED


def test_ledger_append_and_read(tmp_path):
    led = Ledger(tmp_path / "events.jsonl")
    led.append(Event(EventType.ROOT_TASK_CREATED, seq=0, task_id="t1", payload={"description": "go"}))
    led.append(Event(EventType.TASK_COMPLETED, seq=1, task_id="t1"))
    got = led.read()
    assert [e.type for e in got] == [EventType.ROOT_TASK_CREATED, EventType.TASK_COMPLETED]
    assert got[0].payload == {"description": "go"} and got[0].seq == 0


def test_torn_tail_line_is_dropped_not_fatal(tmp_path):
    p = tmp_path / "events.jsonl"
    led = Ledger(p)
    led.append(Event(EventType.ROOT_TASK_CREATED, seq=0, task_id="t1", payload={"description": "go"}))
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"seq": 1, "type": "task_comp')  # a crash mid-write — no newline, truncated JSON
    got = led.read()
    assert len(got) == 1 and got[0].type == EventType.ROOT_TASK_CREATED  # clean prefix survives


def test_eventlog_persists_every_append(tmp_path):
    p = tmp_path / "events.jsonl"
    log = EventLog(ledger=Ledger(p))
    log.append(Event(EventType.ROOT_TASK_CREATED, task_id="t1", payload={"description": "go"}))
    log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    assert p.exists() and len(p.read_text().splitlines()) == 2


def test_append_fails_closed_keeps_memory_and_disk_in_sync(tmp_path):
    # A non-serializable payload must NOT land in memory while the durable write fails — else disk
    # falls behind RAM and seqs go non-contiguous (the adversary's low-severity finding).
    import pytest
    p = tmp_path / "events.jsonl"
    log = EventLog(ledger=Ledger(p))
    log.append(Event(EventType.ROOT_TASK_CREATED, task_id="t1", payload={"d": "go"}))
    with pytest.raises(TypeError):
        log.append(Event(EventType.TOOL_CALLED, task_id="t1", payload={"x": object()}))  # not JSON
    log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    disk = Ledger(p).read()
    assert [e.seq for e in log.events()] == [e.seq for e in disk] == [0, 1]  # memory == disk, contiguous


def test_resume_from_disk_yields_identical_tree(tmp_path):
    p = tmp_path / "events.jsonl"
    sandbox = FsSandbox(str(tmp_path / "work"))
    orch = Orchestrator(
        Roster([Agent("planner", "planner", FakeLLM(_responder)), Agent("coder", "coder", FakeLLM(_responder))]),
        log=EventLog(ledger=Ledger(p)),
        tools=build_fs_tools(),
        sandbox=sandbox,
    )
    orch.run("build a thing", agent=orch.roster.by_role_or_id("planner"))
    live = _snap(orch.log)

    # process died; a fresh one rebuilds purely from the ledger on disk
    resumed = EventLog.replay(Ledger(p))
    assert _snap(resumed) == live
    assert len(resumed.events()) == len(orch.log.events())
    assert [e.seq for e in resumed.events()] == list(range(len(resumed.events())))  # contiguous seqs
