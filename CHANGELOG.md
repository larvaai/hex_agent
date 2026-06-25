# Changelog

Mỗi mục = một đợt thêm/sửa, gắn với **Sprint + Epic**, để theo dõi "thêm gì, vì sao". Mục mới nhất ở trên.

## E21 — Control-plane UI on a fake backend (full T1) · 2026-06-26

- **UI-first slice** (plan `260626-0212`): React+Vite+TS control-plane UI under `ui/control-plane/` built against a fake Python server (`tools/fake_control_server.py`) that **reuses `control/`** (same `Redactor`/`SessionSeq`/`parse_command`/registries/`build_snapshot`) — drop-in to the real backend is "change the URL".
- **Backend contracts**: `control/snapshot.py` (`TaskLoopSnapshot`/`AgentView`/`build_snapshot` folding `loop.*` events — S21.9; reads redacted `ui_payload` only — F2), `CommandAck` in `control/commands.py` (S21.15), `control/replay.py` ring-buffer (2048) with `Last-Event-ID` catch-up + out-of-ring resync (F7).
- **Generated TS contracts** from the dataclasses (`tools/gen_ts_contracts.py` + `--check` drift guard) — no hand-written types.
- **Fake server**: `GET /api/snapshot`, SSE `/api/stream` (redacted `ui_payload` only, visibility-gate drops `secret`, read token via `?token=`), `POST /api/commands` (static-token authz, registry+schema validation, idempotency, `CommandAck`); inject-reality latency + forced SSE drop. `+SubmitPrompt` command type (F5/D8).
- **UI**: Agent Graph (React Flow + dagre), virtualized Event Timeline, Inspector, Approval modal, Prompt/Send; one transport adapter, store written only by the stream (no optimistic mutate).
- **Done = contract-seam test** (`ui/control-plane/src/test/contract-seam.test.ts`) drives the real adapter against the real fake server (UI reads only `ui_payload`, renders `[REDACTED]`, Approve posts a real `RuntimeCommand`, reconnect via `Last-Event-ID`). Live supervisor→snapshot wiring deferred (BACKLOG).

## E08 — RAG (Qdrant + fastembed), slices S2/S3 · 2026-06-25

- **S2 prod adapter** — `rag/stores_qdrant.py::QdrantVectorStore` hiện thực `VectorStorePort` thật trên qdrant-client: collection tạo lười theo dim của vector ở lần `upsert` đầu, point id = `uuid5(source::chunk_index)` (re-upsert ghi đè đúng chỗ), `delete_by_source` lọc theo payload `source` (đã đánh index keyword), search qua `query_points` với `score_threshold` server-side. `health()` không ném: server không reachable → `{"ok": False}` để giữ cổng dependency-failure (S08.1) là control-flow thường.
- Dep RAG vào **optional group `rag`** (`qdrant-client`, `fastembed`) — không nhồi base install; `pip install -e ".[rag]"` khi cần.
- `docker-compose.rag.yml` cho Qdrant local; `tests/test_rag_qdrant.py` chạy adapter thật nhưng **skip nếu Qdrant không reachable** (suite mặc định vẫn offline, không docker). Test dùng `FakeEmbedder` để soát logic store, không tải model.
- **S3 wire + obs** — bật feature `rag` (backend `memory`, offline) trong `config/features.yaml`; mỗi tool phát thêm event ngữ nghĩa `rag.health/rag.ingest/rag.search` (kèm lineage session) song song `tool.*` của chokepoint; envelope `rag_search` thêm `top_k`/`score_threshold` để quan sát.
- Bất biến giữ nguyên: tool qua `execute_tool`; path qua sandbox jail; health-gate trước ingest/search; logic chỉ chạm Qdrant qua `VectorStorePort`; pytest không cần docker.

## Sprint 4 — KernelSession + sequential delegation · 2026-06-24

- Tách toàn bộ per-run state/lifecycle khỏi `AgentKernel` sang `KernelSession`; `SessionFactory` là constructor duy nhất cho root/child session và enforce capability scope thu hẹp.
- Freeze registry, middleware và config trước session đầu tiên; `StateStore` snapshot/restore deep-copy để không alias mutable state giữa các session.
- Harden `EventBus` và `EventLogger` cho concurrent publish, detached payload, monotonic sequence và serialized file writes.
- Thêm contract thuần `DelegationSpec/Policy/Request/Progress/Result`, `DelegationPort`, `DelegationStorePort`, `DelegationServicePort`—không phụ thuộc LangGraph.
- Thêm top-level `delegation/` manager/registry/policy/in-memory store, scripted adapter và local `LangGraphDelegationAgent`; progress được persist trước khi publish.
- LangGraph chạy theo `session=`, checkpoint `session_state` schema v2, migrate key `kernel_state` cũ, và hỗ trợ action `delegate` qua service injection.
- Parallel department, durable delegation resume và transactional outbox vẫn bị khóa bởi readiness gates trong tài liệu kiến trúc.

## Sprint 3 — LangGraph runtime consolidation · 2026-06-24

- Thay hai handwritten agent loop bằng một compiled `StateGraph`; `orchestrator.run/resume` giữ nguyên public API.
- Giữ `AgentKernel` framework-agnostic: node LLM và tool đều gọi `execute_tool`, nên middleware, safety, envelope và trace ID không bị bypass.
- Chuyển checkpoint thật sang `langgraph.sqlite` theo từng run; `checkpoint.json` chỉ là projection nguyên tử cho UI. Resume giữ nguyên `run_id`, `task_id`, messages, budget và kernel state qua process restart.
- Đưa step/parse/same-tool budget vào graph state. Same-tool guard nay hoạt động trên production orchestrator và chặn trước lần thực thi dư.
- Bổ sung graph transition metrics cho EventLogger, migration một lần từ JSON checkpoint cũ, và cấu hình setuptools package discovery để `pip install -e ".[dev]"` hoạt động.
- Dependency: `langgraph>=1.2.6,<1.3`, `langgraph-checkpoint-sqlite>=3.1,<4`.

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
