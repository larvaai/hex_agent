# Changelog

Mỗi mục = một đợt thêm/sửa, gắn với **Sprint + Epic**, để theo dõi "thêm gì, vì sao". Mục mới nhất ở trên.

## E21 — S21.33 evidence types + AC report · 2026-06-26

- **Siết acceptance gate theo loại evidence** (`supervisor/evidence.py` MỚI; `supervisor/graph.py:238`): `evidence_type_of(artifact)` suy loại từ `artifact.kind`; `judge_acceptance` honor `passed` chỉ khi **mọi** id cited resolve trên Blackboard **và ≥1** id là evidence thật (≥1-valid, KHÔNG all-valid). Scaffolding (`session_plan`/`context_packet`/`ac_report` ∈ `NON_EVIDENCE_KINDS`) hoặc kind rỗng → không tính. Chặn O "pass" AC bằng cách trỏ vào scaffolding.
- **AC report khi FINISHED** (`supervisor/evidence.py::record_ac_report`; `supervisor/loop.py:173`): loop đạt FINISHED sinh đúng một artifact `kind=ac_report` (id `ac_report-{session_id}` → idempotent qua resume, AC6) chụp `{session_id, task_id, checks[{status, evidence_ids, evidence_types}]}`. Finish-denied KHÔNG sinh.
- **Phòng thủ adversarial** (`tests_audit/test_acceptance_evidence_adversarial.py` MỚI): ac_report không tự làm evidence (AC5), resume sau finish không nhân đôi report (AC6), property hypothesis ghim bất biến cổng (passed ⇒ all-exist + ≥1-typed).
- Backward-compatible: `AcceptanceCheck` **không đổi** (evidence_type derive, không lưu) → 0 migration; `control/*` + `config/runtime_*_types.yaml` không đổi (artifact-only, no emit). Quyết định: **DEC-7**.

## E21 — Realtime Control Plane (Phase A + Phase B B1) · 2026-06-25

- **Phase A — S-CONTRACT** (commit `7998c27`): contracts + 2 registry trong `control/` — `RuntimeEvent` envelope, `RuntimeCommand`, `RuntimeCheckpoint`, `Permission`, `Redactor` (mask 14 secret keys, không mutate gốc), `event_registry` + `command_registry` allowlist. Lớp ABOVE kernel (như `supervisor`), no I/O.
- **Phase B B1 — EventEmitter canonical path** (commit `f73d377`): `control/emitter.py` publish envelope qua `EventSinkPort`; `BusEventSink` bridge → EventBus/EventLogger. Luồng: gate → seq → redact → fan-out.
- **Gộp E16+E17+E18** thành E21 (review gate + live control + UI dashboard). **PENDING**: transport (POST /api/commands + SSE redaction), Control-Tower UI, command lifecycle, approval-checkpoint, reliability. Chưa wire vào live runtime/UI (supervisor emitter opt-in, default None — `supervisor/graph.py:47`).
- Thiết kế đầy đủ: `docs/spec/active/E21-realtime-control-plane/`.

## E10 — Multi-agent + Delegation · 2026-06-25

- **TaskLoop (Agent O)** (`supervisor/`): vòng lặp round-based trên blackboard — Agent O compose team + scoped context, phát structured decisions, `_drive` lặp tới terminal; `judge_acceptance` gate (honor-system, evidence resolve trên artifacts).
- **DelegationManager** (`delegation/`): chokepoint RIÊNG (không phải method kernel — `delegation/manager.py:63`), policy engine, in-memory store, scripted + LangGraph adapter (`adapters/`); session con scope ⊆ parent.
- Consolidate Sprint 3/4 (commit `4377daa`): KernelSession + EventBus concurrency. Xây trên nền delegation Sprint 4.
- Thiết kế đầy đủ: `docs/spec/done/E10-multi-agent-graph/`.

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
