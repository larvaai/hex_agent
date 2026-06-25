# E18 — UI & Process Dashboard (PRD, draft)

Phase: P4 · Features: F24

## Problem
Cần xem process/log/state trực quan thay vì đọc JSONL thô; cũng là nơi đặt review gate (E16).

## Goal
Một web UI local đọc event log + run state, refresh được; là bề mặt cho review gate.

## Scope — In
- Liệt kê runs; xem events (lọc theo kind/tool); xem summary/metrics; trạng thái run đang chạy.
- Reload data; (host UI cho E16 plan/diff review).

## Scope — Out
- Logic agent/graph (các epic khác).

## Dependencies
E04 (event log), E16 (gate UI).

## Success metrics / Exit
- Hiển thị danh sách run + events + state; refresh cập nhật.

## Open questions
- Framework UI (FastAPI + HTML tối giản, hay tích hợp Plannotator)?
