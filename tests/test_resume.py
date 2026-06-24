"""Resume: run writes a checkpoint each step; resume() restores state+messages+budget and continues. Epic E07."""
from core.bootstrap import build_kernel
from core.schemas import TaskEnvelope
from features.llm_chat import FEATURE, LLMChatTool
from orchestrator import resume, run
from orchestrator.checkpoint import (
    Checkpoint,
    checkpoint_db_path,
    checkpoint_path,
    load_checkpoint,
    save_checkpoint,
)


def _client(script):
    class _C:
        def __init__(self):
            self.script = list(script)
            outer = self

            class _Comp:
                def create(self, **kw):
                    c = outer.script.pop(0) if outer.script else '{"action":"final","message":"(auto)"}'
                    return type("R", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": c})()})()]})()

            self.chat = type("X", (), {"completions": _Comp()})()
    return _C()


def _agent(client):
    k = build_kernel({"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}})
    k.registry.register_feature(FEATURE)
    k.registry.register_tools(FEATURE.capabilities, LLMChatTool(client=client), feature_name=FEATURE.name)
    return k


def test_run_writes_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    k = _agent(_client(['{"action":"final","message":"ok","finish_reason":"done"}']))
    out = run(k, "x", run_id="run42")
    assert out["status"] == "completed"
    cp = load_checkpoint("run42")
    assert cp is not None and cp.status == "completed" and cp.backend == "langgraph"
    assert checkpoint_db_path("run42").exists()


def test_resume_completed_returns_stored_result(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    k = _agent(_client(['{"action":"final","message":"done-once","finish_reason":"done"}']))
    run(k, "x", run_id="r-done")
    k2 = _agent(_client(['{"action":"final","message":"SHOULD-NOT-RUN"}']))
    out = resume(k2, "r-done")
    assert out["status"] == "completed" and out["result"] == "done-once"


def test_run_can_disable_durable_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    k = _agent(_client(['{"action":"final","message":"ephemeral","finish_reason":"done"}']))
    out = run(k, "x", run_id="off", checkpoint=False)
    assert out["status"] == "completed" and out["result"] == "ephemeral"
    assert not checkpoint_db_path("off").exists()
    assert not checkpoint_path("off").exists()


def test_resume_continues_interrupted_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    task = TaskEnvelope(user_request="do X")
    cp = Checkpoint(
        run_id="r-mid", task="do X",
        messages=[{"role": "system", "content": "sys"},
                  {"role": "user", "content": "do X"},
                  {"role": "assistant", "content": '{"action":"tool","tool":"echo","args":{}}'},
                  {"role": "user", "content": "OBSERVATION: {}"}],
        budget={"max_steps": 30, "max_parse_errors": 3, "max_same_tool_calls": 3,
                "steps": 1, "parse_errors": 0, "_tool_calls": {}},
        state={"current_task": task},
        step=1, status="running",
    )
    save_checkpoint(cp)
    k = _agent(_client(['{"action":"final","message":"resumed-done","finish_reason":"done"}']))
    out = resume(k, "r-mid")
    assert out["status"] == "completed"
    assert out["result"] == "resumed-done"
    assert out["task_id"] == task.task_id  # same task_id preserved across resume


def test_resume_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    k = _agent(_client([]))
    try:
        resume(k, "ghost")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_resume_continues_from_langgraph_node_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    first = _agent(_client([]))
    original_execute = first.execute_tool

    def crash_once(tool_name, args=None):
        if tool_name == "llm.chat":
            raise RuntimeError("simulated process crash")
        return original_execute(tool_name, args)

    first.execute_tool = crash_once
    try:
        run(first, "survive restart", run_id="r-crash")
        assert False, "expected simulated crash"
    except RuntimeError as exc:
        assert "simulated process crash" in str(exc)

    persisted_task_id = load_checkpoint("r-crash").state["current_task"].task_id
    second = _agent(_client(['{"action":"final","message":"recovered","finish_reason":"done"}']))
    out = resume(second, "r-crash")
    assert out["status"] == "completed" and out["result"] == "recovered"
    assert out["task_id"] == persisted_task_id
