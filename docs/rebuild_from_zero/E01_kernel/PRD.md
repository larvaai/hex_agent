# E01 — Agent Kernel & Contracts (PRD, draft)

Phase: P0 · Features: F01, F02, F03, F04

## Problem
Cần một lõi ổn định mà việc thêm tool/agent/feature **không phải sửa lõi**. Repo cũ làm tốt phần này (`core/`) nhưng bị nhân đôi orchestrator → ta tách lõi sạch ngay từ đầu.

## Goal
Một `AgentKernel` hexagonal sở hữu state + events + capability registry; mọi tool trả **một envelope chuẩn**; feature nạp theo config và tháo-lắp được.

## Scope — In
- `AgentKernel.execute_tool()` định tuyến qua registry; bắt exception → envelope.
- `CapabilityRegistry` (exact → fallback → `NullToolPort`).
- `CapabilityResult{ok,capability,feature,data,error,metadata}` + `from_raw`.
- `EventBus` + `StateStore`; ports (`tool/code/test/search/memory/...`).
- `features.yaml` loader: bật/tắt feature, mỗi feature khai capabilities + tests.

## Scope — Out
- Tool/agent/LLM cụ thể (E03/E05/E06+).
- Graph orchestration (E05/E10).

## Dependencies
Không (đây là nền). Mọi epit khác phụ thuộc E01.

## Success metrics / Exit
- Đăng ký 1 dummy tool → gọi qua kernel → nhận envelope → có event.
- Tool không tồn tại → `ok=false, missing_capability=true` (kernel không chết).
- Tắt feature trong config → tool của nó trả missing_capability; kernel vẫn boot.

## Open questions
- pydantic hay dataclass cho schema? (khuyến nghị pydantic để dùng cho cả validation/JSON-mode).
