# E02 — Output Discipline (PRD, draft)

Phase: P0 · Features: F05, F07

## Problem
Model local hay trả JSON hỏng (run thật: **33% ở bước final**), và repo cũ nhân đôi logic discipline ở 2 orchestrator. Cần **một module dùng chung**.

## Goal
Một thư viện `discipline/` lo: parse + repair JSON action, nén observation, finish-gate, và budget chống loop — dùng chung cho mọi graph/node.

## Scope — In
- `parse_action()` + repair (cân bằng ngoặc, escape, vá trailing comma) + thông điệp retry.
- `condense(tool_result)` để giảm phình prompt.
- `finish_gate`: chặn `final` nếu đã sửa code mà chưa có validation pass (trừ khi báo blocker).
- Budgets: `max_steps`, `max_parse_errors`, `max_same_tool_calls`; parse-error **không** ăn vào step budget.

## Scope — Out
- Bật JSON-mode (E03, nhưng E02 phụ thuộc nó).
- Wiring vào graph (E05/E10).

## Dependencies
E03 (JSON-mode là tuyến phòng thủ đầu). Được E05/E10 dùng.

## Success metrics / Exit
- JSON hỏng phổ biến được repair thành công; parse-error rate < ngưỡng đặt ra.
- finish-gate chặn final chưa validate; budget dừng loop lặp tool.

## Open questions
- Có chấp nhận "prose-only final sau khi tool đã chạy" như final hợp lệ không? (giảm retry phí — xem log thật).
