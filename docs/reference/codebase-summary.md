# Tóm tắt codebase hex_agent

Cập nhật: 2026-06-25 · Nguồn: pyproject.toml, CHANGELOG.md, plans/reports/architecture-map-260625-2009-hex-agent-report.md

Repo này là một **hệ thống đa tác nhân hình lục giác** (hexagonal/microkernel) xây dựng lại từng epic từ E01 đến E21. Mục đích: tạo runtime agent LLM tương tác với các tool mà tất cả lệnh gọi LLM và tool đi qua một chokepoint duy nhất để đảm bảo observability, safety, và khả năng tiếp tục.

Tấn công hệ thống này từ hai chokepoint:

1. **`AgentKernel.execute_tool`** (`core/kernel.py:63`) - mọi hành động (LLM llm.chat hay tool thường) đều qua đây. Kiểm tra phạm vi, chuỗi middleware, phát sự kiện, bắt exception.
2. **`DelegationManager.delegate`** (`delegation/manager.py:63`) - delegation là lối vào riêng (không phải phương thức kernel). Kiểm tra policy, tạo session con, gọi handler.

## Tech stack

Từ `pyproject.toml` - phiên bản 0.0.1:

| Phần | Dependencies |
|---|---|
| **Core** | langgraph >= 1.2.6, < 1.3; langgraph-checkpoint-sqlite >= 3.1, < 4; openai >= 1.0; PyYAML >= 6.0 |
| **Dev** | pytest >= 8.0; ruff >= 0.5 (lint) |
| **Audit** | hypothesis >= 6 (property-based test); pytest-cov >= 5 (coverage); pytest-timeout >= 2 |
| **RAG** | qdrant-client >= 1.7, < 2 (optional); fastembed >= 0.3 (optional) |

Cài đặt cơ bản: `pip install -e ".[dev,audit]"`. Để dùng Qdrant: `pip install -e ".[rag]"`.

## Cơ cấu repo (~20 package chính)

| Package | Epic | Mục đích |
|---|---|---|
| `core/` | E01 | Microkernel đóng băng: chokepoint execute_tool, registry, envelope, EventBus, KernelSession + scope |
| `discipline/` | E02 | Hàm thuần: json parse + repair, finish gate, budget (step/parse/same-tool), condense |
| `llm/` | E03 | OpenAI-compatible lazy client, JSON mode, retry, expose dưới dạng capability llm.chat |
| `observability/` | E04 | EventBus subscriber -> events.jsonl + summary.json + CLI inspect |
| `graph/` | E05 | Compiled LangGraph per run; nodes (guard, agent, tool, delegate, finish, fail); topology + routing |
| `toolbox/` | E06 | Sandboxed fs/terminal tools (fs_read, fs_write, fs_list, terminal_run) |
| `safety/` | E06 | Workspace path-jail (resolve_in_workspace), terminal argv-only classifier, SafeToolPort wrapper |
| `middleware/` | E06 | Policy gate, retry, condense, budget, timing - xung quanh chokepoint |
| `orchestrator/` | E05 | run() + resume() facade; SQLite checkpoint truth; legacy JSON migration |
| `roles/` | E09 | Role spec + allowed_tools derivation (union explicit + core + skill, minus forbidden) |
| `skills/` | E07 | Skill contract, render (contract / full), union_tools feeds E09 derivation |
| `rag/` | E08 | VectorStorePort/EmbedderPort; ingest/search health-gated; Qdrant + fastembed backend, memory offline |
| `supervisor/` | E10 | Agent-O task loop (round-based, blackboard); DelegationPolicy builder; judge_acceptance |
| `delegation/` | E10 | DelegationManager chokepoint riêng; policy engine; in-memory store; scripted + LangGraph adapter |
| `adapters/` | E10 | Delegation port implementations (scripted, langgraph agents) |
| `control/` | E21 | RuntimeEvent envelope; RuntimeCommand/RuntimeCheckpoint contract; Redactor (14 secret keys); EventEmitter + BusEventSink |
| `config/` | E21 | features.yaml (feature + middleware flags); runtime_event_types.yaml + runtime_command_types.yaml allowlist |
| `ui/` | E18 | HTTP/SSE console (127.0.0.1:8765); /api/{bootstrap,runs,snapshot,tree,file,stream}; legacy, không import control/ |
| `features/` | E01+ | Plugin loader; example_echo; llm_chat install; toolbox install; rag install |

Xem chi tiết tại `plans/reports/architecture-map-260625-2009-hex-agent-report.md`.

## Cách chạy + self-check

```bash
# Cài cơ bản
pip install -e ".[dev,audit]"

# Smoke test (không LLM, không mạng) - in CORE_AGENT_SMOKE_OK
python run_smoke.py

# Đầy đủ test suite
python -m pytest

# Inspect run cuối cùng
python -m observability.inspect summary latest

# Khởi động console UI tại http://127.0.0.1:8765
python -m ui.server

# Regenerate architecture map (nếu thêm file mới)
python tools/gen_map.py
```

Để CI/CD: `.github/workflows/ci.yml` chạy ruff lint + pytest + pytest tests_audit trên Python 3.11.

## Thứ tự đọc cho người mới

1. **File này** - cái gì là cái gì + cách chạy
2. [docs/getting-started.md](../getting-started.md) - 5 lớp dẫn đường (MAP, CHANGELOG, epic doc, test, git log)
3. [docs/reference/runtime-flow.md](./runtime-flow.md) - một task chạy từ input -> output
4. [docs/reference/known-risks.md](./known-risks.md) - file nào dễ vỡ + invariant cần giữ
5. [plans/reports/architecture-map-260625-2009-hex-agent-report.md](../../plans/reports/architecture-map-260625-2009-hex-agent-report.md) - file key + responsibility chi tiết
6. Mở epic đang quan tâm ở [docs/spec/](../spec/) (E01 kernel -> E21 control plane)
7. Đọc test tương ứng + module code

## Trạng thái hiện tại

**Nền móng done**: E01-E04 (Sprint 0) - kernel, discipline, llm adapter, observability.

**Mở rộng done**: E05-E10 + E08 (Sprint 1-4) - single-agent LangGraph, tools/safety, rag (Qdrant + memory), multi-agent delegation.

**Frontier**: E21 Realtime Control Plane (đợt E16+E17+E18) - chỉ Phase A (S-CONTRACT: contracts + registries, commit 7998c27) + Phase B B1 (EventEmitter canonical publish, commit f73d377) merged. Transport / Control-Tower UI / command-lifecycle / approval-gate / reliability / interrupt-streaming chưa. Control plane không dây vào runtime sống hay UI (supervisor emitter là opt-in, default None).

Xem [docs/roadmap/](../roadmap/) để biết roadmap chi tiết.

## Quy tắc không phá

Trước khi sửa `core/kernel.py`, `graph/state.py`, `orchestrator/checkpoint.py`, `graph/runtime.py`, `delegation/policy.py`, `safety/sandbox.py` - đọc [docs/reference/known-risks.md](./known-risks.md). Sửa ẩu ở đó vỡ observability, state, session, safety cho toàn bộ hệ thống.

Kiểm tra nhanh: `python run_smoke.py` + `python -m pytest`. Nếu xanh hết = chưa phá invariant.
