# E20 — Labs (optional, later) (PRD, draft)

Phase: sau (sau khi nền vững) · Features: F26, F27

## Problem
Cần "vườn ươm" thí nghiệm tách biệt engine: hiểu repo, thử prompt, tự đánh giá — chạy được độc lập, mock-first.

## Goal
Lab harness: registry chạy lab độc lập qua một entrypoint chung; mỗi lab self-contained, mock-first (không cần LLM/mạng để chạy demo).

## Scope — In
- **repo-understanding lab** (deterministic): scan + AST + graph + test-map → context-pack → answer/impact, **No-Leap Guardian** (evidence-bounded).
- **prompt lab** (no-code agent room + prompt benchmark).
- **self-eval lab** (E15 ở dạng harness thí nghiệm).
- Registry kiểu `app lab <name> [cmd]`.

## Scope — Out
- Không phải đường chính của engine; không phụ thuộc ngược vào nó.

## Dependencies
Dùng chung tiện ích (discipline, llm, tools) — KHÔNG trùng lặp.

## Success metrics / Exit
- Lab chạy qua một entrypoint; mock chạy offline; repo-understanding bắt được lỗi thật (vd BOM/parse).

## Open questions
- Port lab nào trước? (repo-understanding hữu ích nhất cho coding-agent).
