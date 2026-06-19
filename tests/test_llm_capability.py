"""Part D — LLM is a capability: envelope + events + llm_calls metric + distinct LLMCallEvent. Epic E03/E04."""
from core.bootstrap import build_kernel, create_kernel
from features.llm_chat import FEATURE, LLMChatTool


class _FakeChoiceMsg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeClient:
    """Mirrors the injectable fake client used in tests/test_llm_adapter.py (offline)."""

    def __init__(self, content='{"action":"final","message":"ok"}', boom=False):
        self.content = content
        self.boom = boom
        self.kwargs = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.kwargs = kwargs
                if outer.boom:
                    raise RuntimeError("boom")
                return type("R", (), {"choices": [_FakeChoiceMsg(outer.content)]})()

        self.chat = type("C", (), {"completions": _Completions()})()


def _kernel_with_fake_llm(fake):
    k = build_kernel({"features": {}})
    k.registry.register_feature(FEATURE)
    k.registry.register_tools(FEATURE.capabilities, LLMChatTool(client=fake), feature_name=FEATURE.name)
    return k


def test_llm_is_a_capability_with_envelope():
    fake = _FakeClient()
    k = _kernel_with_fake_llm(fake)
    env = k.execute_tool("llm.chat", {"messages": [{"role": "user", "content": "hi"}], "json_mode": True})
    assert env["ok"] is True
    assert env["capability"] == "llm.chat"
    assert env["feature"] == "llm"
    assert env["data"]["content"] == '{"action":"final","message":"ok"}'
    assert fake.kwargs["response_format"] == {"type": "json_object"}


def test_llm_call_emits_tool_events_with_task_id():
    fake = _FakeClient()
    k = _kernel_with_fake_llm(fake)
    seen = []
    k.events.subscribe(lambda t, p: seen.append((t, p)))
    task = k.accept_task("llm trace")
    k.execute_tool("llm.chat", {"messages": []})
    topics = [t for t, _ in seen]
    assert "tool.requested" in topics and "tool.completed" in topics
    for t, p in seen:
        if t.startswith("tool."):
            assert p["task_id"] == task.task_id


def test_llm_calls_metric_and_distinct_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    from observability import EventLogger, attach_to_bus
    from observability import inspect as insp

    fake = _FakeClient()
    k = _kernel_with_fake_llm(fake)
    logger = EventLogger(run_id="llmrun")
    attach_to_bus(logger, k.events)
    k.accept_task("x")
    k.execute_tool("llm.chat", {"messages": []})
    summary = logger.finish("completed")
    assert summary["metrics"]["llm_calls"] == 1
    assert summary["metrics"]["tool_calls"] == 1
    llm_events = insp.read_events("llmrun", kind="LLMCallEvent")
    assert any(e["topic"] == "tool.completed" for e in llm_events)
    assert all(e.get("task_id") for e in llm_events)  # task_id threaded (part B)


def test_default_config_registers_llm_chat():
    k = create_kernel()
    assert k.registry.has_tool("llm.chat")
