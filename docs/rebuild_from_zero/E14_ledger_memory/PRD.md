# E14 — Ledger & Experience Memory (PRD, draft)

Phase: P4 · Features: F20

## Problem
Agent nên nhớ quyết định/lỗi/bài học để lần sau tốt hơn — nền của tự cải tiến.

## Goal
Ledger append-only (decision/failure/lesson) + tùy chọn nhúng vào RAG kinh nghiệm để truy vấn.

## Scope — In
- `ledger_append(entry_type, title, data, tags)`, `ledger_tail`, `ledger_search(text/type/tag)`, `ledger_get`, `ledger_stats` (JSONL trong workspace).
- Tùy chọn embed entry vào RAG (E08) để search ngữ nghĩa.

## Scope — Out
- Cơ chế quyết định tự cập nhật skill/lens (E15).

## Dependencies
E06 (tool), E08 (RAG tùy chọn).

## Success metrics / Exit
- Append-only (không sửa entry cũ); search theo type/tag/text; sống sót qua restart.

## Open questions
- Khi nào tự động ghi lesson (sau mỗi failure? chỉ khi reviewer chốt)?
