from core.bootstrap import build_kernel
from graph.runtime import run_agent

CONFIG = {
    "features": {
        "toolbox": {"enabled": True, "module": "toolbox.feature"},
        "example_echo": {"enabled": True, "module": "features.example_echo"},
    }
}


def scripted_llm(scripts):
    state = {"i": 0}

    def llm(messages, model=None):
        i = state["i"]
        state["i"] = min(i + 1, len(scripts) - 1)
        return scripts[i]

    return llm


def test_tool_then_final(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    k = build_kernel(CONFIG)
    llm = scripted_llm(
        [
            '{"action":"tool","tool":"echo","args":{"msg":"hi"}}',
            '{"action":"final","message":"done: hi"}',
        ]
    )
    out = run_agent("say hi", kernel=k, llm_call=llm, max_steps=5)
    assert out["final"] == "done: hi"
    assert out["steps"] == 2


def test_retry_on_bad_json(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    k = build_kernel(CONFIG)
    llm = scripted_llm(["this is not json", '{"action":"final","message":"ok"}'])
    out = run_agent("x", kernel=k, llm_call=llm, max_steps=5)
    assert out["final"] == "ok"


def test_agent_uses_fs_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    k = build_kernel(CONFIG)
    llm = scripted_llm(
        [
            '{"action":"tool","tool":"fs_write","args":{"path":"a.txt","content":"hello"}}',
            '{"action":"tool","tool":"fs_read","args":{"path":"a.txt"}}',
            '{"action":"final","message":"read it"}',
        ]
    )
    out = run_agent("write then read", kernel=k, llm_call=llm, max_steps=6)
    assert out["final"] == "read it"
    assert (tmp_path / "ws" / "a.txt").read_text() == "hello"
