"""Sequential call-return delegation stays outside kernel and LangGraph contracts."""
from adapters.agents import LangGraphDelegationAgent, ScriptedDelegationAgent
from core.bootstrap import build_kernel
from core.schemas import DelegationPolicy, DelegationSpec
from core.session import SessionFactory
from delegation import DelegationManager, DelegationRegistry, InMemoryDelegationStore
from features.llm_chat import FEATURE, LLMChatTool
from observability import EventLogger, attach_to_bus
from orchestrator import run

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}


def _manager(kernel, *, target="agent:review", artifacts=None):
    registry = DelegationRegistry()
    registry.register(ScriptedDelegationAgent(target, artifacts=artifacts))
    store = InMemoryDelegationStore()
    manager = DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=store,
    )
    return manager, store


def _scripted_client(script):
    class Client:
        def __init__(self):
            self.script = list(script)
            outer = self

            class Completions:
                def create(self, **kwargs):
                    content = outer.script.pop(0)
                    message = type("M", (), {"content": content})()
                    return type("R", (), {"choices": [type("C", (), {"message": message})()]})()

            self.chat = type("Chat", (), {"completions": Completions()})()

    return Client()


def test_manager_persists_progress_before_notification():
    kernel = build_kernel(ECHO)
    manager, store = _manager(kernel, artifacts=[{"kind": "finding", "value": 1}])
    parent = SessionFactory(kernel=kernel).create_root("parent")
    durable_when_seen = []

    def observe(topic, payload):
        if topic == "delegation.progress":
            durable_when_seen.append(len(store.progress(payload["delegation_id"])) == payload["sequence"])

    kernel.events.subscribe(observe)
    result = manager.delegate(parent, "agent:review", DelegationSpec("review this"))
    assert result.outcome == "success"
    assert len(result.artifacts) == 1
    assert durable_when_seen == [True]
    assert parent.is_active


def test_delegation_metrics_follow_bus_events():
    kernel = build_kernel(ECHO)
    manager, _ = _manager(kernel, artifacts=[{"kind": "finding"}])
    logger = EventLogger(run_id="delegation-metrics", enabled=False)
    attach_to_bus(logger, kernel.events)
    parent = SessionFactory(kernel=kernel).create_root("parent")
    manager.delegate(parent, "agent:review", DelegationSpec("review"))
    assert logger.metrics["delegations"] == 1
    assert logger.metrics["delegation_progress"] == 1
    assert logger.metrics["delegation_failures"] == 0


def test_missing_target_returns_structured_failure():
    kernel = build_kernel(ECHO)
    registry = DelegationRegistry()
    store = InMemoryDelegationStore()
    manager = DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=store,
    )
    parent = SessionFactory(kernel=kernel).create_root("parent")
    result = manager.delegate(parent, "agent:missing", DelegationSpec("x"))
    assert result.outcome == "failed"
    assert "No delegation handler" in result.error
    assert store.result(result.delegation_id) == result


def test_policy_rejects_scope_expansion_as_result():
    kernel = build_kernel(ECHO)
    manager, store = _manager(kernel)
    parent = SessionFactory(kernel=kernel).create_root(
        "parent", allowed_capabilities=frozenset({"echo"})
    )
    result = manager.delegate(
        parent,
        "agent:review",
        DelegationSpec("x"),
        DelegationPolicy(allowed_capabilities=frozenset({"echo", "terminal_run"})),
    )
    assert result.outcome == "rejected"
    assert "scope exceeds" in result.error
    assert store.result(result.delegation_id) == result


def test_parent_graph_delegate_action_returns_to_parent_agent():
    client = _scripted_client(
        [
            '{"action":"delegate","target":"agent:review",'
            '"spec":{"objective":"review","input_context":{"file":"x.py"}},"policy":{}}',
            '{"action":"final","message":"parent resumed","finish_reason":"done"}',
        ]
    )
    kernel = build_kernel(ECHO)
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(
        FEATURE.capabilities,
        LLMChatTool(client=client),
        feature_name=FEATURE.name,
    )
    manager, _ = _manager(kernel, artifacts=[{"kind": "finding", "severity": "low"}])
    finished = []
    kernel.events.subscribe(
        lambda topic, payload: finished.append(payload)
        if topic == "delegation.finished"
        else None
    )
    outcome = run(
        kernel,
        "delegate then finish",
        checkpoint=False,
        delegation_service=manager,
    )
    assert outcome["status"] == "completed"
    assert outcome["result"] == "parent resumed"
    assert finished and finished[0]["outcome"] == "success"


def test_langgraph_child_is_an_adapter_behind_delegation_port():
    kernel = build_kernel(ECHO)
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(
        FEATURE.capabilities,
        LLMChatTool(
            client=_scripted_client(
                ['{"action":"final","message":"child answer","finish_reason":"done"}']
            )
        ),
        feature_name=FEATURE.name,
    )
    registry = DelegationRegistry()
    registry.register(LangGraphDelegationAgent("agent:general"))
    manager = DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=InMemoryDelegationStore(),
    )
    parent = SessionFactory(kernel=kernel).create_root("parent")
    result = manager.delegate(parent, "agent:general", DelegationSpec("solve child task"))
    assert result.outcome == "success"
    assert result.summary["final"] == "child answer"
    assert result.summary["steps"] == 1
