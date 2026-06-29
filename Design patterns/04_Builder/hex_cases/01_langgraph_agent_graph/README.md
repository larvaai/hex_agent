# Case 01 — LangGraph StateGraph Builder: Graph điều phối Agent

> Builder (Creational) trong hex_agent: `StateGraph` đóng vai builder, tích lũy
> node + cạnh qua từng method, validate tại `.compile()`, trả về một compiled
> graph **immutable**.

---

## 1. Bối cảnh trong hex_agent

hex_agent điều phối agent bằng một **máy trạng thái có hướng** (state machine):
agent đi qua các node `guard -> agent -> tool/delegate/finish/fail` theo các cạnh
điều kiện. Việc "lắp ráp" graph này rất phức tạp: 6 node, mỗi node có hàm xử lý
riêng (cần inject `session`), và một mạng cạnh điều kiện định tuyến giữa chúng.

Nếu dựng graph bằng tay (tạo struct, gán dict node, gán dict cạnh, tự kiểm tra
tính hợp lệ) thì code vừa rối vừa dễ sai: quên một cạnh ra, trỏ tới node không
tồn tại, không reach được `END`... và lỗi chỉ lộ ra lúc chạy.

hex_agent dùng `StateGraph` của LangGraph như một **Builder**: hàm
`build_agent_graph()` tạo `builder = StateGraph(AgentState)`, gọi liên tiếp
`add_node()`, `add_edge()`, `add_conditional_edges()` để tích lũy cấu hình, rồi
`builder.compile(...)` để **validate và đóng băng** thành product chạy được.

File thật đã mở kiểm chứng:
- `graph/runtime.py:31-66` — hàm `build_agent_graph()`.
- `graph/runtime.py:27-28` — hàm `_route()` đọc nhánh từ state.
- `graph/runtime.py:8` — import `END, START, StateGraph`.
- `graph/__init__.py:1-4` — export `build_agent_graph` như public API.

---

## 2. Trích đoạn code thật

`graph/runtime.py:38-66`:

```python
builder = StateGraph(AgentState)
builder.add_node("guard", partial(guard_node, session=session))
builder.add_node("agent", partial(agent_node, session=session))
builder.add_node("tool", partial(tool_node, session=session))
builder.add_node(
    "delegate",
    partial(delegation_node, session=session, delegation_service=delegation_service),
)
builder.add_node("finish", partial(finish_node, session=session))
builder.add_node("fail", partial(fail_node, session=session))

builder.add_edge(START, "guard")
builder.add_conditional_edges("guard", _route, {"agent": "agent", "fail": "fail"})
builder.add_conditional_edges(
    "agent",
    _route,
    {"tool": "tool", "delegate": "delegate", "finish": "finish", "guard": "guard", "fail": "fail"},
)
builder.add_conditional_edges("tool", _route, {"guard": "guard", "fail": "fail"})
builder.add_conditional_edges("delegate", _route, {"guard": "guard", "fail": "fail"})
builder.add_conditional_edges("finish", _route, {"guard": "guard", "end": END})
builder.add_edge("fail", END)
return builder.compile(checkpointer=checkpointer, name="core-agent")
```

---

## 3. Ánh xạ vai trò pattern <-> code thật

| Vai trò Builder | Thành phần trong hex_agent | Vị trí |
|---|---|---|
| Builder (stateful) | `StateGraph(AgentState)` instance `builder` | `graph/runtime.py:38` |
| Bước build | `add_node()`, `add_edge()`, `add_conditional_edges()` | `graph/runtime.py:39-65` |
| Finalization (validate + đóng băng) | `builder.compile(checkpointer=..., name=...)` | `graph/runtime.py:66` |
| Product (immutable) | compiled LangGraph trả về | giá trị return của `:66` |
| Biểu diễn (representation) tách rời | `AgentState` (TypedDict state đi qua graph) | `graph/state.py` |
| Hàm định tuyến | `_route(state)` | `graph/runtime.py:27-28` |
| Client / public API | `build_agent_graph` được export | `graph/__init__.py:1-4` |

Điểm cốt lõi: **construction (cách lắp graph) tách khỏi representation
(AgentState đi qua graph)**. Cùng builder có thể dựng nhiều biến thể graph (xem
Case 02) mà không đụng tới định nghĩa state.

---

## 4. Bản rút gọn chạy được

File: [`langgraph_agent_graph.py`](./langgraph_agent_graph.py) — chạy
`python3 langgraph_agent_graph.py`.

**Mô phỏng đúng vai trò pattern:**
- `GraphBuilder` thay `StateGraph`: giữ state đang-build, có `add_node`,
  `add_edge`, `add_conditional_edges` (mỗi cái trả `self` để chaining), và
  `compile()` validate rồi trả product.
- `CompiledGraph` (frozen dataclass) thay compiled LangGraph: **immutable**,
  có `.run()` đi qua các node.
- `build_agent_graph()` distill nguyên trình tự wire của `runtime.py:31-66`
  (lược bớt node `delegate` cho gọn — vai trò pattern không đổi).

**Lược bỏ (thay bằng fake stdlib):**
- LangGraph thật -> builder + compiled graph tự cài bằng dict.
- LLM / kernel / session / `partial(..., session=...)` -> node là hàm thuần xử
  lý dict, không gọi mạng/DB/LLM.
- `AgentState` (TypedDict lớn) -> `dict` đơn giản.

**Các điểm pattern được chứng minh bằng `assert`:**
- Product immutable: gán `graph.name` -> `FrozenInstanceError`.
- Builder đã compile -> không cho `add_node` thêm (mục [4]).
- `compile()` fail-fast khi cạnh trỏ tới đích không tồn tại (mục [5]).
- Đối chứng: dựng graph bằng tay, quên cạnh ra -> sập **lúc chạy** thay vì bị
  bắt ở `compile()` (mục [6]).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Thêm một lớp gián tiếp.** Với graph 2-3 node cố định, dựng dict trực tiếp đơn
  giản hơn — Builder chỉ đáng giá khi có nhiều node, nhiều cạnh điều kiện, và cần
  validate cross-component.
- **Trong Python thuần, nhiều khi `@dataclass` + `__post_init__` đã đủ.** Builder
  toả sáng khi quá trình lắp ráp có **trình tự/nhánh** và **nhiều biến thể** —
  đúng tình huống của graph điều phối, nhưng quá tay cho object phẳng.
- **Builder của LangGraph khá nặng** (mang theo cả runtime). Không nên dựng lại
  graph trong vòng lặp nóng nếu cấu hình không đổi — cache lại product.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `compile()` (chứ không phải mỗi lần `add_edge`) là nơi đặt toàn bộ
   validation cross-component? Lợi ích của việc dồn validate về một chỗ là gì?
2. Product (`CompiledGraph`) là `frozen`. Điều gì sẽ hỏng về mặt invariant nếu ta
   cho phép sửa node/cạnh sau khi đã compile?
3. Trong code thật, `add_node("agent", partial(agent_node, session=session))` —
   tại sao builder cần `partial` ở đây, và việc đó liên quan gì tới việc "tách
   construction khỏi representation"?
