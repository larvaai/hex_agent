# Case 02 — Graph Node Orchestration: pipeline cố định, mỗi node một handler

> Template Method ở **scale kiến trúc**. Khung điều phối (thứ tự node) cố định và
> được engine *ép*; mỗi node là một hook cùng hợp đồng `state -> {..., "route"}`.

---

## 1. Bối cảnh trong hex_agent

`graph/` là lõi điều phối một phiên agent. Một lượt chạy đi qua một **pipeline cố
định**: kiểm tra ngân sách (guard) → gọi LLM lấy một action (agent) → tuỳ action mà
chạy tool / uỷ thác / kết thúc → quay lại guard → ... cho tới khi finish hoặc fail.

Vấn đề thật: làm sao **bảo đảm thứ tự** này không bao giờ bị phá — ví dụ không bao
giờ chạy hai tool liên tiếp mà *quên chen `guard`* giữa chúng (nếu quên, budget không
được kiểm tra → loop có thể chạy vượt quota). Đồng thời mỗi node lại có **logic rất
khác nhau** (guard so sánh số, agent gọi LLM + parse, tool gọi kernel, finish chạy
cổng hoàn thành).

hex_agent giải bằng `build_agent_graph()`: nó **không** viết một vòng `while` thủ
công. Nó **khai báo** các node + các cạnh có điều kiện cho `StateGraph` của LangGraph,
rồi `compile()`. Engine giữ thứ tự; mỗi node chỉ trả về một `dict` update có khoá
`route`, và engine tra bảng cạnh để chọn node kế. Node **không bao giờ** tự gọi node
khác — đúng Hollywood principle: "Don't call us, we'll call you".

File thật đã mở kiểm chứng:
- `graph/runtime.py:31-66` — `build_agent_graph()` dựng khung + bảng cạnh; `_route`
  ở `runtime.py:27-28`.
- `graph/nodes.py:20-37` — `_restore_session` / `_emit` (concrete operations dùng chung).
- `graph/nodes.py:40-48` — `guard_node`.
- `graph/nodes.py:51-103` — `agent_node`.
- `graph/nodes.py:106-138` — `tool_node`.
- `graph/nodes.py:202-240` — `finish_node`.
- `graph/nodes.py:243-255` — `fail_node`.

---

## 2. Trích đoạn code thật

Khung cố định — `graph/runtime.py:38-66` (rút gọn):

```python
builder = StateGraph(AgentState)
builder.add_node("guard", partial(guard_node, session=session))
builder.add_node("agent", partial(agent_node, session=session))
builder.add_node("tool", partial(tool_node, session=session))
builder.add_node("delegate", partial(delegation_node, session=session, delegation_service=delegation_service))
builder.add_node("finish", partial(finish_node, session=session))
builder.add_node("fail", partial(fail_node, session=session))

builder.add_edge(START, "guard")
builder.add_conditional_edges("guard", _route, {"agent": "agent", "fail": "fail"})
builder.add_conditional_edges("agent", _route,
    {"tool": "tool", "delegate": "delegate", "finish": "finish", "guard": "guard", "fail": "fail"})
builder.add_conditional_edges("tool", _route, {"guard": "guard", "fail": "fail"})
builder.add_conditional_edges("delegate", _route, {"guard": "guard", "fail": "fail"})
builder.add_conditional_edges("finish", _route, {"guard": "guard", "end": END})
builder.add_edge("fail", END)
return builder.compile(checkpointer=checkpointer, name="core-agent")
```

`_route` — `graph/runtime.py:27-28` (đọc route từ state, mặc định `fail`):

```python
def _route(state: AgentState) -> str:
    return str(state.get("route") or "fail")
```

Mọi node theo cùng mẫu: restore → xử lý chuyên biệt → emit → return update có
`route`. Ví dụ `guard_node` — `graph/nodes.py:40-48`:

```python
def guard_node(state: AgentState, *, session: KernelSession) -> dict[str, Any]:
    _restore_session(state, session)                     # bước chung
    budget = budget_from_state(state)
    if budget.steps >= budget.max_steps:                 # xử lý chuyên biệt
        error = "step budget exceeded"
        _emit(session, "graph.budget_blocked", state, reason=error)
        return {"route": "fail", "error": error, "session_state": _session_snapshot(session)}
    return {"route": "agent", "session_state": _session_snapshot(session)}
```

`agent_node` set route theo verb của action — `graph/nodes.py:93-103`:

```python
if verb == "tool":
    update["route"] = "tool"
elif verb == "delegate":
    update["route"] = "delegate"
elif verb == "final":
    update["route"] = "finish"
else:
    messages.append({"role": "user", "content": "Unknown 'action'. Use 'tool' or 'final'."})
    update["route"] = "guard"
return update
```

`tool_node` luôn quay về guard sau khi chạy — `graph/nodes.py:133-138`:

```python
return {
    "messages": messages,
    "budget": budget_to_dict(budget),
    "route": "guard",
    "session_state": _session_snapshot(session),
}
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Template Method | Thành phần trong hex_agent |
|---|---|
| Template method factory (dựng skeleton) | `build_agent_graph()` — `runtime.py:31-66` |
| Skeleton enforcer (ép thứ tự) | `StateGraph.compile()` + bảng `add_conditional_edges` |
| Bộ định tuyến giữ thứ tự | `_route()` — `runtime.py:27-28` |
| Hook handlers (cùng hợp đồng) | `guard_node`/`agent_node`/`tool_node`/`delegation_node`/`finish_node`/`fail_node` — `nodes.py:40-255` |
| Shared concrete operations | `_restore_session`, `_session_snapshot`, `_emit`, `budget_from_state` — `nodes.py:20-37` |
| Hợp đồng hook | `node(state) -> dict update` (luôn có khoá `route`) |

Điểm cốt lõi đúng văn phong bài gốc (mục 2.3 — bất biến): **thứ tự gọi node không
thay đổi**; handler thay đổi *logic trong một bước*, không reorder khung. Một node
*không* được tự gọi node kế (nếu nó làm vậy là phá pattern, giống "hook gọi hook khác"
ở Anti-pattern #4). Nó chỉ khai báo `route`, engine mới gọi.

---

## 4. Bản rút gọn chạy được

File: [`graph_node_pipeline.py`](./graph_node_pipeline.py) — chỉ dùng stdlib.

Nó mô phỏng:
- `build_agent_graph()` với đúng các node + bảng cạnh (đã bỏ `delegate` cho gọn).
- Năm node hook (bản thật có sáu; đã bỏ delegate cho gọn) cùng hợp đồng `state -> {..., "route"}`.
- `_restore_budget` / `_emit` / `_route` là concrete operations dùng chung.

Nó lược bỏ / thay thế:
- **LangGraph `StateGraph`** → `MiniStateGraph` tự viết (~40 dòng) làm "skeleton
  enforcer": add_node / add_conditional_edges / compile / stream.
- **`KernelSession` + LLM + kernel.execute_tool** → `FakeSession` với một *script*
  action tất định và `run_tool` trả envelope giả.
- **Checkpointer / projection / parse ladder / delegation** → bỏ.

Các điểm chứng minh (assert) trong demo:
- Run thành công có trace `guard -> agent -> tool -> guard -> agent -> finish` (mục A);
  bất biến: trace luôn **bắt đầu ở guard**, và **sau mỗi `tool` luôn là `guard`**.
- Budget cạn → guard route sang `fail`, trace kết thúc ở `fail` (mục B).
- Mọi node trả update **có khoá `route`** (mục C — bất biến hợp đồng).
- Đối chứng `run_loop_NO_PATTERN`: vòng `while` thủ công vẫn cho cùng output, nhưng
  thứ tự nằm rải trong `if/elif` và **không có ai bảo đảm** guard chen giữa hai tool
  call — đúng loại bug "quên một bước" mà skeleton enforcer phòng được (mục E).

Chạy:

```bash
python3 graph_node_pipeline.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Fragile skeleton**: nếu thứ tự pipeline còn đang thay đổi mỗi sprint, việc cố
  định nó trong một factory + bảng cạnh sẽ phải sửa liên tục. Template Method (và biến
  thể graph này) chỉ "shine" khi khung *đã prove stable* — đúng cảnh báo mục 1.5/kết
  luận bài gốc.
- **Phụ thuộc engine**: đẩy việc ép thứ tự cho `StateGraph` nghĩa là buộc vào một
  framework. Đổi engine = viết lại lớp dựng khung. Đây là cái giá của "framework có
  skeleton, bạn cắm hook".
- **Khi flow quá tự do** (node có thể nhảy bất kỳ đâu, không có thứ tự ổn định) → đây
  không còn là pipeline cố định; dùng máy trạng thái tổng quát / Chain thay vì khung
  topo cố định.
- Đừng nhồi quá nhiều node nhỏ chỉ để "đẹp khung": mỗi node là một điểm phải bảo trì
  hợp đồng `route`. Quá nhiều hook là dấu hiệu sai pattern (Anti-pattern #3 bài gốc).

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `tool_node` luôn trả `route="guard"` thay vì trả `route="agent"` để tiết
   kiệm một bước? Bất biến nào (về budget) sẽ vỡ nếu nó nhảy thẳng sang agent?
2. Trong bản rút gọn, `CompiledGraph.stream` ném `KeyError` nếu một node trả `route`
   không có trong bảng cạnh. Điều này tương ứng với tính chất nào của "skeleton
   enforcer" so với vòng `while` thủ công trong `run_loop_NO_PATTERN`?
3. Nếu muốn thêm node `delegate` (như bản thật), bạn phải sửa ở đâu trong
   `build_agent_graph` và phải giữ nguyên hợp đồng gì ở handler mới?
