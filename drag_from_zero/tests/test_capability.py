"""Gap 3 — capability token + delegation gate (ADR-1..4).

Pins: attenuation only NARROWS (a widen raises); the tool Gate reads the token not the agent's
words; depth and spawn_quota are hard stops surfaced as events; and the default (no capability)
is byte-identical passthrough. The new EventTypes round-trip through the ledger (else resume
would raise on EventType(unknown)).
"""
import pytest

from dragzero import Agent, FakeLLM, Orchestrator, Roster
from dragzero.adapters.tools_fs import FsSandbox, build_fs_tools
from dragzero.capability import Capability, CapabilityError, permissive
from dragzero.events import Event, EventLog, EventType
from dragzero.ledger import Ledger, event_from_dict, event_to_dict


# ── attenuation: subset only, never widen ─────────────────────────────────────
def test_attenuate_narrows_tools_and_decrements_depth():
    parent = Capability(tools=frozenset({"a", "b", "c"}), depth=3, spawn_quota=4)
    child = parent.attenuate(tools={"a", "b"})
    assert child.tools == {"a", "b"} and child.tools < parent.tools
    assert child.depth == 2  # one level down


def test_attenuate_decrements_depth_even_when_equal_requested():
    parent = Capability(depth=3)
    # requesting the parent's own depth must STILL decrement — no stalling the per-level budget
    assert parent.attenuate(depth=3).depth == 2


@pytest.mark.parametrize("kwargs", [
    {"tools": {"a", "z"}},          # z not in parent
    {"depth": 99},                  # deeper than parent
    {"spawn_quota": 99},            # bigger quota than parent
    {"can_delegate": True},         # granting what the parent lacks
])
def test_attenuate_refuses_to_widen(kwargs):
    parent = Capability(tools=frozenset({"a"}), can_delegate=False, depth=2, spawn_quota=2)
    with pytest.raises(CapabilityError):
        parent.attenuate(**kwargs)


# ── the Gate reads the token, not the agent's words ───────────────────────────
def _coder_writes(ctx):
    if ctx["role"] == "planner":
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": "coder", "subtask": "x"}}
    if ctx["role"] == "coder":
        if not ctx["observations"]:
            return {"action": {"type": "tool", "tool": "write_file", "args": {"path": "o.txt", "content": "hi"}}}
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def test_tool_outside_capability_is_denied(tmp_path):
    sandbox = FsSandbox(str(tmp_path))
    # capability allows read_file only; the coder asks for write_file
    cap = permissive(tools=("read_file",))
    orch = Orchestrator(
        Roster([Agent("planner", "planner", FakeLLM(_coder_writes)), Agent("coder", "coder", FakeLLM(_coder_writes))]),
        tools=build_fs_tools(), sandbox=sandbox, capability=cap,
    )
    orch.run("build", agent=orch.roster.by_role_or_id("planner"))
    assert orch.log.of_type(EventType.TOOL_DENIED), "write_file should have been denied"
    assert not (tmp_path / "o.txt").exists()  # the side effect never happened


# ── budgets are hard stops, surfaced as events ────────────────────────────────
def _always_delegate(ctx):
    # every agent tries to delegate one level deeper
    nxt = {"planner": "a", "a": "b", "b": "c", "c": "d"}.get(ctx["role"], None)
    if nxt:
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": nxt, "subtask": "go"}}
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def test_quota_zero_forces_solo_fallback(tmp_path):
    cap = Capability(tools=frozenset(), can_delegate=True, depth=8, spawn_quota=0)  # may not spawn at all
    orch = Orchestrator(
        Roster([Agent("planner", "planner", FakeLLM(_always_delegate)), Agent("a", "a", FakeLLM(_always_delegate))]),
        capability=cap,
    )
    orch.run("go", agent=orch.roster.by_role_or_id("planner"))
    assert orch.log.of_type(EventType.CAPABILITY_EXHAUSTED)
    assert not orch.log.of_type(EventType.SUBTASK_SPAWNED)  # nothing spawned


def test_depth_bounds_the_delegation_chain(tmp_path):
    roster = Roster([Agent(r, r, FakeLLM(_always_delegate)) for r in ("planner", "a", "b", "c", "d")])
    cap = Capability(tools=frozenset(), can_delegate=True, depth=2, spawn_quota=8)  # 2 levels of delegation
    orch = Orchestrator(roster, capability=cap)
    orch.run("go", agent=roster.by_role_or_id("planner"))
    spawned = len(orch.log.of_type(EventType.SUBTASK_SPAWNED))
    assert spawned == 2  # planner->a (depth 2->1), a->b (1->0), b denied
    assert orch.log.of_type(EventType.CAPABILITY_EXHAUSTED)


# ── default is byte-identical passthrough ─────────────────────────────────────
def test_no_capability_is_passthrough(tmp_path):
    sandbox = FsSandbox(str(tmp_path))
    orch = Orchestrator(
        Roster([Agent("planner", "planner", FakeLLM(_coder_writes)), Agent("coder", "coder", FakeLLM(_coder_writes))]),
        tools=build_fs_tools(), sandbox=sandbox,  # capability=None
    )
    orch.run("build", agent=orch.roster.by_role_or_id("planner"))
    assert not orch.log.of_type(EventType.TOOL_DENIED)
    assert (tmp_path / "o.txt").read_text() == "hi"  # tool ran normally


# ── new EventTypes survive the disk round-trip ────────────────────────────────
def test_new_eventtypes_round_trip(tmp_path):
    led = Ledger(tmp_path / "e.jsonl")
    for et in (EventType.TOOL_DENIED, EventType.CAPABILITY_EXHAUSTED):
        e = Event(et, seq=0, task_id="t1", payload={"reason": "x"})
        assert event_from_dict(event_to_dict(e)).type is et
        led.append(e)
    assert len(led.read()) == 2  # EventType(value) reconstructs without raising
