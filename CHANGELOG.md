# Changelog

Mỗi mục = một đợt thêm/sửa, gắn với **Sprint + Epic**, để theo dõi "thêm gì, vì sao". Mục mới nhất ở trên.

## Sprint 2 — Chokepoint discipline + resume: trace, LLM-as-capability, middleware, lifecycle, checkpoint · 2026-06-20
Một nhánh thiết kế "kernel chokepoint": kéo LLM + condense/budget/policy về một cửa `execute_tool`, thêm vòng đời task và một loop mỏng ngoài kernel. **Tồn tại song song** với `graph/` (E05) và `safety/` (E06) của Sprint 1 — không thay thế (quyết định "giữ cả hai").

- **B — Trace IDs** (`core/kernel.py`, `observability/event_log.py`): `execute_tool` gắn `task_id` vào mọi event (`tool.requested/completed/failed`) + `envelope.metadata` → truy được `run_id ⊇ task_id ⊇ request_id` trong `events.jsonl`. An toàn khi chưa `accept_task` (task_id=None).
- **D — LLM là capability** (`features/llm_chat.py`): LLM gọi qua `execute_tool("llm.chat")` → có envelope + event như tool; observability đếm `llm_calls`/`llm_failures` (thêm vào `_METRICS`) và ghi kind `LLMCallEvent`. Transport giữ uniform `tool.*`; observability phân loại (kernel không special-case LLM).
- **Seam 3 — Task lifecycle** (`core/kernel.py`): `complete_task`/`fail_task` đóng vòng đời đối xứng `accept_task` (lưu `last_result`, xóa `current_task`, bắn `task.completed`/`task.failed`). finish_gate vẫn do orchestrator áp, không nhúng vào kernel.
- **Seam 2 — Middleware** (`core/middleware.py`, `middleware/`): chuỗi pre/post quanh chokepoint (`kernel.use(...)`; +1 field +1 method). `PolicyGate`, `BudgetGuard`, `CondenseResult` (bỏ qua `llm.*`), `Retry`, `TimingLog` — tái dùng `discipline`. Mặc định rỗng → tương thích ngược. `bootstrap._install_middleware` wire từ `config['middleware']` (inert nếu thiếu); `BudgetGuard` cố ý KHÔNG wire ở bootstrap (state per-run, tránh rò qua các run).
- **E05′ — Loop orchestrator** (`orchestrator/loop.py`): `run(kernel, request)` ráp các mảnh trên (LLM-as-capability + `complete_task` + discipline + finish-gate). **Song song** `graph/runtime.py`: graph dùng `llm_call` trực tiếp, orchestrator đi qua chokepoint.
- **Safety — giữ cả hai**: `middleware/PolicyGate` (deny-set ở chokepoint) tồn tại song song `safety/SafeToolPort` (bọc per-tool, `ToolPolicy` rich: terminal argv/git/destructive). Chưa hợp nhất (theo quyết định).
- **A — Resume được** (`core/state.py`, `core/schemas.py`, `orchestrator/checkpoint.py`, `orchestrator/loop.py`): `StateStore.snapshot/restore` + `TaskEnvelope.as_dict/from_dict`; loop ghi `checkpoint.json` (atomic: ghi `.tmp` rồi `os.replace`) sau mỗi bước vào `var/agent_runs/<run_id>/`; `resume(run_id)` nạp lại state+messages+budget và chạy tiếp, **giữ nguyên task_id** (trace liền mạch). `run(..., checkpoint=True)` mặc định bật; `run_id` mặc định = task_id (truyền cùng id với EventLogger để checkpoint nằm chung thư mục với events.jsonl).
- **C — LLM bền với lỗi tạm thời** (`llm/adapter.py`): phân loại transient (timeout/connection/429/5xx → retry có backoff mũ 0.5→1→2s) vs permanent (4xx → KHÔNG retry); cấu hình `LLM_MAX_RETRIES` (mặc định 2), `LLM_RETRY_BASE` (0.5s). Hạ `LLM_TIMEOUT` mặc định **600→120s**. Phân loại duck-typed (không import openai) nên giữ lazy + injectable. Lỗi cuối cùng vẫn trả `final/error` (không ném vào loop).
- Tests mới: `tests/test_{trace_ids,llm_capability,lifecycle,middleware,orchestrator,bootstrap_middleware,state,checkpoint,resume,llm_retry}.py`.
- Verify: **50 case (bộ module đụng tới, dựng lại trong sandbox)** xanh — mount sandbox đọc repo thật đang lỗi, nên chạy `python -m pytest` ở máy để xác nhận trên cây đầy đủ (gồm `test_{discipline,graph,safety,toolbox}`).
- Backlog: E10 multi-agent (graph router tái dùng loop); tùy chọn hợp nhất 2 nhánh loop (graph↔orchestrator) và safety (SafeToolPort↔PolicyGate); cân nhắc tách connect/read timeout cho adapter.

## Sprint 1 — Tools/Safety + Single-agent graph · 2026-06-16
Thêm tool layer in-process có chokepoint an toàn, và vòng lặp single-agent trên graph.

- **E06 Tools & Safety** (`safety/`, `toolbox/`):
  - `safety/sandbox.py` — path-jail workspace (`resolve` + `is_relative_to`).
  - `safety/policy.py` — `ToolPolicy` (terminal argv-only, chặn shell/lệnh phá hủy/git mutation) + `SafeToolPort` (chokepoint bọc mọi tool).
  - `toolbox/filesystem.py` (`fs_read/fs_write/fs_list`, sandbox), `toolbox/terminal.py` (`terminal_run`, argv-only + timeout), `toolbox/feature.py` (đăng ký tool qua SafeToolPort).
  - Quyết định: tool **in-process** đi qua kernel (không spawn mỗi call), `core/kernel.py` KHÔNG đổi (lõi sạch).
- **E05 Single-agent graph** (`graph/`): `state.py`, `nodes.py` (agent + tool node), `runtime.py` (`run_agent`: loop agent↔tool, dùng discipline + budget + finish-gate + event log). Single = 1 agent node + 1 tool node; multi-agent (E10) tái dùng nguyên loop.
- Tests: `tests/test_{safety,toolbox,graph}.py`. Config: thêm `toolbox` vào `config/features.yaml`.
- Verify: E06 logic test cô lập PASS (sandbox escape, policy, fs jail, SafeToolPort chokepoint); mọi file mới ast-parse sạch. (Full `pytest` xác nhận trên máy bạn — sandbox đang bị glitch đọc mount.)

## Sprint 0 — Nền móng (P0) · 2026-06-16
Khởi tạo repo `core_agent` + 4 epic nền. **24/24 test xanh**, smoke `CORE_AGENT_SMOKE_OK`.

- **E01 Kernel** (`core/`): `kernel`, `registry` (+ null fallback), `schemas` (envelope CapabilityResult), `events`, `state`, `bootstrap`; feature plugin từ `config/features.yaml` (`features/loader.py`, `features/example_echo.py`).
- **E02 Output Discipline** (`discipline/`): `json_gate` (parse+repair), `condense`, `finish_gate`, `budget`.
- **E03 LLM Adapter** (`llm/adapter.py`): JSON-mode, lazy client, injectable, lỗi → final JSON.
- **E04 Observability** (`observability/`): `event_log` (JSONL+summary+metrics), `inspect` CLI.
- Tests: `tests/test_{kernel,discipline,llm_adapter,observability}.py` (24 case). Smoke: `run_smoke.py`.
- Tooling: `tools/gen_map.py` → sinh `MAP.md`.
