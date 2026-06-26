"""Slice 5 — topology loader (Đồ thị 1 as JSON, the API boundary for the UI).

Round-trip fidelity, structural validation, and `build_runtime` turning JSON into
a runnable Orchestrator whose tools/hooks/routers come from the topology. The
runtime is the same one every earlier slice tests — delegation, hooks, routing.
"""
import json

import pytest

from dragzero import EventType, FakeLLM, reduce
from dragzero.adapters.tools_fs import FsSandbox, default_tool_catalog
from dragzero.topology import Topology, TopologyError, dump_json, load_json
from dragzero.wiring import build_runtime

TOPO = {
    "version": 1,
    "nodes": [
        {"id": "a_plan", "type": "agent", "role": "planner", "entry": True},
        {"id": "a_code", "type": "agent", "role": "coder"},
        {"id": "t_read", "type": "tool", "tool": "read_file"},
        {"id": "h_deny", "type": "hook", "hook": "deny_delegation", "phase": "pre_delegate"},
        {"id": "mem", "type": "memory", "name": "scratch"},
    ],
    "edges": [
        {"from": "a_plan", "to": "a_code", "type": "delegates_to"},
        {"from": "a_code", "to": "t_read", "type": "uses_tool"},
    ],
    "budget": {"max_llm_calls": 10},
}


def _solo(ctx):
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _delegate_coder(ctx):
    if ctx["role"] == "planner":
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "delegate", "target": "coder", "subtask": "x"}}
    return _solo(ctx)


def test_round_trip_is_idempotent():
    t = load_json(json.dumps(TOPO))
    once = dump_json(t)
    twice = dump_json(load_json(once))
    assert once == twice  # load -> dump -> load -> dump is stable
    reloaded = Topology.from_dict(json.loads(once))
    assert {n.id for n in reloaded.nodes} == {"a_plan", "a_code", "t_read", "h_deny", "mem"}
    assert reloaded.budget == {"max_llm_calls": 10}


def test_validate_catches_structural_errors():
    bad = Topology.from_dict({
        "nodes": [
            {"id": "x", "type": "agent", "role": "p"},
            {"id": "x", "type": "weird"},
        ],
        "edges": [{"from": "x", "to": "ghost", "type": "delegates_to"}],
    })
    errs = bad.validate()
    assert any("duplicate node id" in e for e in errs)
    assert any("unknown node type" in e for e in errs)
    assert any("edge to unknown node" in e for e in errs)


def test_no_agent_node_is_error():
    with pytest.raises(TopologyError):
        Topology.from_dict({"nodes": [{"id": "t", "type": "tool", "tool": "read_file"}]}).validate(raise_on_error=True)


def test_build_runtime_wires_tools_and_hook(tmp_path):
    (tmp_path / "x.py").write_text("ok")
    rt = build_runtime(load_json(json.dumps(TOPO)), FakeLLM(_delegate_coder),
                       tool_catalog=default_tool_catalog(), sandbox=FsSandbox(tmp_path))
    log = rt.run("do a thing")

    assert len(rt.orchestrator.tools) == 1  # read_file registered from the topology
    assert EventType.HOOK_BLOCKED in log.types()  # deny_delegation hook fired
    assert EventType.SUBTASK_SPAWNED not in log.types()
    root, _ = reduce(log.events())
    assert root.status == "done"


def test_build_runtime_unknown_tool_raises():
    t = Topology.from_dict({"nodes": [
        {"id": "a", "type": "agent", "role": "planner", "entry": True},
        {"id": "tt", "type": "tool", "tool": "does_not_exist"},
    ]})
    with pytest.raises(TopologyError):
        build_runtime(t, FakeLLM(_solo), tool_catalog=default_tool_catalog())


def _router_topology():
    return Topology.from_dict({"nodes": [
        {"id": "a_plan", "type": "agent", "role": "planner", "entry": True},
        {"id": "a_ops", "type": "agent", "role": "devops"},
        {"id": "r", "type": "router", "rule": "by_keyword", "config": {"keyword": "deploy", "role": "devops"}},
    ]})


def test_router_rule_routes_by_keyword():
    rt = build_runtime(_router_topology(), FakeLLM(_solo))
    log = rt.orchestrator.run("please deploy the service")  # no forced agent -> rules decide
    assert log.of_type(EventType.TASK_STARTED)[0].agent_id == "a_ops"


def test_router_no_match_falls_back_to_entry():
    rt = build_runtime(_router_topology(), FakeLLM(_solo))
    log = rt.orchestrator.run("write some docs")  # no 'deploy' keyword
    assert log.of_type(EventType.TASK_STARTED)[0].agent_id == "a_plan"


def test_budget_node_becomes_a_halt():
    topo = Topology.from_dict({
        "nodes": [
            {"id": "a_plan", "type": "agent", "role": "planner", "entry": True},
            {"id": "a_code", "type": "agent", "role": "coder"},
        ],
        "budget": {"max_llm_calls": 1},
    })
    rt = build_runtime(topo, FakeLLM(_delegate_coder))
    log = rt.run("deep task")  # planner delegates -> 2nd call would exceed limit 1
    assert EventType.BUDGET_EXCEEDED in log.types()
