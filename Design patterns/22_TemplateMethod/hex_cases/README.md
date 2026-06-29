# Template Method trong hex_agent — Case Studies

> Tài liệu dạy học đi kèm [Lesson 22 — Template Method](../22_TemplateMethod.md).
> Đây là phần "soi pattern trong code production thật" (`hex_agent`), distill từng chỗ
> xuất hiện thành ví dụ stdlib chạy được.

---

## Template Method là gì (nhắc lại một dòng)

**Base/khung định nghĩa _skeleton_ (thứ tự bước cố định) của một thuật toán; các bước
biến thiên được tách ra thành _hook_.** Skeleton không đổi, chi tiết bước thì thay đổi.
Tinh thần Hollywood: *"Don't call us, we'll call you"* — khung chủ động gọi hook.

---

## Pattern này xuất hiện thế nào trong hex_agent

hex_agent dùng Template Method ở **hai hình thái chính**, đáng chú ý là **không phải**
qua inheritance cổ điển mà qua các cơ chế Pythonic hơn (đúng tinh thần "favor
composition over inheritance" của bài gốc):

1. **Khung hợp đồng qua Protocol** — `Worker(Protocol)` định nghĩa hai bước cố định
   (`propose`, `decompose`); hai lớp (`ScriptedWorker` test double, `LocalLLMWorker`
   production) hiện thực khác hẳn nhau. Khung gọi (`solve_leaf`, `_decompose`) giữ
   thứ tự bước bất biến và chỉ gọi hai hook đó.

2. **Khung điều phối qua graph** — `build_agent_graph()` dựng một pipeline cố định
   (guard → agent → tool/delegate → finish → fail) và để `StateGraph` *ép* thứ tự;
   mỗi node là một hook cùng hợp đồng `state -> {..., "route"}`. Đây là Template
   Method ở scale kiến trúc.

Ngoài hai flagship, pattern còn lặp lại dày đặc ở **tầng middleware** (mỗi middleware
là `__call__(request, nxt)` với khung "trước → gọi `nxt` → sau"), ở các **vòng điều
phối** (`orchestrator/loop.py`, `supervisor/loop.py`, `dragzero/orchestrator.py`) và
ở **bộ tool** (`tools_fs.py`: nhiều tool cùng hợp đồng `run(args, sandbox)`). Xem
[CATALOG.md](./CATALOG.md) để vét cạn mọi occurrence từ bước discover.

---

## Các case con

| # | Case | Trọng tâm | Nguồn thật |
|---|------|-----------|------------|
| 01 | [Worker Protocol](./01_worker_protocol_system/) | Khung `propose`/`decompose` cố định, hai hiện thực (scripted vs LLM) qua Protocol | `decompose_agent/worker.py:182-301`, `decompose_agent/solve.py:80-180` |
| 02 | [Graph Node Pipeline](./02_graph_node_pipeline/) | Pipeline điều phối cố định; mỗi node một hook cùng hợp đồng `state->route` | `graph/runtime.py:31-66`, `graph/nodes.py:20-255` |

Mỗi thư mục case có:
- `README.md` — bài học 6 mục (bối cảnh thật → trích code thật → bảng ánh xạ vai trò →
  bản rút gọn → cái giá → câu hỏi).
- `<name>.py` — bản distill **chỉ dùng stdlib**, có `demo()`, có đối chứng "không dùng
  pattern thì hỏng/khó thế nào", có `assert` chứng minh bất biến.

---

## Chạy thử

```bash
python3 01_worker_protocol_system/worker_protocol_system.py
python3 02_graph_node_pipeline/graph_node_pipeline.py
```

Cả hai thoát code 0, in narration tiếng Việt từng bước.

---

## Hai hình thái Protocol vs graph — đọc kèm bài gốc

- Case 01 minh hoạ rõ ý mục **2.5 (Template Method vs Strategy)** và phần
  **Python-native**: hex_agent chọn structural typing (Protocol) thay cho ABC +
  `@abstractmethod`. Khung vẫn cố định, hook vẫn là điểm biến thiên — nhưng không có
  fragile base class.
- Case 02 minh hoạ ý **"plugin architecture của framework nào cũng là Template Method
  ở tầng kiến trúc"** (phần So sánh với pattern khác): framework (StateGraph) giữ
  skeleton, bạn cắm node-hook.
