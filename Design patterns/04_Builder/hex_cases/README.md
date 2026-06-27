# Builder Pattern trong hex_agent — Hex Cases

> **Builder (Creational): tách quá trình lắp ráp một object phức tạp khỏi biểu
> diễn của nó, để cùng một quy trình có thể tạo nhiều biến thể.**

Đây là bộ "case thực chiến" distill từ codebase thật `hex_agent`, đi kèm lesson
gốc [`../04_Builder.md`](../04_Builder.md). Mỗi case có một bài học (README) và
một file `.py` self-contained chạy được bằng thư viện chuẩn Python 3.14.

---

## Builder xuất hiện ở đâu trong hex_agent?

Builder trong hex_agent chủ yếu đến từ API `StateGraph` của LangGraph. Hàm
`build_agent_graph()` trong `graph/runtime.py` là ví dụ kinh điển: một object
builder (`StateGraph`) tích lũy node và cạnh qua các method
(`add_node`, `add_edge`, `add_conditional_edges`), rồi trả về product đã compile
qua `builder.compile()`.

Cách này **tách quá trình lắp ráp graph phức tạp khỏi biểu diễn `AgentState`**,
cho phép dựng nhiều biến thể graph điều phối bằng cùng một khung builder, đồng
thời giữ **tính bất biến (immutability)** của product cuối cùng.

Các đặc trưng Builder thể hiện ở đây:
- **Fluent / progressive method calls**: gọi tuần tự `add_node`, `add_edge`,
  `add_conditional_edges` để dựng dần.
- **Tách construction khỏi representation**: cách lắp graph tách khỏi state đi
  qua graph.
- **Validation tại finalization**: `.compile()` mới validate toàn graph.
- **Immutability sau build**: compiled graph không sửa được nữa.
- **Một builder, nhiều biến thể product**: có/không checkpointer (xem Case 02).

---

## Các case

| # | Case | Trọng tâm | File |
|---|---|---|---|
| 01 | [LangGraph StateGraph Builder](./01_langgraph_agent_graph/) | Builder dựng graph điều phối agent; validate tại `compile()`; product immutable. | [`langgraph_agent_graph.py`](./01_langgraph_agent_graph/langgraph_agent_graph.py) |
| 02 | [Builder usage trong vòng điều phối](./02_orchestrator_graph_usage/) | Director (`run`/`resume`) + cùng một Builder tạo nhiều biến thể (có/không checkpoint). | [`orchestrator_graph_usage.py`](./02_orchestrator_graph_usage/orchestrator_graph_usage.py) |

Bảng vét cạn mọi occurrence: xem [`CATALOG.md`](./CATALOG.md).

---

## Vai trò pattern (tổng hợp)

| Vai trò | Trong hex_agent |
|---|---|
| Builder | instance `StateGraph` (`graph/runtime.py:38`) |
| Bước build | `add_node()`, `add_edge()`, `add_conditional_edges()` |
| Finalization | `builder.compile()` (`graph/runtime.py:66`) -> graph immutable |
| Product | compiled LangGraph |
| Director | `run()` / `resume()` (`orchestrator/loop.py`) |
| Biến thể product | graph có vs không checkpointer |
| Client / public API | `build_agent_graph` export tại `graph/__init__.py:1-4` |

---

## Chạy thử

```bash
python3 01_langgraph_agent_graph/langgraph_agent_graph.py
python3 02_orchestrator_graph_usage/orchestrator_graph_usage.py
```

Cả hai thoát code 0, in narration từng bước bằng tiếng Việt, và có `assert`
chứng minh các bất biến của Builder (immutable product, validate fail-fast tại
compile, cùng builder ra nhiều biến thể).

---

## Khi nào nên / không nên dùng Builder

**Nên** khi: constructor có > 4 tham số (nhất là nhiều optional); phải dùng
setters sau `new` để hoàn thiện object; có nhiều invariant cross-field cần
validate; cùng quy trình cần dựng nhiều biến thể cấu trúc tương tự (đúng tình
huống graph điều phối nhiều chế độ của hex_agent).

**Không nên** khi: object phẳng, ít trường — trong Python `@dataclass` +
`__post_init__` thường gọn hơn; hoặc chỉ có đúng một cách lắp ráp cố định —
khi đó Builder/Director chỉ thêm lớp gián tiếp không cần thiết.
