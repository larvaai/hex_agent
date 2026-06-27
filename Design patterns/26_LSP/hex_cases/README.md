# LSP trong hex_agent — Bộ case thực chiến

> **Liskov Substitution Principle (LSP)** = bất kỳ subtype `S` nào cũng phải thay thế được cho
> supertype `T` mà **caller không cần biết** mình đang nói chuyện với `T` hay `S`. Nói cách khác:
> subtype tuân đúng *contract* (precondition / postcondition / invariant / exception / side-effect)
> của supertype. (Xem bài học gốc `../26_LSP.md`.)

Thư mục này distill các chỗ LSP xuất hiện **thật** trong codebase `hex_agent` thành các case
self-contained, chạy được bằng **chỉ thư viện chuẩn Python 3.14** (không import hex_agent, không lib bên thứ ba).

---

## LSP trong hex_agent là gì?

hex_agent là một kiến trúc **hexagonal (ports & adapters)**. Mỗi *port* là một `Protocol`
(thường `@runtime_checkable`) định nghĩa một **contract**; nhiều *adapter* khác nhau thỏa contract đó
mà không phá kỳ vọng của caller. Các adapter được **swap** cả trong test (biến thể Fake/Scripted) lẫn
production (adapter Real) — đúng tinh thần LSP: substitutable theo *hợp đồng hành vi*, không phải theo
"trông giống" hay "cùng cha mẹ phân loại".

Các port có ≥ 2 impl giữ contract (đã mở file kiểm chứng):
`ToolPort`, `ToolMiddleware`, `EmbedderPort`, `VectorStorePort`, `DelegationPort`,
`OrchestratorPort`, `BrokerPort`, `ChatLLM`.

Mẫu hình lặp lại:

```
   Caller (RagService / TaskLoop / Kernel)
       │ depend on
   Port (Protocol)  ← contract: pre/post/invariant/exception/side-effect
   ╱        ╲
  S₁         S₂   ← adapter; MỖI cái phải GIỮ contract.
  (offline)  (production)   Nếu một adapter làm yếu hợp đồng → caller buộc isinstance → OCP collapse.
```

Điểm tinh tế nhất trong hex_agent: **exception contract**. Nhiều port hứa "không raise lỗi hạ tầng" —
ví dụ `VectorStorePort.health()` nuốt lỗi server thành `{"ok": False}`, hay `DelegationPort.run()` báo
thất bại qua `outcome='failed'` thay vì throw. Nhờ vậy caller xử lý lỗi *giống hệt* cho mọi adapter.

---

## Các case con

| # | Case | Port (abstraction) | Hai subtype | Điểm LSP nổi bật |
|---|---|---|---|---|
| [01](./01_embedder_port_lsp/) | EmbedderPort | `rag/ports.py:24-28` | `FakeEmbedder` ↔ `FastEmbedEmbedder` | Postcondition cardinality `len(out)==len(texts)` |
| [02](./02_vector_store_port_lsp/) | VectorStorePort | `rag/ports.py:31-36` | `InMemoryVectorStore` ↔ `QdrantVectorStore` | `health()` KHÔNG raise; `search()` sort + cắt top_k |
| [03](./03_delegation_port_lsp/) | DelegationPort | `core/ports.py:32-45` | `LangGraphDelegationAgent` ↔ `ScriptedDelegationAgent` | Fail → `outcome='failed'`, không raise |
| [04](./04_orchestrator_broker_lsp/) | OrchestratorPort & BrokerPort | `supervisor/orchestrator.py:15-18`, `supervisor/broker.py:17-21` | `Scripted*` ↔ `LLM*` | Invariant `source_ids ⊆ slice` thực thi bằng code dù LLM hallucinate |

Mỗi case gồm:
- `README.md` — 6 mục: bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản rút gọn, cái giá, câu hỏi.
- `<name>.py` — bản distill chạy được, có `demo()`, narration tiếng Việt, đối chứng "không-pattern", và `assert`.

Xem [`CATALOG.md`](./CATALOG.md) để có bảng vét cạn MỌI occurrence LSP trong codebase.

---

## Chạy thử

```bash
python3 01_embedder_port_lsp/embedder_port_lsp.py
python3 02_vector_store_port_lsp/vector_store_port_lsp.py
python3 03_delegation_port_lsp/delegation_port_lsp.py
python3 04_orchestrator_broker_lsp/orchestrator_broker_lsp.py
```

Tất cả thoát code 0, in narration từng bước và kết thúc bằng "TẤT CẢ ASSERT PASS".

---

## Nhớ một câu

> LSP **không phải** "subclass kế thừa class cha". LSP là "subtype **hành xử** đúng như hợp đồng —
> caller không cần biết". Trong hex_agent, `@runtime_checkable` chỉ kiểm *cấu trúc* (có method/attr);
> còn LSP thật được giữ bằng **contract + Liskov contract test + guardrail trong code**.
