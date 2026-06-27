# Facade pattern trong hex_agent — Hồ sơ ca thực tế (hex_cases)

> Phụ lục thực chiến cho [Lesson 10 — Facade](../10_Facade.md).
> Mỗi case lấy một đoạn code **có thật** trong `hex_agent`, đã mở file kiểm chứng từng `path:line`, rồi distill thành một file Python tự chạy chỉ dùng thư viện chuẩn.

---

## Facade trong hex_agent là gì?

Bài học gốc ví **brainstem là Facade vĩ đại**: cortex chỉ phát intent cấp cao ("tăng nhịp thở", "respond to stress"), brainstem lo orchestration hàng chục nucleus bên trong. Trong `hex_agent`, mẫu này xuất hiện rất rõ ở những **API/hàm public điều phối nhiều subsystem nội bộ** và che workflow phức tạp khỏi client.

Tiêu biểu nhất, `orchestrator/loop.py` tự ghi trong docstring rằng nó là một *"public run/resume facade"* trên LangGraph đã biên dịch — gói checkpointer, session factory, graph runtime, budget, delegation service vào hai hàm đơn giản `run()` và `resume()`. Tương tự, `RagService` điều phối chunking + embedding + vector store sau các method `ingest`/`search` có gác sức khoẻ; còn `DelegationManager` phối hợp policy + registry + sessions + store + events cho mỗi yêu cầu uỷ thác.

Điểm chung của cả ba: **client chỉ gọi một interface đơn giản, không bao giờ import hay đụng tới subsystem nội bộ** — đúng tinh thần giảm coupling từ M×N xuống M+N.

## Các case con

| # | Case | Facade | Subsystem được che | File |
|---|------|--------|---------------------|------|
| 01 | [Orchestrator Loop](./01_orchestrator_loop_facade/) | `run()` / `resume()` (`orchestrator/loop.py:93`, `:217`) — **stateless** facade dạng hàm | kernel, session factory, graph builder, checkpointer, budget | [orchestrator_loop_facade.py](./01_orchestrator_loop_facade/orchestrator_loop_facade.py) |
| 02 | [RagService](./02_rag_service_facade/) | `RagService.ingest/search/health` (`rag/service.py:15`) — facade + cross-cutting gate | sandbox jail, chunking, embedder, vector store | [rag_service_facade.py](./02_rag_service_facade/rag_service_facade.py) |
| 03 | [DelegationManager](./03_delegation_manager_facade/) | `DelegationManager.delegate()` (`delegation/manager.py:63`) — chokepoint tuần tự + 3 nhánh lỗi | policy, registry→handler, child session, store, event bus | [delegation_manager_facade.py](./03_delegation_manager_facade/delegation_manager_facade.py) |

Mỗi thư mục con có `README.md` (6 mục: bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản rút gọn, cái giá/khi nào không nên dùng, câu hỏi tự kiểm tra) và một file `.py` tự chạy với `demo()` + assert + đối chứng "khi KHÔNG dùng pattern".

## Ba dáng vẻ khác nhau của cùng một pattern

- **Case 01** minh hoạ Facade **stateless dạng hàm** (`run`/`resume`), state nằm hết ở subsystem (session/checkpoint). Đối chứng: client tự lắp ráp 5 subsystem theo đúng thứ tự.
- **Case 02** minh hoạ Facade **class có cross-cutting concern** (health-gate gác mọi method) và **bất biến chống ghi lệch** (cardinality check trước upsert). Đối chứng: client quên check cardinality → ghi dữ liệu thiếu mà vẫn báo "ok".
- **Case 03** minh hoạ Facade **chokepoint nhiều nhánh lỗi**, mọi outcome quy về một `_finish()` duy nhất, giữ bất biến thứ tự event. Đối chứng: client tự dựng vũ điệu → handler nổ giữa chừng làm `finish` không chạy → audit trail rò rỉ.

## Chạy thử

```bash
python3 01_orchestrator_loop_facade/orchestrator_loop_facade.py
python3 02_rag_service_facade/rag_service_facade.py
python3 03_delegation_manager_facade/delegation_manager_facade.py
```

Cả ba thoát code 0, in narration tiếng Việt từng bước, không traceback.

## Vét cạn occurrence

Xem [CATALOG.md](./CATALOG.md) để có bảng đầy đủ **mọi** chỗ pattern Facade (và họ hàng builder/bootstrap gần kề) xuất hiện trong codebase, kèm `path:line`, mô tả và độ rõ.
