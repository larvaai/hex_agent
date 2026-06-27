# Case 01 — Orchestrator Loop: Facade `run()` / `resume()` trên LangGraph

> **Một interface đơn giản (`run`, `resume`) phía trước cả một subsystem chạy graph: kernel, session, builder graph, checkpointer, budget.**

---

## 1. Bối cảnh trong hex_agent

Để chạy một tác vụ agent, hệ thống phải phối hợp rất nhiều mảnh: lấy `AgentKernel` (registry năng lực + event bus dùng chung), tạo `KernelSession` cô lập cho run này, biên dịch một `StateGraph` 6 node (guard/agent/tool/delegate/finish/fail), mở `checkpointer` để persist, tính `recursion_limit` theo `Budget`, stream graph tới terminal state rồi đồng bộ budget lại. Nếu mỗi nơi muốn "chạy 1 task" đều phải tự làm chuỗi này thì coupling khủng khiếp.

hex_agent gói tất cả sau **hai hàm public**: `run()` và `resume()`. Module docstring nói thẳng vai trò:

- `orchestrator/loop.py:1` — `"""Public run/resume facade backed by the single compiled LangGraph."""`
- `orchestrator/loop.py:93-147` — `run()`: tạo/nhận session, build graph (kèm hoặc không checkpoint), `_stream` tới terminal, `_sync_budget`, trả `_outcome`.
- `orchestrator/loop.py:217-273` — `resume()`: đọc checkpoint, khôi phục session, build graph, stream tiếp.
- `orchestrator/loop.py:40-90` — các helper nội bộ `_config`, `_outcome`, `_sync_budget`, `_stream` mà `run`/`resume` lắp ráp.
- `graph/runtime.py:31-66` — `build_agent_graph()`: builder dựng StateGraph 6 node + routing.

Client cấp trên (ví dụ `ui/server.py:230-251`, hàm `RunController._execute`) chỉ gọi `run_agent(kernel, prompt, ...)` — **không** import `SessionFactory`, `build_agent_graph` hay module `checkpoint`.

## 2. Trích đoạn code thật

```python
# orchestrator/loop.py:1
"""Public run/resume facade backed by the single compiled LangGraph."""

# orchestrator/loop.py:93-104, 130-147 (rút gọn)
def run(kernel, user_request, *, budget=None, ..., checkpoint=True,
        session=None, delegation_service=None):
    """Start a task and drive the compiled graph to a terminal state."""
    active_session = session or SessionFactory(kernel=kernel).create_root(...)
    ...
    if not checkpoint:
        graph = build_agent_graph(session=active_session, delegation_service=delegation_service)
        state = _stream(graph, initial, config=config, projection=False)
        _sync_budget(active_budget, state)
        return _outcome(state)

    with open_checkpointer(rid) as saver:
        graph = build_agent_graph(session=active_session, checkpointer=saver,
                                  delegation_service=delegation_service)
        state = _stream(graph, initial, config=config, projection=True)
        _sync_budget(active_budget, state)
        return _outcome(state)
```

```python
# graph/runtime.py:31-37
def build_agent_graph(*, session, checkpointer=None, delegation_service=None):
    """Build the sole orchestration graph around an isolated runtime session."""
    builder = StateGraph(AgentState)
    builder.add_node("guard", partial(guard_node, session=session))
    ...
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Facade | Thành phần trong hex_agent | Trong bản distill `.py` |
|---|---|---|
| **Facade** (stateless, là hàm) | `run()`, `resume()` — `orchestrator/loop.py:93`, `:217` | `run()`, `resume()` |
| Subsystem 1 — năng lực dùng chung | `AgentKernel` (`core/kernel.py`) | `AgentKernel` + `EventBus` |
| Subsystem 2 — cô lập state mỗi run | `SessionFactory` / `KernelSession` (`core/session.py`) | `SessionFactory` / `KernelSession` |
| Subsystem 3 — biên dịch graph | `build_agent_graph()` (`graph/runtime.py:31`) | `build_agent_graph()` → `CompiledGraph` |
| Subsystem 4 — persist & resume | `open_checkpointer` (`orchestrator/checkpoint.py`) | `Checkpointer` (dict in-memory) |
| Subsystem 5 — giới hạn run | `Budget` (`discipline`) | `Budget` |
| Helper nội bộ của facade | `_config`/`_outcome`/`_sync_budget`/`_stream` (`orchestrator/loop.py:40-90`) | `_outcome`, `_stream` |
| Client | `ui/server.py:230-251` gọi `run_agent(...)` | `demo()` gọi `run()`/`resume()` |

## 4. Bản rút gọn chạy được

File: [`orchestrator_loop_facade.py`](./orchestrator_loop_facade.py) — chạy `python3 orchestrator_loop_facade.py`.

**Mô phỏng gì:**
- Giữ đúng choreography của facade thật: `create_root` → `build_agent_graph` → `_stream` tới terminal → trả `_outcome`; đường `resume` đọc checkpoint rồi chạy tiếp.
- `CompiledGraph.stream()` mô phỏng vòng lặp guard→agent→tool→final, có `budget.tick()` ở mỗi node (vai trò node "guard" gác budget) và lưu checkpoint từng bước.
- `demo()` minh hoạ: (1) `run` không checkpoint; (2) đối chứng `run_without_facade` client tự lắp ráp; (3) `run` hết budget giữa chừng → checkpoint dở → `resume` chạy nốt; (4) hoán đổi checkpoint backend không đụng client.

**Lược bỏ gì (so với bản thật):**
- LangGraph thật → một `CompiledGraph` kịch bản xác định bằng list. Không có routing có điều kiện thật, không có `recursion_limit`.
- LLM agent thật → kế hoạch tool cố định.
- SQLite checkpointer + JSON projection + migration legacy (`_legacy_state`, `_restore_persisted_session`) → checkpoint dict in-memory đơn giản.
- `delegation_service`, `TaskEnvelope`, đồng bộ budget chi tiết → giản lược.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Single point of failure**: phá facade là phá đường chạy task (giống brainstem stroke trong bài gốc). `run/resume` phải được test kỹ vì mọi client phụ thuộc.
- **Nguy cơ God Object**: nếu nhét thêm mọi biến thể chạy (batch, streaming UI, eval...) vào `run()`, nó phình. hex_agent giữ facade mỏng bằng cách đẩy logic vào helper (`_config/_outcome/_stream`) và builder riêng (`build_agent_graph`).
- **Khi client cần kiểm soát chi tiết** từng node/edge của graph cho mục đích nghiên cứu, facade quá kín; lúc đó nên dùng thẳng `build_agent_graph` (facade không cấm — GoF cho phép bypass có kiểm soát).
- **Subsystem quá đơn giản** (1-2 bước) thì thêm facade chỉ là lớp gián tiếp thừa.

## 6. Câu hỏi tự kiểm tra

1. `run()` là facade **stateless** (hàm, không lưu state riêng) trong khi brainstem ở bài gốc là **stateful**. Ưu/nhược của lựa chọn stateless ở đây là gì, và state thực sự nằm ở đâu?
2. Vì sao tách `build_agent_graph()` (builder) ra khỏi `run()` (facade) lại giúp facade không biến thành God Object? Builder đóng vai trò gì trong cặp Facade + Factory?
3. Khi đổi checkpoint backend (ví dụ từ SQLite sang Postgres), những file nào phải sửa và những file nào tuyệt đối không cần đụng? Bản distill chứng minh điều này ở bước `[4]` như thế nào?
