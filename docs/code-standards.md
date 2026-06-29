# Tiêu chuẩn viết mã — quy tắc bất biến mà đóng góp phải giữ

Cập nhật: 2026-06-25 · Nguồn: core/kernel.py, graph/state.py, delegation/manager.py, reference/runtime-flow.md, reference/known-risks.md, getting-started.md

Repo này là một **microkernel hexagonal** (epics E01–E21). Những quy tắc dưới đây là các bất biến mà mỗi thay đổi code PHẢI bảo vệ. Nếu sửa và vô tình vi phạm một điều khoản nào, bạn sẽ phá hệ thống mà có thể không biết được cho đến khi chạy.

## 1. Bất biến kiến trúc (mỗi bất biến có file:line để kiểm chứng)

### 1.1 Chokepoint đơn lẻ: `execute_tool`

**Bất biến:** Mọi hành động LLM **và** tool, không ngoại lệ, đều đi qua `AgentKernel.execute_tool` (`core/kernel.py:63`).

**Vì sao:** Đây là nơi duy nhất để:
- Publish `tool.requested` / `tool.completed/failed` (observability).
- Kiểm tra `allowed_capabilities` (security).
- Wrap với middleware (policy, retry, budget).
- Chuẩn hóa output thành `CapabilityResult` envelope.

**Nếu vi phạm:** Mất observability/audit đối với toàn bộ hệ thống, hoặc tool có thể làm sập kernel (exception không bị bắt).

**Cách giữ:**
- Không thêm đường thực thi tool ngoài `execute_tool`.
- Không bỏ `try/except` bọc executor ở `core/kernel.py:110-125`.
- Giữ thứ tự event: `tool.requested` → chain → `tool.completed|failed`.
- LLM là capability `llm.chat` (xem 1.2).

**Kiểm chứng:** `python -m pytest tests/test_kernel.py tests/test_trace_ids.py -q`

---

### 1.2 LLM không có đường tắt

**Bất biến:** LLM là một capability thường thường (`llm.chat`, `features/llm_chat.py:12`), không một phương thức kernel. Mọi cuộc gọi LLM phải đi qua `execute_tool` và `scope` check.

**Vì sao:** LLM cần quan sát (observe) giống mọi tool để đếm steps, thử lại nếu cần, và audit.

**Nếu vi phạm:** Code gọi LLM trực tiếp sẽ bỏ qua budget/policy/event, dẫn đến:
- Không đếm LLM call vào step budget.
- Không emit `tool.requested/completed`.
- Khó trace lại hành động.

**Cách giữ:**
- Mọi LLM call phải qua `session.execute_tool("llm.chat", {...})`.
- Nếu cần LLM ở nơi không có session (ví dụ supervisor `llm.py:64`), inject một hàm thực thi qua `execute_tool`.

---

### 1.3 Kernel đóng băng, KernelSession chứa trạng thái per-run

**Bất biến:**
- `AgentKernel.freeze()` (`core/kernel.py:48`) được gọi trước session đầu tiên. Sau đó:
  - Registry, config, middleware pipeline không thể sửa.
  - Thử gọi `kernel.use()` sẽ raise `RuntimeError`.
- Mọi **trạng thái per-run** sống trong `KernelSession` (`core/session.py`): identity, state dict, messages, outcome.

**Vì sao:** Kernel được chia sẻ giữa nhiều run cùng lúc (multi-run async). Không đóng băng → state từ run A tô màu lên run B.

**Nếu vi phạm:** State rò giữa các run, hoặc middleware được thêm sau khi có session (một nửa run dùng cái cũ, nửa dùng cái mới).

**Cách giữ:**
- Gọi `kernel.freeze()` trước `run()` / `resume()` lần đầu.
- Không sửa config dict sau freeze.
- Ghi config / middleware từ file YAML trước freeze.

**Kiểm chứng:** `python -m pytest tests/test_kernel.py -q`

---

### 1.4 SessionFactory kiểm soát scope con ⊆ scope cha

**Bất biến:** `SessionFactory.create_child()` (`core/session.py:163`) buộc con phải có `allowed_capabilities ⊆ cha.allowed_capabilities`. Vi phạm → raise `PermissionError`.

**Vì sao:** Con không được phép "leo quyền" so với cha (delegation/multi-agent safety).

**Nếu vi phạm:** Child session (delegation target) được thêm capability cha không cho phép → escape scope.

**Cách giữ:**
- Mọi delegation phải tạo child qua `SessionFactory.create_child()`, không tạo session mới.
- Không hardcode `allowed_capabilities` cho con; lấy từ parent → DelegationPolicy.

**Kiểm chứng:** `python -m pytest tests/test_delegation.py -q`

---

### 1.5 AgentState chỉ chứa primitive + encoded values; codec `encode/decode_session_state`

**Bất biến:** `AgentState` (`graph/state.py:12`) là một `TypedDict` chỉ chứa:
- Primitive: `str`, `int`, `bool`, `dict[str, Any]`, `list`.
- Hoặc các giá trị **đã encode** (ví dụ `TaskEnvelope` → dict).

Mọi giá trị non-primitive lưu trong `session.state` phải được handle trong `encode_session_state()` (`graph/state.py:42`) + `decode_session_state()` (`graph/state.py:51`).

**Vì sao:** `AgentState` checkpoint vào SQLite. SQLite không serialize dataclass/object → checkpoint.json sẽ corrupt, hoặc resume sẽ load sai.

**Nếu vi phạm:** Sau khi checkpoint và resume, dữ liệu non-primitive bị mất hoặc transform sai.

**Cách giữ:**
- Mỗi khi thêm field mới vào `session.state`, nếu có object:
  - Thêm logic encode / decode.
  - Tăng `schema_version` → `3` (code phòng vệ ở `graph/state.py:64`).
  - Viết test: `tests/test_resume.py` phải xanh.

**Kiểm chứng:** `python -m pytest tests/test_state.py tests/test_checkpoint.py tests/test_resume.py -q`

---

### 1.6 SQLite là sự thật resume; checkpoint.json là projection cho UI

**Bất biến:**
- **Thật:** `var/agent_runs/<run_id>/langgraph.sqlite` (LangGraph's `SqliteSaver`, `orchestrator/checkpoint.py:35`).
- **Projection (UI):** `var/agent_runs/<run_id>/checkpoint.json` (ghi sau mỗi step, `orchestrator/loop.py:…`).
- `resume()` (`orchestrator/loop.py:213`) **chỉ** đọc SQLite, không checkpoint.json.

**Vì sao:** SQLite là `langgraph` engine state. `checkpoint.json` là readable snapshot cho observability UI — nó có thể delay, bị mất, hoặc sai khác so với SQLite (không đồng bộ).

**Nếu vi phạm:** Một khi bạn resume từ JSON → bạn mất node được chạy rồi (vì JSON không theo kịp) hoặc chạy lại node cũ (idempotency footgun).

**Cách giữ:**
- Không bao giờ gọi `resume()` dựa vào `checkpoint.json`.
- `resume()` luôn mở SQLite: đọc `get_state()`, restore session, tiếp tục `stream()`.
- Chỉ migrate từ JSON cũ (trước khi dùng LangGraph) một lần (`_legacy_state` ở `orchestrator/loop.py:146`).

**Kiểm chứng:** `python -m pytest tests/test_resume.py tests/test_checkpoint.py -q`

---

### 1.7 Budget split: graph nodes (không kernel middleware)

**Bất biến:** Kiểm soát step/parse/same-tool budget **ở graph node**, không middleware:
- `guard` node chặn `steps >= max_steps`.
- `tool` node chặn `same_tool_exceeded`.
- `agent` node quay lại khi `parse_errors >= max_parse`.

**NOT:** `BudgetGuard` middleware (`core/bootstrap.py:28-32`) **cố ý không** wire ở kernel vì bộ đếm là **per-run** state (thuộc `AgentState`, không kernel).

**Vì sao:** Kernel là shared object; budget phải per-run.

**Nếu vi phạm:** Thêm BudgetGuard ở middleware → state rò giữa runs.

**Cách giữ:**
- Không bật `BudgetGuard` ở `middleware` config.
- Sửa budget → sửa `guard`/`agent`/`tool` node ở `graph/nodes.py`, không middleware.

---

### 1.8 Delegation là seam tách biệt, không kernel method

**Bất biến:** `DelegationManager.delegate()` (`delegation/manager.py:63`) là **chokepoint riêng**, không một phương thức của `AgentKernel`. Nó:
1. Validate policy.
2. Tạo child session (kiểm scope).
3. Chạy handler (scripted / langgraph).
4. Publish event riêng (`delegation.started/finished`).

**Vì sao:** Delegation là một operation **compound** (scope + policy + handler), không phải một tool call. Để giữ separation-of-concerns.

**Nếu vi phạm:** Sợ nó sẽ sợi vào kernel logic, khó test, khó mở rộng (ví dụ, thêm một delegation handler type).

**Cách giữ:**
- Delegation luôn qua `DelegationServicePort.delegate()` (inject vào supervisor).
- Không gọi `kernel.execute_tool()` trực tiếp để delegate.
- Node `delegate` ở graph gọi `delegation_service.delegate()`.

---

### 1.9 Hai lớp safety: PolicyGate (middleware) + SafeToolPort (per-tool)

**Bất biến:** Có **hai lớp song song**:

1. **Lớp A (PolicyGate middleware):** `middleware/policy.py:15`. Đơn giản name deny-list ở kernel level. **Mặc định tắt** (không có section `middleware:` ở config).
2. **Lớp B (SafeToolPort):** `safety/policy.py:105`. Mỗi tool (fs/terminal) có một port wrapper riêng:
   - Check `classify_terminal` (argv-only, không shell, không abs-path escape).
   - Wrap path qua `resolve_in_workspace` (`safety/sandbox.py:18`).
   - Emit `tool.completed/failed` như bất kỳ tool nào.

**Vì sao:** Lớp A ngăn cấp toàn cầu (khi bật). Lớp B ngăn cấp từng tool (luôn bật). Cả hai giữ lại (không loại bỏ) do hiếm khi bảo mật "quá". Đó là quyết định thiết kế.

**Nếu vi phạm:** Thêm tool ngoài toolbox (bỏ qua SafeToolPort) mà không bật PolicyGate → tool không có safety kiểm tra.

**Cách giữ:**
- Tool mới ở `toolbox/` phải register qua `toolbox/feature.py` `:19-36` (tự động wrap `SafeToolPort`).
- Tool ngoài toolbox: bật `middleware.policy` hoặc tự wrap tương đương.
- Luôn gọi `resolve_in_workspace()` trước đọc/ghi file.

**Kiểm chứng:** `python -m pytest tests/test_safety.py tests/test_toolbox.py -q`

---

## 2. Kỷ luật hexagonal: Ports → Adapters

**Quy tắc:** Mỗi điểm tích hợp bên ngoài (LLM, RAG, delegation handler) là một **Port** (Protocol) trước.

| Điểm tích hợp | Port | Adapters | File |
|---|---|---|---|
| LLM | (implicit, `llm.chat` capability) | `llm/adapter.py` (lazy OpenAI) | `llm/adapter.py:53` |
| RAG | `EmbedderPort` / `VectorStorePort` | memory, qdrant | `rag/ports.py:25/:32` |
| Delegation handler | `DelegationPort` | scripted, langgraph | `delegation/registry.py` |
| Event sink | `EventSinkPort` | `BusEventSink` (v1), Kafka/Redis (T2) | `control/ports.py:15` |

**Cách giữ:**
- Định nghĩa port trước (Protocol ở `ports.py`).
- Implement adapter từ port (cụ thể: `_qdrant.py`, `_memory.py`).
- Code dùng port, không biết cái adapter nào.

---

## 3. Quy ước đặt tên

| Loại | Quy ước | Ví dụ | File |
|---|---|---|---|
| Module Python | `snake_case` | `llm_chat`, `dispatch_gate` | pyproject.toml:38-58 |
| Function / method | `snake_case` | `execute_tool()`, `resolve_in_workspace()` | code |
| Class | `PascalCase` | `AgentKernel`, `KernelSession` | code |
| Docstring dòng đầu | `"""<mục đích 1 dòng>. Epic Exx."""` | `features/llm_chat.py:1` | getting-started.md |
| Config key | `kebab-case` (YAML) | `rag: backend`, `delegation: enabled` | config/features.yaml |
| Env var | `UPPER_SNAKE_CASE` | `LLM_MODEL`, `AGENT_WORKSPACE_DIR` | llm/adapter.py:15-21 |
| Commit message | `feat(Exx): …` | `feat(E06): Sandbox fs tools + safety chokepoint` | getting-started.md |

---

## 4. Kỷ luật TDD

**Quy tắc:** (từ `harness/rules/tdd-discipline.md`)

1. **Test trước:** Viết test, chạy đỏ (không fake).
2. **Code đủ để xanh:** Min code.
3. **Chạy full suite:** `python -m pytest -q` phải xanh (cả `tests/` và `tests_audit/`).
4. **Commit cặp:** Test + code, một commit.
5. **Không weakening:** Nếu test đỏ, fix code — không xóa/skip test hoặc hạ thấp assertion.

**Công cụ:**
- Acceptance criteria ở `docs/spec/{done,active}/Exx*/acceptance.md`.
- Test phản chiếu AC (ví dụ: `tests/test_kernel.py` test chokepoint, `tests/test_resume.py` test persist).

**Kiểm chứng:**
```bash
python run_smoke.py                      # CORE_AGENT_SMOKE_OK
python -m pytest -q                      # lõi (cũng gồm test resume/delegation/concurrency)
python -m pytest tests_audit/ -q --tb=no # adversarial (no-xfail, no-weakened-assertion)
```

---

## 5. "Khi THÊM file" — quy trình giữ repo traceable

(từ `getting-started.md`)

1. **Docstring dòng đầu:** `"""<mục đích 1 dòng>. Epic Exx."""` → tự sinh vào MAP.md.
2. **Viết test** map tới acceptance criteria.
3. **Cập nhật CHANGELOG.md:** Một dòng cho epic/feature, thời gian sprint.
4. **Regen MAP.md:** `python tools/gen_map.py` (đọc docstring).
5. **Commit:** `feat(Exx): ... `

**Ví dụ:**
```python
"""LLM exposed as a capability. Epic E03."""
# ↓
# In MAP.md:
# features/llm_chat.py — LLM exposed as a capability. Epic E03.
```

---

## 6. Env var + config

### Env var (mặc định từ `llm/adapter.py:13-22`)

| Biến | Mặc định | Kiểu | Ý nghĩa |
|---|---|---|---|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | URL | OpenAI-compatible endpoint |
| `LLM_API_KEY` | `lm-studio` | str | API key |
| `LLM_MODEL` | `local-model` | str | Model name |
| `LLM_MAX_TOKENS` | `2048` | int | Max output tokens |
| `LLM_TIMEOUT` | `120` | float | Socket timeout (giây) |
| `LLM_MAX_RETRIES` | `2` | int | Retry transient failures |
| `LLM_RETRY_BASE` | `0.5` | float | Exp backoff base |
| `AGENT_WORKSPACE_DIR` | `var/workspace` | path | Workspace path-jail root |
| `AGENT_ALLOW_GIT_MUTATIONS` | (không set) | bool | Nếu set → `git` tool cho phép write |
| `AGENT_RUNS_DIR` | `var/agent_runs` | path | Lưu run logs/checkpoints |

### Config YAML (`config/features.yaml`)

```yaml
features:
  <feature>:
    enabled: true|false
    module: package.module
```

Plugin phải có hàm `install(kernel: AgentKernel)` để register tool/feature (tự động gọi ở `features/loader.py:10`).

---

## 7. File dễ vỡ nhất + test khi sửa

(Tóm tắt từ KNOWN_RISKS.md Phần 1)

| File | Bất biến | Nếu sửa ẩu → vỡ | Test |
|---|---|---|---|
| `core/kernel.py` | Chokepoint `execute_tool` | Mất observability toàn bộ | `test_kernel.py`, `test_trace_ids.py` |
| `graph/state.py` | Serializable only | Resume vỡ âm thầm | `test_state.py`, `test_resume.py` |
| `orchestrator/loop.py` + `checkpoint.py` | SQLite sự thật | Mất progress hoặc lặp node | `test_checkpoint.py`, `test_resume.py` |
| `graph/runtime.py` + `nodes.py` | Topology + lifecycle | Loop vô tận / không terminate | `test_graph.py`, `test_orchestrator.py` |
| `delegation/manager.py` + `policy.py` | Separate chokepoint + scope ⊆ | Đệ quy vô tận / escape quyền | `test_delegation.py` |
| `safety/sandbox.py` + `policy.py` | Workspace jail + no-shell | Path escape / shell injection | `test_safety.py`, `test_toolbox.py` |

---

## 8. Tóm tắt kiểm chứng nhanh

```bash
# Mọi lần sửa xong
python run_smoke.py                      # CORE_AGENT_SMOKE_OK
python -m pytest -q                      # phải xanh

# Nếu sửa một trong 6 file "dễ vỡ" → chạy test tương ứng ở bảng trên
python -m pytest tests/test_kernel.py -q          # chokepoint
python -m pytest tests/test_resume.py -q          # persist + resume
python -m pytest tests/test_delegation.py -q      # scope con
python -m pytest tests/test_safety.py -q          # workspace
```

---

## Tài liệu liên quan

- [runtime-flow.md](./reference/runtime-flow.md) — luồng chạy của một task.
- [known-risks.md](./reference/known-risks.md) — rủi ro hành vi + footgun.
- [getting-started.md](./getting-started.md) — cách đọc repo khi lớn.
- [Codebase Map](../plans/reports/architecture-map-260625-2009-hex-agent-report.md) — toàn bộ file + trách nhiệm.
- `docs/spec/{done,active}/Exx*/acceptance.md` — acceptance criteria per epic.
