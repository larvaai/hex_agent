"""E05 — single-agent loop: tool->final, parse recovery, finish gate, step budget. Driven by a scripted LLM."""
from core.bootstrap import build_kernel
from discipline import Budget
from features.llm_chat import FEATURE, LLMChatTool
from orchestrator import run


def _scripted_client(script):
    class _Client:
        def __init__(self):
            self.script = list(script)
            outer = self

            class _Completions:
                def create(self, **kwargs):
                    content = outer.script.pop(0) if outer.script else '{"action":"final","message":"(auto)"}'
                    return type("R", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": content})()})()]})()

            self.chat = type("C", (), {"completions": _Completions()})()
    return _Client()


def _always_tool_client():
    class _Client:
        def __init__(self):
            class _Completions:
                def create(self, **kwargs):
                    return type("R", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": '{"action":"tool","tool":"echo","args":{}}'})()})()]})()
            self.chat = type("C", (), {"completions": _Completions()})()
    return _Client()


def _agent(client):
    k = build_kernel({"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}})
    k.registry.register_feature(FEATURE)
    k.registry.register_tools(FEATURE.capabilities, LLMChatTool(client=client), feature_name=FEATURE.name)
    return k


def test_loop_tool_then_final():
    k = _agent(_scripted_client([
        '{"action":"tool","tool":"echo","args":{"msg":"hi"}}',
        '{"action":"final","message":"done","finish_reason":"done"}',
    ]))
    seen = []
    k.events.subscribe(lambda t, p: seen.append((t, p)))
    out = run(k, "do the thing")
    assert out["status"] == "completed" and out["result"] == "done"
    assert any(t == "tool.completed" and p["tool"] == "echo" for t, p in seen)
    tids = {p.get("task_id") for t, p in seen if t.startswith("tool.")}
    assert len(tids) == 1 and None not in tids          # every tool event correlated to the task


def test_loop_recovers_from_bad_json():
    k = _agent(_scripted_client(["not json at all", '{"action":"final","message":"ok"}']))
    b = Budget()
    out = run(k, "x", budget=b)
    assert out["status"] == "completed" and out["result"] == "ok"
    assert b.parse_errors == 1
    assert b.steps == 1                                 # parse error did not consume a step


def test_loop_finish_gate_blocks_then_blocker():
    k = _agent(_scripted_client([
        '{"action":"final","message":"x","finish_reason":"done"}',
        '{"action":"final","message":"x","finish_reason":"blocker"}',
    ]))
    k.state.set("code_changed", True)
    out = run(k, "x")
    assert out["status"] == "completed"


def test_loop_step_budget_fails():
    k = _agent(_always_tool_client())
    out = run(k, "loop forever", budget=Budget(max_steps=2))
    assert out["status"] == "failed"
    assert "step budget" in out["result"]["reason"]
