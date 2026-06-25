# E11 — Departments (Research & Safety) (PRD, draft)

Phase: P3 · Features: F17

## Problem
Một số năng lực nên gom thành "phòng ban" có quy trình riêng + một chốt an toàn trước khi chạy.

## Goal
- **Research Department**: search → source_reader → pdf_extract → citation, trả report có nguồn.
- **Safety Department**: permission + risk + prompt_injection + tool_scope, có thể **chặn** task.

## Scope — In
- `ResearchDepartment.run(request)` → `{summary, sources[]}` (citations).
- `SafetyDepartment.run(request, plan)` → `{status, notes}`; status `blocked` thì dừng sớm.
- Các member agent (E09 roles) gọi tool E06/E08.

## Scope — Out
- Global supervisor wiring (E12).

## Dependencies
E09, E06, E08.

## Success metrics / Exit
- Research trả bằng chứng + citation gắn nguồn.
- Safety chặn được task nguy hiểm (status=blocked → supervisor dừng).

## Open questions
- Department là sub-graph LangGraph hay class tuần tự gọi agent?
