---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — Chương 1: Kernel + execute_tool

> Plan: [plan.md](plan.md) · Template: [phase-01-scaffold-and-map.md](phase-01-scaffold-and-map.md)
> Nguồn: `core/kernel.py` · `core/registry.py` · `core/schemas.py` · `system-architecture.md` §4

## Mục tiêu

Nhu cầu #0: *"Tôi ra lệnh, có thứ thi hành."* → sinh ra kernel + `execute_tool` + registry + envelope.
Copy template từ P1.

## Files

- **Tạo** `docs/explanation/learn/chapter-1-kernel.html` (self-contained).

## Nội dung (khớp code HIỆN TẠI — đây là điểm chống drift)

**Câu đố**: "Tool có thể lỗi: file thiếu, network chết, bug. Nếu một tool ném exception, chuyện gì xảy ra
với cả agent?" → Lật: kernel bọc `try/except` quanh executor → tool **không bao giờ** làm sập kernel, lỗi
biến thành envelope `kernel_error` ([core/kernel.py:113](../../core/kernel.py)).

**Bảng `__init__` của `AgentKernel`** ([core/kernel.py:42-46](../../core/kernel.py)) — gồm cả field nội bộ:

| Field | Vai trò |
|---|---|
| `registry: CapabilityRegistry` | tra tên-tool → executor |
| `events: EventBus` | publish `tool.requested/completed/failed` |
| `config: Mapping` | cấu hình (đông cứng khi freeze) |
| `_middlewares: list` | các lớp onion quanh cửa |
| `_frozen: bool` | đã khoá chưa (cấm sửa khi có session) |

> ⚠️ KHÔNG có field `state` và KHÔNG có `accept_task` — prose cũ `docs/explanation/modules/kernel.md`
> tả nhầm (đã drift sang `KernelSession`/`SessionFactory.create_root`). Verify: grep `state` trong
> `core/kernel.py` class body → không có field state.

**Sân khấu**: animate đúng 6 bước thật của `execute_tool` ([system-architecture.md:82-114](../../docs/system-architecture.md), [core/kernel.py:63-169](../../core/kernel.py)):
`publish tool.requested` → `scope check` → `middleware onion` (mờ, sẽ sâu ở Chương 3) → `core: resolve→execute→envelope` → `publish completed|failed` → return. Token chạy qua từng trạm, dừng ở "scope check" minh hoạ nhánh chặn.

**Slice khó — `deep_freeze` config** ([core/kernel.py:14-21,48-54](../../core/kernel.py)): `<details>` giải
"vì sao đông cứng config?" → để state không rò giữa các run khi kernel shared. Snippet tối giản minh hoạ
`MappingProxyType` chặn ghi.

**Registry/envelope**: 1 đoạn ngắn — `resolve_tool` trả `NullToolPort` khi thiếu tool (kernel vẫn sống),
envelope `CapabilityResult` chuẩn hoá mọi kết quả. `[UNVERIFIED line core/registry.py / core/schemas.py —
confirm in cook]`.

## Execution steps

1. Confirm `[UNVERIFIED]`: mở `core/registry.py` + `core/schemas.py`, lấy line thật cho NullToolPort + CapabilityResult.
2. Copy template P1 → điền nội dung trên.
3. Self-check Validation.

## Tests / validation

- [ ] 0 lỗi console; animation 6 bước khớp `execute_tool`.
- [ ] Bảng `__init__` đúng 5 field; KHÔNG liệt kê `state`/`accept_task`.
- [ ] Mọi `file:line` trong footer trỏ thật (grep verify).
- [ ] `[UNVERIFIED]` đã resolve thành line thật.
- [ ] No CDN/external.

## Risks + rollback

- Risk: copy nhầm prose drift. Mitigate: bảng field verify bằng grep code thật.
- Rollback: `git rm chapter-1-kernel.html`.
