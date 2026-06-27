# CATALOG — Mọi occurrence của Strategy Pattern trong hex_agent

> Vét cạn các điểm Strategy (Behavioral) xuất hiện trong codebase. Mọi `path:line` đã được mở
> file kiểm chứng. Path là tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent`.
> Ba dòng **đậm** là flagship, có case con riêng trong thư mục này.

| path:line | Mô tả (vai trò Strategy) | Độ rõ |
|---|---|---|
| **`core/middleware.py:11-22`** | `ToolMiddleware` Protocol — Strategy interface cho mọi guard quanh `execute_tool`. → **Case 01** | Rất cao |
| **`core/kernel.py:49-73`** | `_wrap()` — composition: bind 1 middleware quanh `nxt`, xử lý fail-open (advisory) vs fail-closed (blocking). → **Case 01** | Rất cao |
| **`core/kernel.py:100-104`** | `AgentKernel.use()` — inject một strategy vào pipeline (đăng ký = outer→inner). → **Case 01** | Cao |
| **`core/kernel.py:192-194`** | Chain composition: `for mw in reversed(self._middlewares): handler = _wrap(mw, handler)`. → **Case 01** | Cao |
| **`core/bootstrap.py:28-53`** | `_install_middleware()` — chọn/lắp strategy theo `config['middleware']`, thứ tự timing→policy→retry→condense. → **Case 01** | Cao |
| **`middleware/retry.py:23-33`** | `Retry` ConcreteStrategy — gọi lại `nxt` khi non-ok; bỏ qua effect non-idempotent (`retry.py:14-20`). → **Case 01** | Rất cao |
| **`middleware/policy.py:9-21`** | `PolicyGate` ConcreteStrategy — chặn theo deny-set, short-circuit không gọi `nxt`. → **Case 01** | Rất cao |
| **`middleware/budget.py:10-23`** | `BudgetGuard` ConcreteStrategy — đếm cùng-tool, chặn khi vượt ngân sách (state per-run). → **Case 01** | Cao |
| `middleware/timing.py:10-26` | `TimingLog` ConcreteStrategy fail-open (`fail_open = True`) — telemetry advisory. → Case 01 | Cao |
| `middleware/condense.py:11-30` | `CondenseResult` ConcreteStrategy fail-open — cắt gọn kết quả lớn trước khi feed lại model. | Trung bình |
| **`rag/ports.py:24-36`** | `EmbedderPort` + `VectorStorePort` Protocol — hai Strategy interface của RAG. → **Case 02** | Rất cao |
| **`rag/embedders.py:33-46`** | `FakeEmbedder` ConcreteStrategy (offline, hash bag-of-words). → **Case 02** | Rất cao |
| **`rag/embedders.py:49-60`** | `FastEmbedEmbedder` ConcreteStrategy (production, lazy-import fastembed). → **Case 02** | Cao |
| **`rag/stores.py:24-56`** | `InMemoryVectorStore` ConcreteStrategy (cosine trong tiến trình). → **Case 02** | Rất cao |
| **`rag/stores_qdrant.py:32-49`** | `QdrantVectorStore` ConcreteStrategy (production, lazy-import qdrant_client). → **Case 02** | Cao |
| **`rag/feature.py:27-42`** | `build_service()` — Factory chọn/inject strategy theo `config['backend']`. → **Case 02** | Cao |
| `rag/service.py:15-39` | `RagService` — Context delegate cho embedder/store strategy; health-gate. → Case 02 | Cao |
| `rag/feature.py:109-121` | `install()` — RAG feature inject service strategy vào kernel. | Cao |
| **`decompose_agent/reduce.py:44-77`** | `run_reduce()` — Context dispatch theo `node.reduce_op` (pick/concat/merge_json/manifest). → **Case 03** | Rất cao |
| **`decompose_agent/node.py:114`** | `Node.reduce_op` — selector của strategy gộp; `inputs` (`node.py:115`) là nguồn. → **Case 03** | Cao |
| **`decompose_agent/node.py:28`** | `REDUCE_OPS = frozenset({...})` — tập strategy hợp lệ. → **Case 03** | Cao |
| **`decompose_agent/node.py:132-133`** | Bất biến: reduce node phải có `reduce_op ∈ REDUCE_OPS` (ép tại construction). → **Case 03** | Cao |
| `decompose_agent/reduce.py:35-41` | `_deep_merge()` — helper cho strategy `merge_json`. → Case 03 | Cao |
| `decompose_agent/tests/test_reduce.py:34-55` | Test mỗi reduce strategy độc lập (pick/concat/merge/manifest). → Case 03 | Cao |
| `core/registry.py:43-112` | `CapabilityRegistry` — `register_tool`/`set_fallback_tool_executor`/`resolve_tool`: tool strategy cắm được + fallback. | Cao |
| `core/ports.py:19-45` | `ToolPort`, `DelegationPort` Protocol — Strategy interface cho tool/delegation executor. | Cao |
| `features/loader.py:10-25` | `install_configured_features()` — chọn/cài feature theo config (factory động qua importlib). | Cao |
| `features/llm_chat.py:35-37` | `install()` — inject `LLMChatTool` strategy vào kernel. | Trung bình |
| `llm/adapter.py:72-119` | `call_llm()` — chọn chiến lược retry/backoff (transient/response-format, exponential backoff). | Cao |
| `supervisor/evidence.py:26-40` | `evidence_type_of()` — chọn chiến lược phân loại evidence theo `kind`. | Trung bình |
| `supervisor/evidence.py:43-57` | `_overall_verdict()` — các chiến lược verdict (pending/passed_with_risk/passed). | Trung bình |
| `drag_from_zero/dragzero/llm.py:12-39` | `LLM` Protocol + `FakeLLM` + `by_role()` — chọn responder strategy theo role. | Trung bình |
| `drag_from_zero/dragzero/eval/scorers.py:15-100` | Scorer factory — mỗi factory trả một callable scorer strategy cho eval. | Trung bình |
| `core/bootstrap.py:56-71` | `build_kernel()`/`create_kernel()` — orchestrate cài đặt strategy (feature + middleware). | Trung bình |

---

## Quan sát tổng hợp

- **Hai biểu hiện chủ đạo của Strategy trong hex_agent:**
  (a) *Protocol-based* (`ToolMiddleware`, `EmbedderPort`/`VectorStorePort`, `ToolPort`,
  `DelegationPort`, `LLM`) — interface mỏng, duck typing, chọn bằng factory/config;
  (b) *selector dispatch* (`reduce_op`, retry-mode trong `call_llm`, verdict trong evidence) —
  một phép toán nhiều cài đặt, chọn theo một khoá khai báo.
- **Factory luôn đi kèm Strategy** (đúng bảng "Factory Method" cuối `21_Strategy.md`):
  `build_service`, `_install_middleware`, `install_configured_features`, `build_kernel`.
- **Tư thế fail-open/fail-closed** (Case 01) là một biến thể tinh tế: strategy advisory tự khai
  báo `fail_open = True` để kernel xử lý lỗi khác đi — declarative, không if/elif trong Context.
- **`if/elif` vẫn xuất hiện hợp lệ** (`run_reduce`, `call_llm` retry) khi số strategy ít/ổn định —
  trung thực với cảnh báo "đừng strategy explosion" của bài gốc.
