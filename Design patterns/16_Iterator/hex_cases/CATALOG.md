# CATALOG — Mọi nơi Iterator xuất hiện trong hex_agent

Bảng vét cạn (exhaustive) các occurrence của Iterator pattern — cả tường minh lẫn ẩn. Cột **độ rõ** đánh giá mức độ "đây đúng là Iterator pattern" so với "chỉ là một vòng lặp tuần tự thường".

Ba dòng **★ flagship** được đào sâu thành case riêng trong các thư mục `01_`, `02_`, `03_`.

| path:line | Mô tả | Độ rõ |
|-----------|-------|-------|
| ★ `decompose_agent/tree.py:43-51` | `Tree.next_node()` trả node `pending` kế tiếp theo `(depth, order)` với mọi `depends_on` đã `done`, **không lộ cấu trúc tree**. Cursor thật sự của DAG. → case **01** | cao |
| ★ `decompose_agent/solve.py:262-293` | Vòng `solve()`: `while (node := tree.next_node()) is not None`. Client kéo cursor đến khi `None`, không cần biết logic topo-sort. → case **01** | cao |
| ★ `drag_from_zero/dragzero/events.py:87-88` | `EventLog.__iter__()` trả `iter(self._events)` → `for event in log` chạy được. Iterator protocol native. → case **02** | cao |
| ★ `drag_from_zero/dragzero/ledger.py:47-67` | `Ledger.read()` duyệt từng dòng JSONL (dòng 53), parse mỗi dòng thành `Event`, **bỏ qua dòng hỏng** (fail-soft). External iterator trên storage. → case **02** | cao |
| ★ `harness/scripts/telemetry_paths.py:54-84` | `iter_records_in_window()` là generator `yield` record khớp time-window. O(1) bộ nhớ dù file lớn (comment dòng 65). Stream line-by-line + lọc. → case **03** | cao |
| `orchestrator/checkpoint.py:35-40` | `open_checkpointer()` context manager khai báo trả `Iterator[SqliteSaver]`. Dùng iterator protocol ẩn qua type hint (`@contextmanager` + `yield`). | cao |
| `orchestrator/loop.py:69-90` | `_stream()` duyệt `graph.stream(graph_input, config, ...)` — yield ra `AgentState` từng giá trị. External iteration trên state graph (lazy). | cao |
| `decompose_agent/journal.py:32-50` | `Journal.records(node_id)` duyệt `path.read_text().splitlines()` (dòng 37), parse mỗi dòng JSON, bỏ qua dòng hỏng. Trả `list` (không generator) — đơn giản hơn Iterator đầy đủ. | cao |
| `drag_from_zero/dragzero/events.py:78-85` | `EventLog.events()` trả `list[Event]`; `of_type()` / `types()` lọc bằng cách duyệt `self._events`. Accessor tiện lợi bọc quanh iterator. | trung bình |
| `decompose_agent/tree.py:28-29` | `Tree.children_of(node_id)` trả tuple child IDs. Dùng trong ngữ cảnh duyệt: `for c in tree.children_of(nid)` (solve.py). | trung bình |
| `decompose_agent/solve.py:90-104, 141-178` | `solve_leaf()` và `_decompose()` dùng `while`-loop với retry. Duyệt tuần tự có cursor cục bộ (attempts, rejections) — không phải iterator protocol nhưng là sequential traversal. | trung bình |
| `tools/fake_control_server.py:86-105` | `FakeControlPlane.stream()` duyệt pending events (dòng 94) yield ra SSE frames. External iterator đẩy frame vào HTTP response. | trung bình |
| `graph/runtime.py:78` (trong tests) | `for final_state in graph.stream(initial, config)`. `stream()` của LangGraph là interface Iterator trên state mutations. | trung bình |
| `supervisor/loop.py:154-199` | `_drive()` `while`-not-terminal điều phối task loop. Không phải Iterator đúng nghĩa — loop theo state machine (`decision.decision` branches). Sequential traversal kinh điển. | thấp |
| `control/emitter.py:48-60` | `EventEmitter` duyệt `self._sinks` (dòng 59) để fan-out event. Sinks dựng bằng `list(sinks)`. Duyệt đơn giản, không phải custom Iterator. | thấp |
| `decompose_agent/store.py:79-85` | `DecompCache._attach()` duyệt children (dòng 81: `enumerate`) để gắn node. Enumeration đơn giản, không phải cursor-based iterator. | thấp |

---

## Cách đọc cột "độ rõ"

- **cao** — Logic duyệt có giá trị riêng (lazy / ordered / filtered / topo / stream), hoặc dùng đúng iterator protocol của Python (`__iter__` / generator). Đây là Iterator pattern thực thụ.
- **trung bình** — Có dáng dấp duyệt-tuần-tự hoặc accessor bọc quanh iterator, nhưng nghiêng về tiện ích hơn là pattern đầy đủ.
- **thấp** — Chỉ là vòng lặp/`for` thường trên một list. Liệt kê để vét cạn, nhưng đừng nhầm với Iterator pattern (xem cảnh báo "Iterator không phải for-loop với extra steps" ở bài gốc, mục 1.5).
