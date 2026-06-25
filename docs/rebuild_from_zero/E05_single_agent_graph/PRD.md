# E05 — Single-agent Graph Loop (PRD, draft)

Phase: P1 · Features: F08

## Problem
Cần vòng lặp tool viết **một lần** và tái dùng cho multi-agent. Repo cũ viết loop 2 lần (orchestrator + langgraph) → nợ. Ta xây single-agent **trên graph** ngay từ đầu.

## Goal
Một LangGraph `StateGraph` tối giản: node `agent` (LLM → action) + node `tool` + `route_next` (tool/final), dùng lại E01 kernel, E02 discipline, E03 adapter, E04 observability.

## Scope — In
- `AgentState` (TypedDict): messages, step_count, next_agent, last_failure, ...
- `make_agent_node`, `make_tool_node`, `route_next`.
- `run_single(task)` entrypoint; ghi event log mỗi node.
- Single-agent = graph 1 node (cấu hình), KHÔNG phải engine riêng.

## Scope — Out
- Nhiều role / multi-agent (E09/E10).

## Dependencies
E01, E02, E03, E04, E06 (tool call).

## Success metrics / Exit
- Hoàn thành 1 task đọc-tool (vd git/đọc file) end-to-end với LLM thật.
- Cùng node/loop sẽ được E10 tái dùng (không viết lại).

## Open questions
- Tool nội bộ chạy in-process hay qua MCP cho vòng lặp này? (xem E06).
