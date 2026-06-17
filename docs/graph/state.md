# Giải thích `graph/state.py`

File `graph/state.py` định nghĩa `AgentState`, state object cho vòng single-agent graph.

Nói ngắn gọn: `AgentState` giữ trí nhớ ngắn hạn của agent loop.

## Nội dung chính

```python
@dataclass
class AgentState:
    task: str
    messages: list[dict[str, str]] = field(default_factory=list)
    step: int = 0
    final: str | None = None
    last_action: dict[str, Any] | None = None
    code_changed: bool = False
    validation_passed: bool = False
```

## Các field

`task`: yêu cầu gốc của user. Đây là input ban đầu được đưa vào prompt.

`messages`: lịch sử message bổ sung giữa graph và LLM. Ví dụ observation sau khi tool chạy, hoặc retry message khi JSON hỏng.

`step`: số bước agent đã chạy.

`final`: câu trả lời cuối cùng nếu agent đã hoàn tất.

`last_action`: chỗ chuẩn bị để giữ action gần nhất. Hiện runtime chưa set field này.

`code_changed`: cờ cho biết tool/role đã thay đổi code. Finish gate dùng cờ này để yêu cầu validation.

`validation_passed`: cờ cho biết validation đã pass. Finish gate dùng cùng `code_changed`.

## Vì sao có state riêng?

Kernel có `StateStore`, nhưng graph cần state giàu ngữ cảnh hơn cho vòng agent:

- task,
- message history,
- step counter,
- final answer,
- validation flags.

Tách `AgentState` giúp graph loop không nhồi quá nhiều logic vào kernel.

## Quan hệ với file khác

- `graph.nodes.agent_node()` đọc `state.task` và `state.messages`.
- `graph.runtime.run_agent()` tăng `state.step`, cập nhật `state.final`, append observations vào `state.messages`.
- `discipline.finish_gate.check_finish()` dùng `code_changed` và `validation_passed`.

## Tóm tắt

`graph/state.py` chứa dataclass `AgentState`, là state runtime của single-agent loop và là nền để multi-agent sau này tái dùng.
