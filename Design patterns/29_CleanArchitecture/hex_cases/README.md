# hex_cases — Clean Architecture trong hex_agent

> Bộ case study **distill** (rút gọn trung thực) cho pattern **Clean Architecture** *như nó thực sự xuất hiện* trong codebase `hex_agent`.
> Mỗi case trỏ về file:line THẬT trong repo, kèm một bản `.py` self-contained chỉ dùng **standard library** để bạn chạy thử ngay.

Đây là phần thực hành đi kèm bài học gốc [`29_CleanArchitecture.md`](../29_CleanArchitecture.md). Bài học gốc dạy lý thuyết 4 vòng tròn + dependency rule; thư mục này chỉ cho bạn **cùng pattern đó đang sống ở đâu trong hex_agent**.

---

## Pattern là gì (một dòng)

**Clean Architecture** = bố cục hệ thống thành các vòng đồng tâm với **một quy tắc duy nhất: source-code dependency chỉ đi VÀO TRONG**. Lõi (entities + use cases) ổn định, không biết gì về vòng ngoài; vòng ngoài (adapters + frameworks) phụ thuộc lõi qua **interface owned by inner** (ở Python là `Protocol`).

## Pattern này hiện diện ở hex_agent thế nào

hex_agent triển khai Clean Architecture qua nhiều "seam" (đường khâu) inbound:

- **Lõi ổn định** (`core/ports.py`, `core/schemas.py`) định nghĩa các interface `Protocol` và các entity bất biến (`frozen dataclass`). Lõi **không bao giờ** import adapter.
- **Adapter** (`adapters/agents/`, `llm/adapter.py`, `rag/stores_qdrant.py`) *implement* các port từ lõi; chúng import vào trong, không bao giờ ngược lại.
- **Composition root** (`core/bootstrap.py`, `delegation/bootstrap.py`, `features/loader.py`) là nơi DUY NHẤT thấy mọi vòng — nơi wiring adapter cụ thể vào use case.
- Mỗi domain con (`rag`, `control`, `supervisor`, `delegation`) tự expose port riêng (`rag/ports.py`, `control/ports.py`, `supervisor/orchestrator.py`, `supervisor/broker.py`) để tách use case khỏi chi tiết hạ tầng (vendor LLM client, vector DB...).

Điểm cốt lõi: bạn có thể đổi `ScriptedDelegationAgent` ↔ `LangGraphDelegationAgent`, đổi `InMemoryVectorStore` ↔ `QdrantVectorStore`, mà **không chạm** vào use case (`DelegationManager`, `RagService`). Đó chính là dependency rule một chiều của Clean Architecture.

---

## Các case con (flagship)

Mỗi case là một folder đánh số, có `README.md` (bài học) + `<name>.py` (bản chạy được).

| # | Case | Distill từ | Dạy điều gì |
|---|------|-----------|-------------|
| 01 | [`core_delegation_seam`](01_core_delegation_seam/) | `core/ports.py`, `adapters/agents/scripted.py`, `delegation/bootstrap.py` | **Core Port + Adapter**: use case (`DelegationManager`) nhận `Protocol`, không biết adapter nào. Test chỉ cần mock port. Swap agent tại bootstrap, logic không đổi. |
| 02 | [`rag_layered_seam`](02_rag_layered_seam/) | `rag/ports.py`, `rag/stores_qdrant.py`, `rag/feature.py` | **Port cho external service**: `EmbedderPort` + `VectorStorePort`. Đổi backend (memory ↔ qdrant) chỉ rewire adapter; use case `RagService` hằng định. Lazy import giữ lõi nhẹ. |
| 03 | [`kernel_session_entities`](03_kernel_session_entities/) | `core/schemas.py`, `core/session.py`, `core/kernel.py` | **Entities bất biến (vòng 1)**: `frozen dataclass` làm contract qua mọi boundary. Tạo/serialize/deserialize không cần framework; 100% unit-testable. |
| 04 | [`feature_installer_composition`](04_feature_installer_composition/) | `core/bootstrap.py`, `features/loader.py`, `features/llm_chat.py` | **Composition root**: nơi duy nhất import mọi vòng. Config-driven lazy loading: tắt feature → không import adapter của nó. Đổi wiring → đổi hành vi, lõi y nguyên. |

Bảng vét cạn MỌI occurrence của pattern trong repo: xem [`CATALOG.md`](CATALOG.md).

---

## Cách chạy

```bash
cd 29_CleanArchitecture/hex_cases
python3 01_core_delegation_seam/core_delegation_seam.py
python3 02_rag_layered_seam/rag_layered_seam.py
python3 03_kernel_session_entities/kernel_session_entities.py
python3 04_feature_installer_composition/feature_installer_composition.py
```

Mỗi file in narration tiếng Việt từng bước, chạy `assert` chứng minh bất biến của pattern, và (nếu hợp lý) có một đối chứng "khi KHÔNG dùng pattern thì hỏng thế nào". Tất cả thoát code 0, không cần cài gì thêm.

---

## Quy ước đọc

- Mỗi case `README.md` có đủ 6 mục: (1) bối cảnh thật + file:line, (2) trích code thật, (3) bảng ánh xạ vai trò pattern ↔ code, (4) bản rút gọn mô phỏng gì / lược bỏ gì, (5) cái giá / khi nào KHÔNG nên dùng, (6) câu hỏi tự kiểm tra.
- Mọi `path:line` đã được mở và xác minh trong repo tại thời điểm viết. File `.py` distill **không** import `hex_agent` — chúng tự đứng độc lập để bạn đọc và chạy.
