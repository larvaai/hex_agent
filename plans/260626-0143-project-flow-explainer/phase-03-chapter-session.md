---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — Chương 2: Session + State + Factory

> Plan: [plan.md](plan.md) · Template: [phase-01-scaffold-and-map.md](phase-01-scaffold-and-map.md)
> Nguồn: `core/session.py` · `core/state.py` · `system-architecture.md` §6

## Mục tiêu

Nhu cầu #1: *"Mỗi lần chạy phải có bộ nhớ riêng, không giẫm chân nhau."* → sinh ra `KernelSession`,
`StateStore`, `SessionFactory`, `SessionIdentity`. Copy template P1.

## Nội dung (khớp code hiện tại)

**Câu đố**: "Kernel thì **shared + frozen** (dùng chung, đông cứng). Vậy chỗ nào giữ bộ nhớ riêng của một
task đang chạy, và vì sao KHÔNG để chung trong kernel?" → Lật: `KernelSession` giữ per-run state; tách ra
để state không rò giữa các run trên cùng kernel shared ([system-architecture.md:155-163](../../docs/system-architecture.md), [core/session.py:49-51](../../core/session.py)).

**Bảng `__init__` `KernelSession`** ([core/session.py:49-57](../../core/session.py)) — gồm field nội bộ:

| Field | Vai trò |
|---|---|
| `kernel` | tham chiếu kernel shared |
| `identity: SessionIdentity` | "tôi là ai" (xem bảng dưới) |
| `state: StateStore` | sổ ghi chú riêng của run này |
| `allowed_capabilities: frozenset[str]` | phạm vi tool được phép |
| `_closed: bool` | vòng đời task đã đóng chưa |

**Bảng `SessionIdentity`** ([core/session.py:15-23](../../core/session.py)): `session_id`, `run_id`,
`task_id`, `agent_id`, `parent_session_id`, `delegation_id`, `depth` — giải mỗi cái là correlation ID gì.

**Sân khấu**: animate vòng đời — `SessionFactory.create_root` ([core/session.py:119](../../core/session.py))
→ session "active" (có `current_task`) → `execute_tool` (gọi qua kernel kèm `call_context`,
[core/session.py:75-85](../../core/session.py)) → `complete_task`/`fail_task` → `_closed=True`. Token đi
qua các trạng thái; minh hoạ "session không active → trả lỗi" ([core/session.py:76-84](../../core/session.py)).

**Slice — substrate vs per-run**: `<details>` so sánh 2 cột: cái gì thuộc kernel (frozen, shared) vs cái gì
thuộc session (mutable, riêng). Đây là insight cốt lõi để hết "rối".

> Lưu ý: `create_child` (delegation) chỉ **nhắc qua 1 dòng** ("đứa con, scope hẹp hơn — Chương 9 đào sâu"),
> KHÔNG dạy ở đây (giữ phạm vi).

## Execution steps

1. Copy template P1 → điền nội dung.
2. Self-check Validation.

## Tests / validation

- [ ] 0 lỗi console; animation vòng đời chạy; nhánh "không active → lỗi" có minh hoạ.
- [ ] 2 bảng `__init__` đủ field (KernelSession 5, SessionIdentity 7), gồm `_closed`.
- [ ] `file:line` footer trỏ thật.
- [ ] No CDN/external.

## Risks + rollback

- Risk: lan sang delegation/multi-agent. Mitigate: chốt 1 dòng nhắc, defer Chương 9.
- Rollback: `git rm chapter-2-session.html`.
