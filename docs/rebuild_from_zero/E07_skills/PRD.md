# E07 — Skills System (PRD, draft)

Phase: P2 · Features: F11

## Problem
Repo cũ: skill nhồi nguyên body, không có Allowed/Forbidden rõ, **không khai báo MCP tool** → không thể thu hẹp allowlist, loãng context (xem `docs/24`).

## Goal
Skill = **operating contract** ngắn: Allowed/Forbidden + **tool MCP đích danh**; loader hỗ trợ **progressive disclosure** (contract-mode mặc định, full khi skill được chọn).

## Scope — In
- Template `SKILL.md`: frontmatter (name, description+triggers) + `Allowed (tools)` + `Forbidden (tools)` + Steps + Report.
- Loader: parse frontmatter, `mode="contract"` (cắt từ `## Steps`) vs `mode="full"`.
- Skill khai báo tool → dùng để **suy `allowed_tools` của role**.

## Scope — Out
- Roles/allowed_skills (E09).

## Dependencies
E06 (tên tool), E09 (role gắn skill).

## Success metrics / Exit
- Contract-mode chỉ nạp description + Allowed + Forbidden mặc định.
- Mỗi skill nêu tool MCP đích danh; allowlist role suy được từ union tool của skill.

## Open questions
- Tự động derive `allowed_tools` role = union(tool của skill role đó) + tool lõi?
