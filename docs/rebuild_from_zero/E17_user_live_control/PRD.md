# E17 — User Live Control (PRD, draft)

Phase: cross-cutting · Features: F22

## Problem
Người dùng cần chèn chỉ thị **khi run đang chạy** (đổi hướng, thêm ràng buộc) thay vì chờ xong.

## Goal
Kênh user-agent: inbox directive đọc giữa các bước; chỉ thị người **ưu tiên hơn** gợi ý agent-agent; có compliance gate.

## Scope — In
- Inbox: `control/inbox.jsonl` hoặc stdin interactive.
- `apply_user_directives()` chèn directive vào state trước bước kế.
- Compliance gate: directive KHÔNG được tắt trace/log, bịa tool không có, hay đòi chain-of-thought ẩn.
- (Tùy chọn) replan khi directive đổi mục tiêu.

## Scope — Out
- Review gate plan/diff (E16) — khác mục đích nhưng chung kênh feedback.

## Dependencies
E05/E10 (vòng lặp), E04 (trace), chung kênh với E16.

## Success metrics / Exit
- Directive được nhặt giữa run; được ưu tiên hơn gợi ý agent.
- Không thể tắt trace/bịa tool qua directive.

## Open questions
- Interactive stdin vs file inbox làm mặc định?
