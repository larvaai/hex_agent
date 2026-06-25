# E09 — Roles & Lenses (PRD, draft)

Phase: P3 · Features: F13, F14

## Problem
Repo cũ: cùng một role tồn tại 3 dạng (config / class / langgraph node) → nợ. Cần **một nguồn sự thật** cho role.

## Goal
Role khai báo bằng YAML (allowed_tools, route_permissions, test_ownership, lenses); một `Agent` build từ config, **enforce allowlist runtime**; lenses là góc nhìn review nhúng vào prompt.

## Scope — In
- `roles/<role>.yaml`: name, role, department, system_prompt, allowed_tools (hỗ trợ `server.*`), allowed_skills, route_permissions.may_route_to, test_ownership.
- Role loader + validate chặt (thiếu trường → lỗi rõ).
- `Agent.build_prompt()` (role + lens + tools allowlist + skills contract); `is_tool_allowed()`; gọi tool ngoài quyền → JSON `finish_reason=blocker` (handoff).
- Lens specs + render block (purpose, allowed/forbidden tools, output_schema).

## Scope — Out
- Graph wiring (E10).

## Dependencies
E01, E06, E07.

## Success metrics / Exit
- Role config sai → lỗi validate rõ; tool ngoài allowlist → bị chặn (handoff).
- `test_ownership.owns_validation=false` ⇒ role code KHÔNG tự validate, phải handoff test.
- **Một** định nghĩa role dùng cho cả single & multi.

## Open questions
- Lens chạy trong prompt (phụ thuộc model tuân thủ) hay tách lời gọi riêng?
