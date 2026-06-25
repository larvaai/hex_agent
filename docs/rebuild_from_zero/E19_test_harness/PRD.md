# E19 — Test / Regression Harness (PRD, draft)

Phase: cross-cutting · Features: F25

## Problem
Hành vi agent dễ trôi; cần bộ kiểm hồi quy chạy được, gồm cả deterministic (không LLM) lẫn prompt-based.

## Goal
Harness: case runner (prompt → run → kiểm marker/substring, timeout, log), groups, smoke deterministic, dev_checks quick/full, capability suite — và **map acceptance.md (G/W/T) của các epic thành test**.

## Scope — In
- `run_cases` theo group (kernel/discipline/tools/rag/multi-agent/...); ghi `var/test_runs/<ts>/`.
- Deterministic smokes (không cần LLM/mạng) cho mọi epic nền.
- `dev_checks --quick/--full`, `capability_suite`, feature-contract tests.
- Quy ước biến **Acceptance Criteria** từng epic thành case (G/W/T → assert).

## Scope — Out
- Bản thân tính năng (các epic khác).

## Dependencies
Tất cả epic (kiểm chúng).

## Success metrics / Exit
- Chạy theo group; smoke deterministic xanh offline; log + summary ghi ra.
- Mỗi epic có ≥1 deterministic test cho AC cốt lõi.

## Open questions
- Sinh test tự động từ `acceptance.md` (G/W/T) tới mức nào?
