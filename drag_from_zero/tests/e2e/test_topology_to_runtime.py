"""E2E: examples/topology.json config -> live runtime behaviour, end to end."""
import pathlib

from dragzero import EventType, FakeLLM, build_runtime, load_file, reduce
from dragzero.adapters.tools_fs import FsSandbox, default_tool_catalog

# tests/e2e/test_topology_to_runtime.py -> parents[2] is the repo root.
EXAMPLES = pathlib.Path(__file__).resolve().parents[2] / "examples" / "topology.json"


def _responder(ctx):
    """Plan+decision or a tool action, scripted per role to match the agent seam."""
    role = ctx["role"]
    if role == "planner":
        return {
            "plan": {"steps": [], "next": None},
            "decision": {"mode": "delegate", "target": "coder", "subtask": "write the patch"},
        }
    if role == "coder":
        if not ctx["observations"]:
            # first step: emit a write_file tool action (observable TOOL_CALLED)
            return {"action": {"type": "tool", "tool": "write_file",
                               "args": {"path": "out.txt", "content": "done"}}}
        # second step: tool ran, observations non-empty -> terminal solo decision
        return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}
    # reviewer / devops: solo
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def _solo(ctx):
    return {"plan": {"steps": [], "next": None}, "decision": {"mode": "solo"}}


def test_example_topology_loads_and_validates():
    topo = load_file(str(EXAMPLES))
    topo.validate(raise_on_error=True)  # must not raise
    assert topo.budget == {"max_llm_calls": 50}


def test_config_drives_delegation_tool_and_completion(tmp_path):
    topo = load_file(str(EXAMPLES))
    rt = build_runtime(topo, FakeLLM(_responder),
                       tool_catalog=default_tool_catalog(), sandbox=FsSandbox(tmp_path))
    log = rt.run("Fix parse_config and add a test")

    types = log.types()
    assert EventType.SUBTASK_SPAWNED in types  # planner delegated to coder
    assert EventType.TOOL_CALLED in types      # coder called write_file

    # the coder actually wrote the file through the sandbox
    assert (tmp_path / "out.txt").exists()
    assert (tmp_path / "out.txt").read_text() == "done"

    # the execution-tree root folded from the log is done
    root, _nodes = reduce(log.events())
    assert root.status == "done"


def test_router_routes_deploy_to_devops_and_else_to_entry():
    # Rebuilt runtime per assertion: a fresh orchestrator with no pre-run state.
    rt2 = build_runtime(load_file(str(EXAMPLES)), FakeLLM(_solo),
                        tool_catalog=default_tool_catalog())
    log = rt2.orchestrator.run("please deploy the service")
    # by_keyword('deploy' -> role 'devops') resolves to the devops agent id 'ops'
    assert log.of_type(EventType.TASK_STARTED)[0].agent_id == "ops"

    rt3 = build_runtime(load_file(str(EXAMPLES)), FakeLLM(_solo),
                        tool_catalog=default_tool_catalog())
    log2 = rt3.orchestrator.run("write some docs")  # no 'deploy' keyword
    # no rule match -> falls back to the entry planner id 'plan'
    assert log2.of_type(EventType.TASK_STARTED)[0].agent_id == "plan"
