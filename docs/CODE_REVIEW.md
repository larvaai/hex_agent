# CODE REVIEW — toàn repository

> Review trên working tree ngày **2026-06-25**. Phạm vi: toàn bộ production source, frontend,
> config và test suite. Kết quả tự động: full suite xanh, optional Qdrant integration được skip khi
> service không chạy; `python -m ruff check .` sạch,
> `run_smoke.py` thành công.
>
> P1 = nên xử lý trước khi cho agent chạy với dữ liệu/quyền thật; P2 = correctness/operability
> đáng xử lý trong sprint gần; P3 = nhỏ hoặc latent.

## Kết luận

Nền tảng single-agent có boundary khá sạch: kernel shared/frozen, session cô lập, tool envelope
thống nhất, parent graph có checkpoint/resume và tests tốt. Khoảng trống lớn nằm ở safety thật của
terminal, semantics capability scope khi delegation, error propagation của LLM, và việc E09/E10
đã có class nhưng chưa được wire thành enforcement/lifecycle production.

## Findings

### P1 — `terminal_run` không bị giam trong workspace

**Vị trí:** `toolbox/terminal.py::Terminal.execute`, `safety/policy.py::classify_terminal`.

`cwd=workspace` chỉ đặt thư mục làm việc; process vẫn có thể đọc/ghi/xóa path tuyệt đối hoặc `..`.
Policy chặn một số executable/token, nhưng vẫn cho phép ví dụ `python -c` và executable tùy ý.
Vì toolbox bật mặc định, mô tả “workspace-sandboxed terminal” tạo cảm giác an toàn sai.

**Khuyến nghị:** dùng sandbox cấp OS/container/job object với filesystem allowlist, hoặc tắt
`terminal_run` mặc định. Deny-list argv không thay thế sandbox.

### P1 — explicit empty child scope bị đổi thành full parent scope

**Vị trí:** `core/session.py::SessionFactory.create_child`,
`delegation/policy.py::DelegationPolicyEngine.validate`, `supervisor/graph.py::run_round`.

Cả hai nơi dùng truthiness (`if not requested_scope`, `policy.allowed_capabilities or ...`). Vì vậy
`frozenset()` không có nghĩa “không tool”; nó kế thừa toàn bộ quyền parent. Trong Supervisor,
`AgentAssignment.allowed_capabilities=()` là default nên Agent O bỏ field sẽ vô tình cấp full scope,
trái với invariant “scope comes ONLY from O's assignment”.

**Khuyến nghị:** phân biệt `None` (inherit) và empty set (deny all) trong schema/policy; thêm test
Supervisor assignment rỗng phải tạo child scope rỗng.

### P1 — role/lens/team policy chưa enforce ở runtime

**Vị trí:** `roles/agent.py`, `roles/spec.py`, `roles/lenses.py`, `supervisor/graph.py`.

- Default UI không dựng `SkillRegistry/LensRegistry/AgentRegistry`.
- Supervisor chỉ dùng AgentRegistry làm role catalog; không gọi `Agent.guard_tool_call` hoặc
  `guard_finish`.
- `run_round` không kiểm tra assignment thuộc `selected_agents`, không intersect scope với
  `RoleView.default_scope`, không kiểm tra `may_route_to`.
- Lens `forbidden_tools` chỉ được render vào prompt. Ví dụ role `code` có allowlist `fs_write`
  nhưng lens `correctness` render `forbidden: fs_write`; guard vẫn cho phép.
- `ToolPolicy(repair_mode=True)` đã có unit/integration test thủ công, nhưng toolbox mặc định tạo
  `ToolPolicy()` và không có runtime transition nào bật repair mode sau failed validation.

**Khuyến nghị:** tạo một policy resolver code-side: selected team + route permission +
`assignment_scope ∩ role_scope ∩ parent_scope`; dùng cùng resolver trước create_child và tool call.

### P1 — lỗi LLM transport có thể được ghi nhận là run `completed`

**Vị trí:** `llm/adapter.py::call_llm`, `features/llm_chat.py::LLMChatTool.execute`,
`graph/nodes.py::agent_node/finish_node`, `ui/server.py::_effective_status`.

Adapter bắt exception và trả text JSON `{"action":"final","finish_reason":"error",...}`.
`LLMChatTool` vẫn trả `ok=True`; graph parse action rồi gọi `session.complete_task`; event/summary
cốt lõi vì vậy là completed và `llm_failures` không tăng. UI phải sửa hiển thị bằng cách soi
`finish_reason=error`, nhưng lifecycle và metrics vẫn sai.

**Khuyến nghị:** adapter trả typed failure/envelope hoặc raise exception đã phân loại để
`LLMChatTool` trả `ok=False`; `agent_node` phải xử lý failed envelope trực tiếp và route `fail`.

### P1 — raw tool/LLM args được ghi nguyên vào event log

**Vị trí:** `core/kernel.py::AgentKernel.execute_tool`, `observability/event_log.py`.

`tool.requested` chứa `args`; với `llm.chat`, args là toàn transcript. Secret, source code và PII có
thể nằm trong `events.jsonl`. Deep-copy/thread safety không giải quyết data exposure.

**Khuyến nghị:** descriptor-driven redaction; log digest, sizes và safe preview. Cho phép opt-in raw
payload ở môi trường dev, không mặc định.

### P1 — UI nạp JavaScript bên thứ ba vào origin có quyền đọc project/run

**Vị trí:** `ui/static/index.html` (Lucide từ `unpkg.com`), `ui/server.py` file/snapshot APIs.

Script CDN chạy trong origin của local UI nên có thể gọi `/api/file`, đọc source/run logs và gửi ra
ngoài. Không có SRI/CSP; UI cũng có thể được bind ra `0.0.0.0` mà không có auth.

**Khuyến nghị:** bundle icon script local, thêm CSP chặn script/network ngoài; nếu cho phép non-loopback
thì bắt buộc auth + CSRF/origin policy và cảnh báo startup.

### P2 — Supervisor kết thúc nhưng không đóng `KernelSession` lifecycle

**Vị trí:** `supervisor/loop.py::run_task_loop/_terminate`.

TaskLoop đổi `TaskLoopState.status` rồi return, nhưng không gọi
`supervisor_session.complete_task/fail_task`. Session vẫn active; thiếu `task.completed/failed`, state
`current_task` chưa clear và observer thấy lifecycle dang dở.

**Khuyến nghị:** một terminal finalizer duy nhất map FINISHED → complete, BLOCKED/FAILED → fail;
đảm bảo idempotent và test event/state.

### P2 — in-flight delegation chưa durable, resume vẫn có thể lặp side effect

**Vị trí:** `delegation/bootstrap.py`, `delegation/store.py`,
`adapters/agents/langgraph_agent.py`, `supervisor/checkpoint.py`, `supervisor/graph.py::run_round`.

Parent LangGraph và optional Supervisor Blackboard đều có SQLite. Supervisor còn save sau mỗi
completed turn và skip turn đó khi resume. Tuy nhiên delegation store và child checkpointer vẫn
in-memory: nếu process chết **trong** worker turn, trước khi turn được append/save, resume có thể tạo
child/side effect mới mà không có durable idempotency key.

TaskLoop checkpoint cũng không lưu current `OrchestratorDecision`, pending assignments, `Budget` hay
repeated-decision signature. Resume hỏi Agent O lại từ Blackboard; completed agent chỉ được skip nếu
decision mới giao lại đúng agent/round. Test hiện dùng scripted O tái phát cùng decision, nên chưa
chứng minh resume deterministic với LLM O.

**Khuyến nghị:** durable delegation ledger keyed by `delegation_id`; persist control state/pending
decision và discipline counters; resume/reconcile thay vì luôn tạo ID mới hoặc hỏi O lại mù.

### P2 — `run_id` đi thẳng vào filesystem path

**Vị trí:** `observability.event_log.EventLogger`, `orchestrator.checkpoint.checkpoint_*`.

Public Python APIs nhận arbitrary `run_id` rồi dùng `runs_dir() / run_id`; không validate basename
hay containment. UI tự sinh ID an toàn, nhưng caller khác có thể dùng `../...` hoặc absolute path.

**Khuyến nghị:** một `validate_run_id` dùng chung (strict charset/length) và containment check sau
`resolve`; từ chối reuse run ID đã có khi `run()` bắt đầu mới.

### P2 — descriptor-aware retry chưa được áp đúng cho built-in capabilities

**Vị trí:** `core/registry.py::ToolDescriptor`, `middleware/retry.py::Retry`, các feature installers,
`safety/policy.py::SafeToolPort`.

Kernel đã stamp descriptor vào envelope và Retry đã tránh `kind=effect,idempotent=false`. Nhưng các
built-in `fs_write`, `terminal_run`, RAG ingest, LLM... vẫn register bằng default `kind=tool`, nên
retry chưa biết effect thật. Ngoài ra policy block từ `SafeToolPort` nằm ở `data.policy_blocked`,
không phải `metadata.policy_block`, nên `_retryable` có thể gọi policy-blocked tool lặp lại.

**Khuyến nghị:** khai descriptor cho mọi built-in; chuẩn hóa mọi policy block thành cùng metadata
flag; thêm attempts metadata vào envelope/event.

### P2 — Supervisor compose/round input thiếu validation và budget hữu hiệu

**Vị trí:** `supervisor/graph.py::compose_team/run_round`, `supervisor/loop.py`.

Compose JSON hỏng làm raise thẳng, không dùng parse-error retry như `o_decide`. Team ID không được
validate với catalog. Một decision có thể chứa số assignment/tool request không giới hạn; Supervisor
Budget chỉ dùng parse errors, không record step/tool calls.

**Khuyến nghị:** schema validation + retry cho compose, max calls per round, record Budget steps và
reject unknown/unselected agents trước delegation.

### P2 — SSE snapshot làm full scan lặp lại

**Vị trí:** `ui/server.py::_stream`, `_read_events`, `tree_snapshot`, `run_snapshot`.

Mỗi SSE connection, mỗi 0,75 giây, đọc toàn bộ `events.jsonl`, scan đệ quy file tree, dựng JSON rồi
hash. Log/workspace lớn hoặc nhiều tab sẽ tăng I/O/CPU đáng kể; request thread tồn tại tới khi client
ngắt.

**Khuyến nghị:** tail event theo offset, cache tree theo mtime/watch service, event-driven queue và
giới hạn concurrent streams.

### P3 — một số contract nhỏ gây hiểu nhầm

- `FsWrite` trả field `bytes=len(content)`, thực tế là số Unicode code point; dùng
  `len(content.encode("utf-8"))` hoặc đổi tên `chars`.
- `ContextPacket` của `DeterministicBroker` có thể liệt kê `source_ids` bị cắt khỏi briefing do char
  budget; provenance nên chỉ giữ source thực sự xuất hiện.
- `InMemoryDelegationStore` khóa truy cập nhưng trả dataclass chứa dict/list tham chiếu; caller có thể
  mutate nested payload ngoài lock.
- `CapabilityRegistry.list_tools()` chưa expose `ToolDescriptor`, làm prompt/policy layer không biết
  kind/idempotency/risk.

## Test gaps ưu tiên

1. Empty assignment scope → child có zero capabilities.
2. LLM transport exception → lifecycle failed + `llm_failures=1`.
3. Supervisor terminal → root session closed đúng một lần.
4. Unknown/unselected worker và scope vượt role bị reject.
5. Terminal process cố đọc/ghi ngoài workspace bị chặn bởi sandbox thật.
6. Resume giữa delegation không lặp side effect.
7. Malformed team composition được retry có budget.
8. Unsafe `run_id` bị từ chối.
