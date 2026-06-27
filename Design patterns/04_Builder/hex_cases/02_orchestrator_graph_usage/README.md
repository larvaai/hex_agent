# Case 02 — Builder + Director: nhiều biến thể graph trong vòng điều phối

> Builder (Creational) trong hex_agent ở mức ứng dụng: hàm `run()`/`resume()`
> đóng vai **Director**, gọi **cùng một Builder** (`build_agent_graph`) với cấu
> hình khác nhau để tạo **nhiều biến thể product** (graph có/không checkpoint).

---

## 1. Bối cảnh trong hex_agent

Vòng điều phối ở `orchestrator/loop.py` cần chạy agent trong hai chế độ:

- **Không checkpoint** (`checkpoint=False`): nhanh, không lưu state, không
  resume được. Dùng cho run dùng-một-lần.
- **Có checkpoint** (`checkpoint=True`, mặc định): dùng `open_checkpointer(rid)`
  mở một saver (SQLite), graph lưu state sau mỗi node -> **resume được** khi gián
  đoạn.

Điểm hay: cả hai chế độ dùng **chung một builder** `build_agent_graph()`. Khác
biệt chỉ là **truyền hay không truyền `checkpointer`**. Hàm `run()` và `resume()`
chính là **Director** — chúng đóng gói "công thức" dựng graph cho từng tình
huống, còn client gọi `run()`/`resume()` không cần biết wiring bên trong.

File thật đã mở kiểm chứng:
- `orchestrator/loop.py:130-147` — `run()`: nhánh `if not checkpoint` dựng graph
  không saver (`:131-134`), nhánh `with open_checkpointer(...)` dựng graph có
  saver (`:139-144`).
- `orchestrator/loop.py:246-273` — `resume()`: đọc checkpoint rồi dựng lại graph
  bền bỉ bằng cùng builder (`build_agent_graph(...)` tại `:255-259`).
- `graph/runtime.py:31-66` — `build_agent_graph` (Builder dùng chung).
- `adapters/agents/langgraph_agent.py:45-49` — cùng builder, biến thể dùng
  `InMemorySaver` cho child agent.

---

## 2. Trích đoạn code thật

`orchestrator/loop.py:130-147`:

```python
if not checkpoint:
    graph = build_agent_graph(
        session=active_session,
        delegation_service=delegation_service,
    )
    state = _stream(graph, initial, config=config, projection=False)
    _sync_budget(active_budget, state)
    return _outcome(state)

with open_checkpointer(rid) as saver:
    graph = build_agent_graph(
        session=active_session,
        checkpointer=saver,                 # <- biến thể "bền bỉ"
        delegation_service=delegation_service,
    )
    state = _stream(graph, initial, config=config, projection=True)
    _sync_budget(active_budget, state)
    return _outcome(state)
```

`orchestrator/loop.py:255-259` (trong `resume()`):

```python
graph = build_agent_graph(
    session=session,
    checkpointer=saver,
    delegation_service=delegation_service,
)
```

---

## 3. Ánh xạ vai trò pattern <-> code thật

| Vai trò Builder/Director | Thành phần trong hex_agent | Vị trí |
|---|---|---|
| Director | `run()` và `resume()` | `loop.py:93-147`, `:217-273` |
| Builder | `build_agent_graph(...)` | `loop.py:131`, `:140`, `:255` |
| Biến thể product A (simple) | graph không `checkpointer` | `loop.py:131-134` |
| Biến thể product B (resilient) | graph có `checkpointer=saver` | `loop.py:139-144` |
| Hạ tầng product B | `open_checkpointer(rid)` (SQLite saver) | `loop.py:139`, `orchestrator/checkpoint.py` |
| Biến thể product C (child) | graph có `InMemorySaver` | `adapters/agents/langgraph_agent.py:45-49` |
| Client code | caller của `run()`/`resume()` | ngoài `loop.py` |

Cùng một Builder, **cờ runtime quyết định product nào được sinh ra** — đặc trưng
kinh điển của Builder kết hợp Director.

---

## 4. Bản rút gọn chạy được

File: [`orchestrator_graph_usage.py`](./orchestrator_graph_usage.py) — chạy
`python3 orchestrator_graph_usage.py`.

**Mô phỏng đúng vai trò pattern:**
- `build_agent_graph(checkpointer=None | Saver)` là Builder: cùng quy trình, cờ
  `checkpointer` rẽ thành hai biến thể `CompiledGraph` (`core-agent` vs
  `core-agent+ckpt`).
- `run()` / `resume()` là Director: `run(checkpoint=False)` -> biến thể simple;
  `run(checkpoint=True)` và `resume()` -> biến thể resilient.
- `CompiledGraph` (frozen) lưu checkpoint sau mỗi bước khi có saver -> minh họa
  vì sao chỉ biến thể bền bỉ mới resume được.

**Lược bỏ (thay bằng fake stdlib):**
- `open_checkpointer` + SQLite trên đĩa -> `InMemorySaver` (dict trong RAM).
- LangGraph + `_stream` + LLM + session -> `step_fn` xử lý plan đơn giản.
- `Budget`, `_sync_budget`, `_outcome` -> rút về `steps`/`status`/`final`.

**Các điểm pattern được chứng minh bằng `assert`:**
- Cùng builder tạo hai product cùng kiểu nhưng khác cấu hình (mục [3]).
- Biến thể bền bỉ lưu checkpoint -> `resume()` chạy tiếp tới hoàn tất (mục [4-5]).
- Đối chứng: biến thể simple không lưu state -> `resume()` ném
  `FileNotFoundError` (mục [6]) — đúng cái giá của tốc độ.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Dựng lại graph mỗi lần `run()`/`resume()` có chi phí.** Nếu cấu hình cố định
  và gọi rất nhiều, cân nhắc cache product thay vì build lại.
- **Director thêm một lớp.** Khi chỉ có đúng một cách dựng graph, gọi builder
  trực tiếp đủ rồi — Director chỉ đáng giá khi có **vài preset** (simple /
  resilient / child) cần đóng gói.
- **Biến thể nở ra theo cờ.** Nếu số cờ tăng (checkpoint × delegation × model ×
  ...), tổ hợp biến thể có thể bùng nổ; lúc đó cân nhắc tách cấu hình thành một
  object config rõ ràng thay vì nhiều tham số rời.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao việc "đưa hay không đưa `checkpointer`" lại đủ để tạo ra hai product
   hành vi khác hẳn nhau, mà không cần hai hàm builder riêng?
2. `resume()` đọc checkpoint rồi gọi lại `build_agent_graph(checkpointer=saver)`.
   Nếu builder lúc resume khác builder lúc run (ví dụ thiếu một node), điều gì sẽ
   hỏng? Đây là lý do vì sao "cùng một builder" quan trọng.
3. So với việc nhồi cả checkpointing vào trong định nghĩa graph, việc để
   Director quyết định cấu hình giúp client (caller của `run`) dễ dùng hơn như
   thế nào?
