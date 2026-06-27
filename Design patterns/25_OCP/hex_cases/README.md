# OCP (Open/Closed Principle) trong hex_agent — Bộ ca thực chiến

> **OCP** = mở để **mở rộng**, đóng để **sửa đổi**. Yêu cầu mới đến → **thêm** code mới
> (interface impl / decorator / strategy / plugin), **không sửa** code cũ đã test.
> — lesson gốc: [`../25_OCP.md`](../25_OCP.md)

Thư mục này distill các chỗ hex_agent áp dụng OCP thành những bản **chạy được, chỉ stdlib**,
kèm bài học. Mỗi case trỏ ngược về `path:line` thật trong codebase (đã mở file kiểm chứng).

---

## hex_agent áp dụng OCP ở đâu?

hex_agent là một agent kernel, và OCP là *xương sống kiến trúc* của nó. Toàn bộ năng lực được
gắn vào hệ thống qua **extension point**, không qua mổ xẻ code lõi:

1. **Protocol-based ports** định nghĩa abstraction: `ToolPort`, `ToolMiddleware`, `Worker`,
   `EmbedderPort`/`VectorStorePort`, `ChatLLM`, `OrchestratorPort`, `EventSinkPort`,
   `DelegationPort`…
2. **Nhiều implementation cho mỗi port** mà không sửa code cũ: `ScriptedWorker`/`LocalLLMWorker`,
   `FakeEmbedder`/`FastEmbedEmbedder`, `InMemoryVectorStore`/`QdrantVectorStore`,
   `ScriptedOrchestrator`/`LLMOrchestrator`.
3. **CapabilityRegistry + plugin (features/install)** cho phép thêm tool mới mà không đụng kernel.
4. **ToolMiddleware chain (Decorator)** trong `kernel.execute_tool` cho phép thêm cross-cutting
   concern (logging, retry, budget) độc lập, cắm bằng `kernel.use()`.
5. **Config-driven dispatch** (`rag.feature.build_service`, các `*TypeRegistry` data-driven) đẩy
   "loại" vào data thay vì if/elif ở caller.

Kết quả: thêm một variant mới (tool, embedder, vector store, middleware, worker, orchestrator) =
thêm 1 class mới, **0 sửa class cũ**. Đúng định nghĩa OCP của Robert C. Martin.

---

## Các case con (flagship)

| # | Case | Cơ chế OCP | Nguồn thật chính |
|---|---|---|---|
| 01 | [CapabilityRegistry + ToolPort](./01_capability_registry_and_port_pattern/) | Plugin / Registry (#6) | `core/ports.py:19-27`, `core/registry.py:43-122`, `features/*.py`, `rag/feature.py` |
| 02 | [ToolMiddleware chain](./02_middleware_decorator_chain/) | Decorator (#3) | `core/middleware.py:11-22`, `core/kernel.py:24-104,192-194`, `middleware/*.py` |
| 03 | [Worker Strategy (Scripted/LocalLLM)](./03_worker_strategy_pattern/) | Strategy (#1) | `decompose_agent/worker.py:182-301`, `supervisor/orchestrator.py:15-39` |

Mỗi thư mục con có:
- `README.md` — bài học 6 mục (bối cảnh, trích code thật, ánh xạ vai trò, bản rút gọn, cái giá,
  câu hỏi tự kiểm).
- `<name>.py` — bản distill self-contained, `python3 <name>.py` exit 0, in narration tiếng Việt,
  có assert chứng minh bất biến OCP và đối chứng anti-pattern.

---

## Vét cạn mọi occurrence

Xem [`CATALOG.md`](./CATALOG.md) — bảng đầy đủ **mọi** chỗ OCP xuất hiện trong codebase (ports,
implementations, registry, config-driven dispatch), kèm `path:line` và độ rõ.

---

## Cách chạy nhanh tất cả

```bash
cd "Design patterns/25_OCP/hex_cases"
python3 01_capability_registry_and_port_pattern/capability_registry_and_port_pattern.py
python3 02_middleware_decorator_chain/middleware_decorator_chain.py
python3 03_worker_strategy_pattern/worker_strategy_pattern.py
```

Cả ba thoát code 0, không traceback. Chỉ dùng thư viện chuẩn Python 3.14 — không import hex_agent,
không thư viện bên thứ ba.

---

## Một câu để nhớ

> OCP không phải "đừng sửa code". OCP là "**axis of change** đã rõ → đặt extension point đúng nơi →
> variant mới đến qua extension point, không qua mổ xẻ code cũ." (lesson 25)
