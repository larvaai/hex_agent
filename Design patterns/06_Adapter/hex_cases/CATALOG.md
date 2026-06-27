# CATALOG — Mọi lần xuất hiện của Adapter trong hex_agent

Bảng vét cạn các occurrence của pattern **Adapter** (Structural) trong codebase, lấy từ
bước discover. Cột `path:line` là đường dẫn TƯƠNG ĐỐI so với root `hex_agent/`; mở file thật
tại `/Users/uspro/Desktop/namnson/hex_agent/<path>`.

> Ghi chú độ rõ: **high** = ví dụ Adapter sạch, dễ thấy; **medium** = đúng pattern nhưng
> trộn thêm side-effect / tiện ích nên ranh giới mờ hơn.

| # | path:line | Mô tả | Độ rõ |
|---|-----------|-------|-------|
| 1 | `rag/ports.py:31-36` | **`VectorStorePort`** (Protocol) — Target interface mà `RagService` kỳ vọng: `health()/upsert()/search()`. Adaptee hai phía khác hẳn nhau (qdrant-client vs list). → **Case 01** | high |
| 2 | `rag/stores.py:24-57` | **`InMemoryVectorStore`** — Concrete Object Adapter bọc một list Python (`_chunks`), cosine search trong RAM. Adapter test offline. → **Case 01** | high |
| 3 | `rag/stores_qdrant.py:32-148` | **`QdrantVectorStore`** — Concrete Object Adapter bọc `qdrant_client.QdrantClient`; dịch `Chunk → PointStruct`, `Hit ← query_points`, lazy collection, `health()` không raise. → **Case 01** | high |
| 4 | `rag/service.py:15-19` | **`RagService`** (Client) — nhận `VectorStorePort` qua DI; logic chỉ gọi qua port, không coupling backend. → **Case 01** | high |
| 5 | `llm/adapter.py:72-119` | **`call_llm()`** — Adapter cấp-module bọc `openai.OpenAI`; cam kết không raise (luôn trả JSON), retry/backoff, downgrade json_object→text, thông điệp lỗi actionable. → **Case 02** | high |
| 6 | `llm/adapter.py:40-50` | **`_is_transient`** — phân loại lỗi đáng retry (429/5xx/timeout/connection) bằng duck-typing, không import lớp exception của openai. Tầng dịch lỗi của adapter. → **Case 02** | medium |
| 7 | `llm/adapter.py:53-59` | **`_is_connection_error`** — phát hiện endpoint không tới được (server chết / sai port). Lái thông điệp lỗi actionable. → **Case 02** | medium |
| 8 | `core/ports.py:32-45` | **`DelegationPort`** (Protocol) — Target interface cho agent ủy thác: `name/can_handle/run`. Core không biết agent thật hay giả. → **Case 03** | high |
| 9 | `adapters/agents/scripted.py:17-59` | **`ScriptedDelegationAgent`** — Concrete Object Adapter bọc list artifact ghi sẵn (test double tất định). → **Case 03** | high |
| 10 | `adapters/agents/langgraph_agent.py:21-95` | **`LangGraphDelegationAgent`** — Concrete Object Adapter bọc đồ thị langgraph (`graph.stream`); dịch mỗi bước thành `ArtifactEnvelope`. → **Case 03** | high |
| 11 | `adapters/agents/__init__.py:1-4` | Xuất cả hai delegation adapter — bằng chứng chúng thay thế nhau được. → **Case 03** | high |
| 12 | `rag/embedders.py:49-60` | **`FastEmbedEmbedder`** — Object Adapter bọc `fastembed.TextEmbedding` (lazy import, optional dep). Cài `EmbedderPort` (`dim`, `embed`); dịch numpy array → `list[list[float]]`. | high |
| 13 | `rag/embedders.py:33-46` | **`FakeEmbedder`** — Object Adapter bọc một hàm băm tất định; cài `EmbedderPort` cho test offline (không adaptee third-party, nhưng đúng hình dạng pattern). | high |
| 14 | `drag_from_zero/dragzero/adapters/llm_local.py:208-241` | **`OpenAICompatLLM`** — Object Adapter bọc `http_transport` (injectable, mặc định urllib OpenAI-compat). Cài port `complete(ctx) → dict`; trích/ép JSON, repair khi output hỏng, fallback. | high |
| 15 | `drag_from_zero/dragzero/adapters/llm_local.py:244-268` | **`RecordedLLM`** — Object Adapter bọc list chuỗi phản hồi (test double tất định); cùng port với `OpenAICompatLLM`, qua cùng đường `coerce_response`. | high |
| 16 | `drag_from_zero/dragzero/adapters/tools_fs.py:44-94` | **`ReadFileTool/WriteFileTool/ListDirTool/RunCommandTool`** — mỗi tool bọc method của `FsSandbox`, trả `ToolResult(ok, output, error)` không-bao-giờ-raise. Adapter có side-effect. | medium |
| 17 | `drag_from_zero/dragzero/adapters/tools_fs.py:16-42` | **`FsSandbox`** — adapter bọc `pathlib.Path` + `subprocess`, nhốt thao tác trong thư mục gốc; raise `SandboxError` khi vượt rào. Adapter giữa logic tool và filesystem/subprocess thô. | medium |
| 18 | `Design patterns/06_Adapter/06_adapter.py` | Ví dụ tham chiếu (pedagogical): `LGNAdapter/MGNAdapter/VPLAdapter` bọc adaptee mô phỏng thần kinh, cài `ThalamocorticalSignal` Protocol. Minh hoạ GoF chuẩn. | high |
| 19 | `Design patterns/30_Hexagonal/hex_cases/01_rag_service_ports_adapters/rag_service_ports_adapters.py:150-234` | Ví dụ dạy hexagonal: `InMemoryVectorStore` (150-177) + `QdrantVectorStore` (204-234) + `FakeQdrantClient` (180-201). Chưng cất từ code production; cùng `VectorStorePort` hai cách. | high |
| 20 | `llm/adapter.py:62-69` | **`_is_response_format_error`** — phát hiện server từ chối `response_format=json_object`; lái downgrade sang text. Tầng dịch của adapter. → **Case 02** | medium |
| 21 | `tests/test_llm_adapter.py:5-24` | **`_FakeClient` + `_FakeChoiceMsg`** — test double mô phỏng cấu trúc `openai.OpenAI`; test logic retry/backoff/json-mode của adapter không cần mạng. Minh hoạ DI để test được. | medium |
| 22 | `tests_audit/test_rag_qdrant_adapter_contract.py:63-243` | Bộ test hợp đồng adapter dùng `FakeClient` (dict state thay mạng): test `QdrantVectorStore` độc lập (upsert/search/delete/health); chứng minh dịch `Chunk → PointStruct`, `Hit ← payload`. | high |
| 23 | `tests_audit/test_rag_qdrant_adapter_contract.py:118-136` | **`test_health_never_raises_and_reports_collection_count`** — health() trả `{"ok": False, "error": str(exc)}` thay vì raise khi `ConnectionError("offline")`. Adapter dịch exception thành envelope dữ liệu. | high |

**Flagship đã dựng thành case con:**
- **Case 01** `01_rag_vector_store_adapter/` — hàng #1–4 (dual vector store).
- **Case 02** `02_llm_openai_adapter/` — hàng #5–7, #20–21 (LLM adapter retry/translate).
- **Case 03** `03_delegation_agent_adapters/` — hàng #8–11 (dual delegation agent).
