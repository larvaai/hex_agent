# Giải thích `tests/test_graph.py`

File `tests/test_graph.py` kiểm tra vòng single-agent graph trong `graph.runtime.run_agent`.

Nói ngắn gọn: test này đảm bảo agent loop có thể gọi tool, retry khi JSON hỏng, và dùng toolbox filesystem tools.

## Config test

```python
CONFIG = {
    "features": {
        "toolbox": {"enabled": True, "module": "toolbox.feature"},
        "example_echo": {"enabled": True, "module": "features.example_echo"},
    }
}
```

Kernel test bật hai feature:

- `toolbox`: fs/terminal tools.
- `example_echo`: tool echo đơn giản.

## Helper `scripted_llm`

```python
def scripted_llm(scripts):
    state = {"i": 0}

    def llm(messages, model=None):
        i = state["i"]
        state["i"] = min(i + 1, len(scripts) - 1)
        return scripts[i]

    return llm
```

Helper này tạo fake LLM trả lần lượt các string trong `scripts`.

Ý nghĩa:

- test graph offline,
- không cần LLM thật,
- kiểm soát chính xác action ở từng step.

Khi scripts hết, helper tiếp tục trả item cuối.

## `test_tool_then_final`

```python
llm = scripted_llm(
    [
        '{"action":"tool","tool":"echo","args":{"msg":"hi"}}',
        '{"action":"final","message":"done: hi"}',
    ]
)
out = run_agent("say hi", kernel=k, llm_call=llm, max_steps=5)
assert out["final"] == "done: hi"
assert out["steps"] == 2
```

Luồng:

1. LLM yêu cầu gọi tool `echo`.
2. Runtime gọi kernel/tool node.
3. Observation được append vào messages.
4. LLM trả final.
5. Runtime kết thúc ở step 2.

Hợp đồng: graph loop xử lý tool action rồi final action đúng.

## `test_retry_on_bad_json`

```python
llm = scripted_llm(["this is not json", '{"action":"final","message":"ok"}'])
out = run_agent("x", kernel=k, llm_call=llm, max_steps=5)
assert out["final"] == "ok"
```

Luồng:

1. LLM trả text không phải JSON.
2. `agent_node` trả action `retry`.
3. Runtime record parse error và append retry message.
4. LLM trả final hợp lệ.
5. Runtime kết thúc.

Hợp đồng: graph không chết khi LLM output hỏng; nó retry bằng discipline gate.

## `test_agent_uses_fs_tools`

```python
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
```

Test này set:

```python
AGENT_WORKSPACE_DIR=<tmp>/ws
```

Luồng:

1. Agent gọi `fs_write`.
2. File được ghi trong workspace.
3. Agent gọi `fs_read`.
4. Agent final.
5. Test kiểm tra file thật tồn tại và có content `"hello"`.

Hợp đồng: graph loop tích hợp được với toolbox filesystem tools qua kernel.

## Env var trong test

Mỗi test set:

```python
AGENT_RUNS_DIR
AGENT_WORKSPACE_DIR
```

để log và workspace nằm trong `tmp_path`, không ảnh hưởng máy thật.

## Nếu test này đỏ nghĩa là gì?

- `run_agent` có thể không xử lý action tool/final đúng.
- Retry JSON gate có thể hỏng.
- Observation có thể không quay lại loop.
- Toolbox feature có thể không đăng ký hoặc sandbox path sai.
- EventLogger/runs dir có thể không tương thích với graph runtime.

## Tóm tắt

`tests/test_graph.py` bảo vệ vòng agent thật: tool call, retry invalid JSON, final answer và integration với filesystem toolbox.
