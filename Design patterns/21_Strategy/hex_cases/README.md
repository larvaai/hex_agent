# Strategy Pattern (Behavioral) trong hex_agent — Bộ case thực chiến

> Phụ lục thực hành cho [`21_Strategy.md`](../21_Strategy.md). Mỗi case là một bằng chứng
> rằng Strategy KHÔNG phải lý thuyết: nó là *xương sống của configurable systems* và xuất hiện
> ở nhiều tầng của hex_agent. Mỗi case có một bản distill **chạy được bằng stdlib thuần** (Python
> 3.10+), trích đúng `file:line` của code thật, và một đối chứng "khi không dùng pattern thì hỏng".

---

## Strategy hiện diện ở đâu trong hex_agent

`21_Strategy.md` định nghĩa Strategy = đóng gói *một họ thuật toán* (cùng giải một bài toán)
thành các đơn vị riêng để Context đổi algorithm runtime mà không sửa Context. hex_agent dùng tư
tưởng này ở **năm chiều** khác nhau:

1. **Middleware Pipeline** — nhiều middleware (`Retry`, `PolicyGate`, `TimingLog`,
   `CondenseResult`, `BudgetGuard`) cùng thoả Protocol `ToolMiddleware`, được compose thành một
   chuỗi quanh chokepoint `execute_tool` qua `kernel.use()`. → **Case 01**.
2. **RAG Backend Abstraction** — RAG chọn giữa `FakeEmbedder`/`InMemoryVectorStore` (offline) và
   `FastEmbedEmbedder`/`QdrantVectorStore` (production), tất cả thoả `EmbedderPort`/`VectorStorePort`
   Protocol, chọn bằng config. → **Case 02**.
3. **Reduce Operations** — `run_reduce()` dispatch sang các thuật toán gộp khác nhau (pick, concat,
   merge_json, manifest) theo `node.reduce_op`. → **Case 03**.
4. **Feature Installation** — feature được nạp động từ config qua một registry/loader, cho phép
   hoán đổi cài đặt tool. → xem CATALOG (`features/loader.py`).
5. **Tool Execution Registry** — tool resolver thoả một interface chung và được inject qua cấu
   hình, hỗ trợ fallback và suy biến nhẹ nhàng. → xem CATALOG (`core/registry.py`, `core/ports.py`).

Điểm chung xuyên suốt: **interface mỏng (Protocol) + nhiều cài đặt có trade-off rõ + chọn bằng
config/factory + Context không biết mình đang dùng cài đặt nào.** Đó đúng là dual-route fear của
LeDoux trong `21_Strategy.md`: cùng câu hỏi, nhiều thuật toán, chọn theo ngữ cảnh.

---

## Các case con (flagship)

| # | Case | Dạng Strategy | Điểm nhấn |
|---|---|---|---|
| [01](./01_middleware_chain/) | **Middleware Pipeline** | Strategy + Pipeline/Decorator | Compose nhiều strategy quanh 1 chokepoint; fail-open vs fail-closed; Retry không double-apply effect |
| [02](./02_rag_backend_selection/) | **RAG Backend Selection** | Strategy "sách giáo khoa" | Cùng Context (`RagService`), đổi embed + store qua Protocol; chọn bằng config; trade-off latency/persistence |
| [03](./03_reduce_operations/) | **Reduce Aggregation** | Strategy dispatch theo selector | `reduce_op` khai báo trên Node chọn 1 trong 4 cách gộp; bất biến ép tại construction |

Mỗi folder có `README.md` (6 mục: bối cảnh, trích code thật, bảng ánh xạ, bản rút gọn, cái giá,
câu hỏi tự kiểm tra) và một file `.py` self-contained chạy `python3 <name>.py` → exit 0.

Toàn bộ occurrence (kể cả ngoài flagship) được liệt kê trong [`CATALOG.md`](./CATALOG.md).

---

## Chạy thử

```bash
python3 01_middleware_chain/middleware_chain.py
python3 02_rag_backend_selection/rag_backend_selection.py
python3 03_reduce_operations/reduce_operations.py
```

Cả ba in narration tiếng Việt từng bước và kết thúc bằng "Mọi assert PASS". Không cần cài gì
ngoài Python chuẩn — các file **không** import hex_agent hay thư viện bên thứ ba.

---

## Nối lại với bài học gốc

- **Case 01** minh hoạ ô "Strategy vs Decorator" và "Pipeline of strategies" (bảng biến thể
  mục 2.4 của `21_Strategy.md`): strategy ở đây *stack* chứ không *chọn 1*.
- **Case 02** là minh hoạ thuần nhất cho hình Context + Strategy interface + N ConcreteStrategy
  (mục 2.1), kèm Factory chọn strategy theo config (so sánh với Factory Method ở bảng cuối bài).
- **Case 03** minh hoạ "Strategy registry" và nhắc lại cảnh báo "khi if/elif là đủ" (mục 1.4) —
  một lời nhắc trung thực rằng không phải lúc nào cũng cần class formal.
