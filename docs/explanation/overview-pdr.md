# Tổng quan dự án & Tuyên bố thiết kế (PDR)

Cập nhật: 2026-06-25 · Nguồn: core_agent · Sprint 4 / E21

## 1. Bài toán & Mục tiêu

**Vấn đề gốc:** Hệ thống agent đa-tác nhân dành cho tự động hóa phức tạp cần một kiến trúc mở rộng từ single-agent → multi-agent mà không phá vỡ observability, safety hoặc tracing. Các hệ thống trước đây không có chokepoint duy nhất, dẫn đến các tác nhân có thể bypass logging, bỏ qua chính sách bảo mật hoặc mất chi tiết dòng sự kiện.

**Mục tiêu của dự án:** xây dựng từ ground-up một nền tảng agent trên **các nguyên tắc hexagonal architecture (ports & adapters)**, nơi một **chokepoint duy nhất** (`AgentKernel.execute_tool`, `core/kernel.py:63`) làm cho observability, tracing, bảo mật và redaction **không thể vòng qua được**. Single-agent hoạt động trên một StateGraph được biên dịch; multi-agent mở rộng bằng một TaskLoop ngoài kernel.

**Ràng buộc:** Python 3.11, không có hạ tầng nặng (Postgres/Kafka/Redis) trong v1, offline-first (bộ nhớ như default, Qdrant là tùy chọn).

---

## 2. Những quyết định chính & lý do

### 2.1 Chokepoint duy nhất: `AgentKernel.execute_tool`

**Quyết định:** mọi hành động LLM và tool đều phải đi qua một điểm kiểm soát duy nhất.

**Lý do:**
- Observability không bị bypass: một sự kiện `tool.requested` → middleware chain → `tool.completed/failed` là bắt buộc cho tất cả các tool, kể cả LLM.
- Middleware có thể kiểm soát cross-cutting concerns (retry logic, policy enforcement, timing, budgets) mà không phải nhúng logic vào mỗi adaptor tool riêng.
- Tracing: `run_id ⊇ task_id ⊇ request_id` được ghi vào `events.jsonl` (observability/event_log.py:60) — bất kỳ cách nào gọi tool đều để lại dấu vết.
- Lineage bền: sự kiện được publish với đủ metadata (run_id, task_id, session_id, delegation_id) trước khi công việc được thực hiện (`core/kernel.py:72-82`).

**Chứng minh:** tất cả các tệp test trong `tests/` gọi tool thông qua `kernel.execute_tool()` hoặc thông qua orchestrator đại loại; không có "đường tắt" nào.

### 2.2 LLM là một Capability, không phải trường hợp đặc biệt

**Quyết định:** gọi LLM thông qua `kernel.execute_tool("llm.chat", args, context=...)` (`features/llm_chat.py`), không có method `kernel.llm_call()` riêng.

**Lý do:**
- Uniform transport: LLM events (`tool.requested/completed/failed` với `kind=LLMCallEvent`) được đếm như bất kỳ tool nào (observability/event_log.py:77-80).
- Middleware cũng áp dụng cho LLM: nếu bật retry hoặc policy gate, cả LLM và tool đều được che chắn.
- Tính nhất quán: lợi ích tương tự là gì từ toán tử graph hoặc từ một agent delegated — chúng đều `llm.chat` qua chokepoint.

**Chứng minh:** `features/llm_chat.py` định nghĩa một capability; `graph/nodes.py:51` gọi `kernel.execute_tool("llm.chat", ...)` trong agent node.

### 2.3 Một StateGraph thống nhất (Sprint 3 Consolidation)

**Quyết định:** một compiled LangGraph (`graph/runtime.py::build_agent_graph`, :31) làm việc cho cả single-agent (E05) và multi-agent qua injection — không phải hai loop riêng.

**Lý do:**
- Topology là sự thật (`graph/runtime.py:49-65`): `START → guard → agent → {tool | delegate | finish | fail} → ... → END`.
- State serializable: `AgentState` (graph/state.py:12) dùng `encode/decode_session_state` (`:18`) để marshal TaskEnvelope và các serializable primitive. Checkpoint SQLite (orchestrator/checkpoint.py:35) giữ graph state qua resume.
- Sprint 3 consolidation: tránh duy trì hai bộ machine-state (một handwritten loop, một LangGraph) đã dẫn đến divergence (theo CHANGELOG.md, dòng 23).

**Chứng miết:** Supervisor's TaskLoop (multi-agent, E10) reuse cùng graph qua delegation node (`graph/nodes.py:141`).

### 2.4 Delegation là một Chokepoint RIÊNG, không phải kernel method

**Quyết định:** `DelegationManager.delegate()` (delegation/manager.py:63) là một seam độc lập, không phải `kernel.delegate_to()`.

**Lý do:**
- Tách biệt các mối quan tâm: kernel nắm giữ shared frozen state (registry, middleware); delegation nắm giữ per-run child session, scope narrowing, policy enforcement.
- Scope enforcement: `SessionFactory.create_child()` (core/session.py:163) đảm bảo `allowed_capabilities` của child ⊆ parent's, không cho phép agent con tận dụng quyền mà cha không có.
- Policy không phải middleware: `DelegationPolicyEngine.validate()` (delegation/policy.py) kiểm tra độ sâu, ngân sách, scope; nó nằm bên ngoài kernel middleware chain vì áp dụng *trước* khi tạo child session.

**Chứng minh:** node `delegate` trong graph gọi `DelegationServicePort.delegate()` được inject vào (`supervisor/graph.py:173`); không có method kernel.

### 2.5 Hai lớp bảo mật được GIỮ CẢ HAI (cố ý không hợp nhất)

**Quyết định:** `PolicyGate` (middleware/policy.py:9) tồn tại song song với `SafeToolPort` (safety/policy.py:105); mỗi lớp kiểm tra khác nhau.

**Chứng minh:**
- **Layer A (PolicyGate):** deny-set tên công cụ ở chokepoint (core/bootstrap.py:28-32). Kích hoạt khi config có `middleware:` key; mặc định không dây.
- **Layer B (SafeToolPort):** bọc từng tool trong toolbox (toolbox/feature.py:19-36) với ToolPolicy: argv-only cho terminal, path-jail cho filesystem (`safety/policy.py:53` gọi `classify_terminal`), không có shell/git mutation/destructive commands.

**Tại sao giữ cả hai?** Một cặp mắt hơn là hoàn hảo, nhưng việc hợp nhất đã tạo ra "ý định duy nhất" khó bảo trì. Layer A có thể được cấu hình dynamically; Layer B là chuỗi logic cứng giữ workspace jail tránh path traversal (safety/sandbox.py:18). Rủi ro đã được ghi chép (KNOWN_RISKS.md, dòng 35).

**Chứng minh:** Nếu loại bỏ PolicyGate, tool không được phép mới sẽ vẫn có thể vượt qua nếu không có `SafeToolPort`. Nếu chỉ dùng deny-list, path traversal vẫn có thể xảy ra với tool filesystem. Cả hai đều cần để dự phòng.

### 2.6 SQLite là Nguồn Sự Thật duy nhất cho Resume

**Quyết định:** LangGraph checkpoint được lưu trong SQLite (`orchestrator/checkpoint.py:30` → `langgraph.sqlite`); `checkpoint.json` chỉ là dự phòng cho UI (không bao giờ được dùng để resume).

**Lý do:**
- Transactional safety: `SqliteSaver` (langgraph-checkpoint-sqlite) đảm bảo từng graph step được lưu trữ hoặc không; không có "vừa xong nửa chừng".
- Resume từ SQLite giữ nguyên run_id (orchestrator/loop.py:213) và task_id, dòng sự kiện không bị gián đoạn.
- Migration: `orchestrator/loop.py:146` đã xử lý nâng cấp từ `checkpoint.json` cũ (v1) lên SQLite (CHANGELOG.md, dòng 27).

**Chứng minh:** `resume()` đọc từ checkpoint DB, không từ JSON (`orchestrator/checkpoint.py:35` → `SqliteSaver.from_conn_string()`). Test `test_resume.py` kiểm tra sự hoàn toàn và idempotency.

### 2.7 KernelSession & SessionFactory: Per-run Isolation

**Quyết định:** Mỗi run tạo một `KernelSession` (core/session.py:49) qua `SessionFactory` (core/session.py:104); kernel bị freeze trước session đầu tiên (core/kernel.py:48).

**Lý do:**
- Không rò state giữa các run: `StateStore.snapshot/restore` (core/state.py) deep-copy mọi giá trị trạng thái, không alias.
- Scope enforcement: child session (qua delegation) không thể gọi tool ngoài `allowed_capabilities` của nó (core/session.py:163 → `PermissionError`).
- Per-run counters: task_id, session_id, agent_id được ghi vào event context; tracing có ý nghĩa.

**Chứng minh:** `orchestrator/loop.py:89` gọi `SessionFactory.create_root()` trước `run_agent()`. Khi delegation xảy ra, `DelegationManager.delegate()` gọi `sessions.create_child(scope=allowed_capabilities)`.

### 2.8 E21: Right-sizing Control Plane (Ports, không Heavy Infra)

**Quyết định:** `EventEmitter` (control/emitter.py:53) + `RuntimeCommand`/`RuntimeCheckpoint`/`Permission` contracts; EventSinkPort để swap backend; SQLite + JSONL cho MVP, không Postgres/Kafka/Redis ngay từ đầu.

**Lý sau:**
- Contracts đúng: `RuntimeEvent` (control/events.py:113), `RuntimeCommand` được validate có cấu trúc — UI không gửi text thô, nó gửi lệnh typed.
- Redaction được wire: `control/redaction.py::Redactor` (`:37`) đánh dấu 14 secret keys và mask payload trước khi gửi đến UI/SSE.
- Hạ tầng khả năng mở rộng: `EventSinkPort` (control/ports.py:15) cho phép swap `BusEventSink` (default) cho `KafkaEventSink`/`RedisEventSink` trong tương lai mà không đổi core.
- Offline-first: E21 Phase A (commit 7998c27) + B1 (commit f73d377) đã ship contracts + EventEmitter; transport/command-channel/approval-gate/interrupt vẫn trong backlog.

**Chứng minh:** `supervisor/graph.py:47` có `control_emitter` parameter (opt-in, default None); chỉ Supervisor sử dụng. Redactor hiện tại không được wire ở toàn bộ event stream (rủi ro đã biết, KNOWN_RISKS.md, dòng 33).

### 2.9 RAG: Optional Backend, Memory Default

**Quyết định:** RAG (E08, Qdrant) được cài đặt là tùy chọn (`pip install -e ".[rag]"`); bộ nhớ là default.

**Lý do:**
- Không có phụ thuộc bắt buộc: Qdrant client + fastembed nằm trong `[project.optional-dependencies]` (pyproject.toml:21).
- Health-gated: `RagService._require_healthy()` (rag/service.py:30) kiểm tra trạng thái trước ingest/search; nếu Qdrant không reachable, hệ thống thoái lui bằng cách phát `dependency_unavailable` event, không sập.
- Test không cần docker: `tests/test_rag_qdrant.py` cần docker-compose.rag.yml chạy, nhưng test suite mặc định chạy offline với FakeEmbedder.

**Chứng minh:** `config/features.yaml` có `rag: {backend: memory}` (mặc định); người dùng có thể chuyển sang `qdrant` nếu muốn.

---

## 3. Ràng buộc & Phi-mục tiêu

### Ràng buộc
- **Python 3.11** (pyproject.toml:5): Phiên bản tối thiểu để compat.
- **SQLite** (không multi-process safe cho write-heavy): Một instance per run, một khóa `_REPLACE_LOCK` trên Windows để tránh race (orchestrator/checkpoint.py:22).
- **Offline-first**: Hệ thống chạy mà không cần kết nối mạng (LLM và RAG đều optional).
- **Không có heavy infra trong v1**: Postgres, Kafka, Redis là nâng cấp tương lai (sau Port).

### Phi-mục tiêu (không ưu tiên cho v1)
- Parallel department / multi-department routing (E11 chỉ là string field trên RoleSpec).
- Global Supervisor với IntentRouter (E12 PRD draft).
- Ledger & persistent memory (E14).
- Self-evaluation & governance (E15).
- Software Factory (E13).

---

## 4. Các câu hỏi sản phẩm mở

### Từ E21 PRD
1. **Authentication cho POST /api/commands:** bây giờ localhost không xác thực. Khi mở rộng, người dùng có cần API key hay OAuth?
2. **Auto-approve cho checkpoint thấp rủi ro:** nên ai/cái gì quyết định? Config static hay nhân vào từng run?
3. **SSE retention:** bao lâu để giữ event stream trước khi purge? Kích thước bộ nhớ?

### Từ KNOWN_RISKS.md
1. **Redaction không được dây:** `core/kernel.py:79-82` ghi raw tool args vào `events.jsonl`; `control/redaction.py::Redactor` tồn tại nhưng chưa được gọi. Trước khi bật MCP write-tool, phải redact.
2. **Retry không biết idempotency:** middleware/retry.py hiện không wire, nhưng khi bật sẽ retry tất cả `ok=False` trừ policy_block. Chỉ retry tool nếu descriptor `idempotent=true`.
3. **checkpoint.json không phải sự thật:** dễ nhầm lẫn. Cần documentation rõ ràng: "read-only cho UI, SQLite là source-of-truth".

---

## 5. Trạng thái Epic

| Epic | Tên | Trạng thái | Ghi chú |
|---|---|---|---|
| E01 | Kernel | ✓ Xong | Chokepoint, registry, envelope, EventBus, KernelSession |
| E02 | Discipline | ✓ Xong | JSON parse/repair, finish-gate, budgets |
| E03 | LLM Adapter | ✓ Xong | OpenAI-compatible, JSON-mode, retry có exp-backoff |
| E04 | Observability | ✓ Xong | events.jsonl + summary.json + inspect CLI |
| E05 | Single-agent LangGraph | ✓ Xong | StateGraph, topology guard→agent→tool→finish |
| E06 | Tools & Safety | ✓ Xong | SafeToolPort, path-jail, argv-only terminal |
| E07 | Skills | ✓ Xong | Role-agnostic contracts, allowlist derivation |
| E08 | RAG (Qdrant) | ✓ Xong | Optional backend, health-gated, memory default |
| E09 | Roles & Lenses | ✓ Xong | allowed_tools derivation, skill cycle-break |
| E10 | Multi-agent TaskLoop | ✓ Xong | Agent-O, delegation node, scope narrowing |
| E21 | Realtime Control Plane | 🟡 Partial | Phase A (contracts) + B1 (EventEmitter); transport/command-gate/approval PENDING |
| E11 | Departments | ❌ Không bắt đầu | Chỉ string field trên RoleSpec |
| E12 | IntentRouter | ❌ PRD draft | Supervisor loop là E10, không E12 |
| E13 | Software Factory | ❌ Không bắt đầu | |
| E14 | Ledger & Memory | ❌ Không bắt đầu | |
| E15 | Self-eval | ❌ Không bắt đầu | |
| E19 | Test Harness | ✓ Xong | ~327 test functions, no-xfail rule, CI gates |
| E20 | Labs | ❌ Không bắt đầu | |

---

## 6. Liên hệ

Đối với chi tiết triển khai, xem:
- [runtime-flow.md](../reference/runtime-flow.md) — luồng chạy từ input → output.
- [known-risks.md](../reference/known-risks.md) — tệp dễ vỡ, rủi ro hành vi.
- [spec/](../spec/) — thiết kế epic-by-epic.
- [plans/reports/architecture-map-260625-2009-hex-agent-report.md](../../plans/reports/architecture-map-260625-2009-hex-agent-report.md) — sơ đồ kiến trúc chi tiết (file:line).
