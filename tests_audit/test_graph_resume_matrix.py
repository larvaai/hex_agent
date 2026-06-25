"""Graph transition, failure and crash/resume matrix."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.bootstrap import build_kernel
from core.schemas import FeatureDescriptor
from core.session import SessionFactory
from discipline import Budget
from features.llm_chat import FEATURE as LLM_FEATURE
from features.llm_chat import LLMChatTool
from graph.nodes import agent_node, tool_node
from graph.state import new_agent_state
from orchestrator import resume, run
from orchestrator.checkpoint import Checkpoint, load_checkpoint, save_checkpoint


BASE_CONFIG = {
    "features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}
}


class ScriptClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.calls += 1
                if not outer.script:
                    raise AssertionError("unexpected LLM call")
                value = outer.script.pop(0)
                if isinstance(value, Exception):
                    raise value
                message = type("Message", (), {"content": value})()
                return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

        self.chat = type("Chat", (), {"completions": Completions()})()


def _agent(*script):
    kernel = build_kernel(BASE_CONFIG)
    client = ScriptClient(script)
    kernel.registry.register_feature(LLM_FEATURE)
    kernel.registry.register_tools(
        LLM_FEATURE.capabilities,
        LLMChatTool(client=client),
        feature_name=LLM_FEATURE.name,
        kind="model",
        idempotent=True,
    )
    return kernel, client


def _state(kernel, *, max_steps=12, max_parse_errors=3):
    session = SessionFactory(kernel=kernel).create_root("task", run_id="run")
    state = new_agent_state(
        session=session,
        messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "task"}],
        budget=Budget(max_steps=max_steps, max_parse_errors=max_parse_errors),
    )
    return session, state


@pytest.mark.audit
@pytest.mark.parametrize("verb", ["", "TOOL", "unknown", " finish ", 42, None])
def test_unknown_action_never_dispatches_a_tool_and_consumes_exactly_one_step(verb):
    kernel, _ = _agent(json.dumps({"action": verb}))
    session, state = _state(kernel)

    update = agent_node(state, session=session)

    assert update["route"] == "guard"
    assert update["budget"]["steps"] == 1
    assert update["messages"][-1]["role"] == "user"
    assert "Unknown 'action'" in update["messages"][-1]["content"]


@pytest.mark.audit
def test_non_mapping_tool_args_are_normalized_to_empty_mapping():
    kernel, _ = _agent()
    session, state = _state(kernel)
    state["last_action"] = {"action": "tool", "tool": "echo", "args": ["not", "a", "mapping"]}

    update = tool_node(state, session=session)
    observation = json.loads(update["messages"][-1]["content"])

    assert update["route"] == "guard"
    assert observation["ok"] is True
    assert observation["data"] == {"echo": {}}


@pytest.mark.audit
def test_missing_tool_is_an_observation_not_an_unhandled_exception():
    kernel, _ = _agent()
    observation = kernel.execute_tool("does.not.exist", {})

    assert observation["ok"] is False
    assert observation["data"]["missing_capability"] is True


@pytest.mark.audit
def test_llm_transport_failure_preserves_root_cause_in_terminal_outcome():
    kernel, _ = _agent(RuntimeError("provider connection reset"))

    outcome = run(
        kernel,
        "task",
        budget=Budget(max_steps=4, max_parse_errors=1),
        checkpoint=False,
    )

    assert outcome["status"] == "failed"
    assert "provider connection reset" in outcome["result"]["reason"]


@pytest.mark.audit
def test_run_rejects_foreign_session_task_and_run_id():
    first, _ = _agent()
    second, _ = _agent()
    foreign = SessionFactory(kernel=second).create_root("task", run_id="actual")
    with pytest.raises(ValueError, match="different kernel"):
        run(first, "task", session=foreign, checkpoint=False)

    own, _ = _agent()
    session = SessionFactory(kernel=own).create_root("owned", run_id="actual")
    with pytest.raises(ValueError, match="requested task"):
        run(own, "different", session=session, checkpoint=False)
    with pytest.raises(ValueError, match="run_id"):
        run(own, "owned", session=session, run_id="different", checkpoint=False)


@pytest.mark.audit
def test_resume_completed_run_does_not_call_llm_again():
    first, first_client = _agent('{"action":"final","message":"once","finish_reason":"done"}')
    assert run(first, "task", run_id="done")["result"] == "once"
    assert first_client.calls == 1
    second, second_client = _agent(AssertionError("completed run called the LLM"))

    outcome = resume(second, "done")

    assert outcome["status"] == "completed"
    assert outcome["result"] == "once"
    assert second_client.calls == 0


@pytest.mark.audit
def test_crash_after_effect_does_not_replay_effect_on_resume():
    effects = []

    class Effect:
        def execute(self, request):
            effects.append(dict(request.args))
            return {"ok": True, "applied": len(effects)}

    first, _ = _agent('{"action":"tool","tool":"effect","args":{"id":1}}')
    first.registry.register_feature(FeatureDescriptor("effect_feature", capabilities=("effect",)))
    first.registry.register_tool("effect", Effect(), feature_name="effect_feature", kind="effect", idempotent=False)
    original = first.execute_tool
    llm_calls = 0

    def crash_on_second_llm(name, args=None, **kwargs):
        nonlocal llm_calls
        if name == "llm.chat":
            llm_calls += 1
            if llm_calls == 2:
                raise RuntimeError("simulated hard crash after effect")
        return original(name, args, **kwargs)

    first.execute_tool = crash_on_second_llm
    with pytest.raises(RuntimeError, match="hard crash"):
        run(first, "apply once", run_id="effect-crash")
    assert effects == [{"id": 1}]

    second, _ = _agent('{"action":"final","message":"recovered","finish_reason":"done"}')
    second.registry.register_feature(FeatureDescriptor("effect_feature", capabilities=("effect",)))
    second.registry.register_tool("effect", Effect(), feature_name="effect_feature", kind="effect", idempotent=False)
    outcome = resume(second, "effect-crash")

    assert outcome["status"] == "completed"
    assert outcome["result"] == "recovered"
    assert effects == [{"id": 1}]


@pytest.mark.audit
@pytest.mark.concurrency
def test_json_projection_same_run_concurrent_writes_remain_atomic_and_valid():
    checkpoints = [
        Checkpoint(run_id="shared", task=f"task-{index}", step=index, status="running")
        for index in range(100)
    ]

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(save_checkpoint, item) for item in checkpoints]
        errors = [future.exception() for future in futures]

    assert errors == [None] * len(checkpoints)
    loaded = load_checkpoint("shared")
    assert loaded is not None
    assert loaded.step in range(100)
    assert loaded.task == f"task-{loaded.step}"


@pytest.mark.audit
def test_checkpoint_from_json_rejects_missing_or_wrong_typed_identity():
    with pytest.raises(ValueError, match="run_id"):
        Checkpoint.from_json({})
    with pytest.raises((TypeError, ValueError), match="run_id"):
        Checkpoint.from_json({"run_id": ["not", "a", "string"]})
