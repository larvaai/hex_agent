# E04 — Observability (PRD, draft)

Phase: P0 · Features: F06

## Problem
Quan sát/audit rẻ khi làm sớm, đắt khi nhồi sau. Repo cũ có event log tốt — giữ và chuẩn hóa từ commit đầu.

## Goal
Event log event-sourced + run artifacts + CLI inspect, để mọi run có vết đầy đủ (debug, đánh giá, hồi quy).

## Scope — In
- `EventLogger` ghi `events.jsonl` (Message/Action/Observation/State) + `summary.json` + `index.jsonl`.
- Metrics counters: steps, llm_calls, parse_errors, tool_calls, tool_failures, policy_blocks, finish_gate_blocks, condensed...
- CLI `inspect` (list / summary latest / events filter theo kind/tool/text/json).
- Bật/tắt qua env `AGENT_EVENT_LOG`.

## Scope — Out
- Web dashboard (E18).

## Dependencies
E01 (EventBus). Dùng bởi mọi run.

## Success metrics / Exit
- Mỗi run sinh `events.jsonl` + `summary.json`; metrics khớp số sự kiện.
- `inspect events latest --kind ObservationEvent` lọc đúng.

## Open questions
- Chính sách retention/rotation cho `var/agent_runs/`?
