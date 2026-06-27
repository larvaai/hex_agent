---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Microkernel, chokepoint & observability

> Epic: E01 + E04 · Cổng vào: (nền, không deps) · Rời phase với: `python run_smoke.py` in `CORE_AGENT_SMOKE_OK`, mỗi run ghi `events.jsonl`+`summary.json`, `inspect` CLI đọc lại được.

## 1. Mục tiêu & ranh giới

Dựng **cái lõi sống tối thiểu**: một kernel dùng chung, đóng băng, có **đúng một cửa** cho mọi
hành động (`execute_tool`), và một lớp observability bám vào cửa đó để **không bỏ sót một call nào**.

Trong phase này:
- Kernel đăng ký tool → resolve → execute → trả **envelope chuẩn** (`CapabilityResult`).
- Mọi call publish event có **lineage** đầy đủ; logger ghi xuống `events.jsonl` + `summary.json` + metrics.
- State theo-run cô lập trong `KernelSession`; kernel chia sẻ thì `freeze()` trước session đầu.

**Chưa** có trong phase này: LLM (Phase 2), toolbox/safety jail (Phase 3), graph/resume (Phase 4),
delegation (Phase 6). Ở đây chỉ có `echo` — một tool đồ chơi để chứng minh cái khung chạy đúng.

Ranh giới hexagonal: `core/` **không import** LangGraph/OpenAI/Qdrant. Hành vi cụ thể nằm sau
`ToolPort` (`core/ports.py:20`); cross-cutting nằm trong middleware quanh cửa. Đổi hạ tầng = viết adapter, không sửa lõi.

## 2. Bạn sẽ xây gì (bản đồ module)

| file | vai trò 1 dòng | class/hàm chính |
|---|---|---|
| `core/schemas.py` | hợp đồng dữ liệu (envelope, request, lineage) | `TaskEnvelope`, `ToolRequest`, `ToolCallContext`, `CapabilityResult`, `FeatureDescriptor` |
| `core/ports.py` | seam mọi tool implement | `ToolPort` (Protocol, `runtime_checkable`) |
| `core/registry.py` | tên tool → executor, có fallback | `CapabilityRegistry`, `NullToolPort`, `ToolResolution`, `ToolDescriptor` |
| `core/events.py` | pub/sub thread-safe, giao detached | `EventBus` |
| `core/kernel.py` | **cửa duy nhất** + middleware chain | `AgentKernel.execute_tool`, `freeze`, `use`, `_wrap`, `_LatchedNext` |
| `core/state.py` | state theo-run, snapshot/restore deep-copy | `StateStore` |
| `core/session.py` | vòng đời + scope một task | `KernelSession`, `SessionFactory`, `SessionIdentity` |
| `core/middleware.py` | hợp đồng pre/post quanh cửa | `ToolMiddleware` (Protocol) |
| `observability/event_log.py` | bám EventBus → JSONL + summary + metrics | `EventLogger`, `attach_to_bus` |
| `observability/inspect.py` | CLI đọc lại run | `read_events`, `read_summary`, `list_runs`, `main` |
| `core/bootstrap.py` | ráp kernel từ config | `build_kernel`, `create_kernel`, `load_config` |
| `features/loader.py` | cài feature enabled trong config | `install_configured_features` |
| `features/example_echo.py` | feature mẫu = pattern plugin | `EchoTool`, `install`, `FEATURE` |
| `run_smoke.py` | smoke quyết định, no LLM/network | `main` |

## 3. Dựng step-by-step

Thứ tự xây = thứ tự phụ thuộc. Mỗi bước là **một mảnh chạy được** + cách tự kiểm ngay.

**B1 — Schemas (hợp đồng trước tiên).** Viết `core/schemas.py`: `ToolRequest` (name+args+context+`request_id`
auto, `schemas.py:28`), `ToolCallContext` (lineage bất biến, `schemas.py:36`), `CapabilityResult` envelope
6 khóa cố định `ok/capability/feature/data/error/metadata` (`schemas.py:63`), `FeatureDescriptor`,
`TaskEnvelope`. Mọi dataclass `frozen=True`. *Tự kiểm:* `CapabilityResult.from_raw(...)` gói được cả dict
thô lẫn dict đã-là-envelope (`schemas.py:74`).

**B2 — Port (seam tool).** Viết `core/ports.py`: `ToolPort` Protocol có `name` + `execute(request)->dict`
(`ports.py:20`). `runtime_checkable` để test `isinstance`. Đây là chỗ *duy nhất* tool đời thực phải khớp.

**B3 — Registry + fallback.** Viết `core/registry.py`. `register_tool/register_tools` (`registry.py:67`),
`resolve_tool` ưu tiên khớp chính xác → `_fallback` → `NullToolPort` (`registry.py:103`). `NullToolPort.execute`
trả `ok=False, missing_capability=True` thay vì ném (`registry.py:34`) — **tool thiếu không làm sập runtime**.
`freeze()` khóa đăng ký (`registry.py:60`). *Tự kiểm:* resolve tên lạ → ra `null_tool`, không exception.

**B4 — Kernel + chokepoint (trái tim phase).** Viết `core/kernel.py`. `execute_tool` (`kernel.py:106`) chạy
đúng trình tự: deep-copy args → publish `tool.requested` → **scope check** → middleware chain bọc `core`
→ `registry.resolve_tool` → `executor.execute` trong try/except → chuẩn hóa `CapabilityResult` →
publish `tool.completed|failed`. `freeze()` (`kernel.py:91`) đóng băng registry+config; `use()` (`kernel.py:100`)
ném nếu đã frozen. *Tự kiểm:* gọi tool ném exception → envelope `ok=False, kernel_error=True`, kernel vẫn sống.

**B5 — Events + Session + State.** `core/events.py` `EventBus.publish` (`events.py:22`): chụp subscriber
trong lock rồi giao **ngoài** lock, mỗi observer nhận **bản deep-copy riêng**, observer ném thì nuốt
(`events.py:29`). `core/state.py` `StateStore.snapshot/restore` deep-copy (`state.py:21`). `core/session.py`:
`SessionFactory.create_root` gọi `kernel.freeze()` rồi publish `task.accepted` (`session.py:141`);
`KernelSession.execute_tool` bơm `call_context()` vào kernel (`session.py:75`). *Tự kiểm:* `test_snapshot_not_affected_by_later_set`.

**B6 — Observability.** `observability/event_log.py`: `EventLogger.emit` append-JSONL có seq+timestamp+run_id
(`event_log.py:60`); `attach_to_bus` subscribe một `sink` mirror mọi event + đếm metrics (`event_log.py:102`).
`finish()` ghi `summary.json` đúng một lần (`event_log.py:80`). `observability/inspect.py`: CLI `list/summary/events`
đọc lại. *Tự kiểm:* `python -m observability.inspect summary latest`.

**B7 — Bootstrap + feature loader.** `core/bootstrap.py` `build_kernel` ráp `AgentKernel(registry, events, config)`,
gọi `install_configured_features` rồi wire middleware (`bootstrap.py:56`). `features/loader.py` import động
module mỗi feature enabled, gọi `install(kernel)` (`loader.py:10`). `features/example_echo.py` `install`
đăng ký `FEATURE` + `EchoTool` cho cap `echo` (`example_echo.py:23`). *Tự kiểm:* `build_kernel(ECHO).describe_capabilities()` thấy `echo`.

**B8 — run_smoke (cổng đóng phase).** `run_smoke.py` ráp kernel+logger, chạy `echo`, chứng minh:
envelope `ok` + `metadata.task_id` truy vết được (`run_smoke.py:18-20`), tool ngoài scope bị chặn
(`run_smoke.py:22-23`), lifecycle đóng (`run_smoke.py:31-32`), in `CORE_AGENT_SMOKE_OK` (`run_smoke.py:35`).

## 4. Class & biến kiểm soát (cái neo)

| class/biến `file:line` | giữ invariant gì | sai thì mất gì |
|---|---|---|
| `AgentKernel.execute_tool` `kernel.py:106` | mọi call đi qua đúng một cửa; try/except quanh executor | mất observability+safety+envelope cho *toàn bộ* call; tool ném làm sập kernel |
| `AgentKernel.freeze` `kernel.py:91` | đóng băng registry+config trước session đầu | sửa config giữa chừng → state rò giữa run |
| `ToolCallContext` `schemas.py:36` + `event_fields()` `:48` | lineage bất biến, **không bao giờ** lọt vào args tool | không truy vết được ai gọi gì |
| `CapabilityResult` `schemas.py:63` + `from_raw` `:74` | mọi call trả về cùng 6-khóa envelope | caller phải đoán hình dạng kết quả mỗi tool |
| `NullToolPort.execute` `registry.py:34` | tool thiếu → `ok=False`, không ném | một tool chưa đăng ký làm crash cả run |
| `StateStore.snapshot/restore` `state.py:21` | deep-copy, không alias state giữa session | hai run xài chung mutable → nhiễm chéo |
| `EventBus.publish` `events.py:22` | giao detached + deep-copy + nuốt lỗi observer | một observer hỏng làm gãy runtime |
| `_LatchedNext` `kernel.py:24` | `nxt` one-shot cho middleware fail-open | middleware advisory raise sau `nxt` → chạy lại tool (FM-HIGH) |

Cửa — trình tự bất biến (rút gọn từ `kernel.py:106`):

```python
def execute_tool(self, tool_name, args=None, *, context=None):
    request = ToolRequest(name=tool_name, args=copy.deepcopy(args) if args else {}, context=context)
    lineage = context.event_fields() if context is not None else {...}      # run_id/task_id/...
    self.events.publish("tool.requested", {**lineage, "tool": request.name,
                                           "request_id": request.request_id, "args": request.args})
    if context and context.allowed_capabilities is not None \
            and request.name not in context.allowed_capabilities:
        ... return scope_block envelope + publish "tool.failed"               # scope check
    handler = core                                                           # core = resolve+execute
    for mw in reversed(self._middlewares):                                   # bọc reversed (outer→inner)
        handler = _wrap(mw, handler, on_skip=on_skip)
    try: envelope = handler(request)
    except Exception as exc: envelope = CapabilityResult(ok=False, ...).as_dict()  # mw không sập cửa
    self.events.publish("tool.completed" if envelope.get("ok") else "tool.failed", {...})
    return envelope
```

Lõi không bao giờ để tool làm sập kernel (`kernel.py:152`):

```python
def core(req):
    resolution = self.registry.resolve_tool(req.name)
    try:
        result = resolution.executor.execute(req)
    except Exception as exc:                       # một tool KHÔNG được crash kernel
        result = {"ok": False, "tool": req.name, "error": str(exc), "kernel_error": True}
    return CapabilityResult.from_raw(capability=req.name, feature=resolution.feature,
                                     result=result, metadata={**lineage, ...}).as_dict()
```

**Thứ tự middleware — `use()` đăng ký ngoài→trong, kernel bọc reversed quanh `core`.**
`ToolMiddleware` (`middleware.py:11`) là một callable `(request, nxt) -> dict`: nó act *trước* (sửa request),
gọi `nxt` để đi vào trong, rồi act *sau* (sửa envelope) — hoặc short-circuit (không gọi `nxt`). Bạn đăng ký
theo thứ tự **ngoài→trong** (`kernel.py:100`); cửa xây handler bằng cách bọc `reversed(self._middlewares)`
quanh `core` (`kernel.py:193`), nên middleware đăng ký *đầu* là lớp *ngoài cùng* — thấy request sớm nhất,
thấy envelope muộn nhất. Ví dụ wire `[timing, policy, retry, condense]` (`bootstrap.py:36-53`) → request đi
`timing → policy → retry → condense → core`, envelope về ngược lại. Đây là vì sao `timing` đo được cả
thời gian của các lớp trong, còn `policy` chặn sớm trước khi tốn công retry. Posture mặc định **fail-closed**:
middleware raise → propagate ra biên cửa (`ok=False`); chỉ ai khai `fail_open=True` (advisory: telemetry/condense)
mới được skip khi raise (`kernel.py:58`, `middleware.py:14-20`).

`freeze()` đóng băng cái chia sẻ trước session đầu (`kernel.py:91`):

```python
def freeze(self):
    if self._frozen: return
    self.registry.freeze()
    self.config = _deep_freeze(copy.deepcopy(dict(self.config)))   # config bất biến từ đây
    self._frozen = True
```

## 5. Invariant của phase

Bốn invariant nền (trùng **I1–I4** trong [README.md](README.md) §2):

- **I1 — Một cửa duy nhất.** Mọi tool đi qua `AgentKernel.execute_tool` (`kernel.py:106`). Không đường tắt.
- **I2 — Kernel đóng băng trước session đầu.** `freeze()` (`kernel.py:91`) khóa registry+config; `use()` sau freeze ném (`kernel.py:102`).
- **I3 — State theo-run cô lập khỏi kernel.** `KernelSession` giữ `StateStore` riêng; snapshot/restore deep-copy (`state.py:21`) → không alias giữa session.
- **I4 — Lineage gắn vào mọi event.** Mọi event mang `run_id/task_id/session_id/parent_session_id/delegation_id/actor_id` từ `ToolCallContext.event_fields()` (`schemas.py:48`).

Phụ trợ (không đánh số nhưng phải giữ):
- Envelope đồng nhất: mọi call trả `CapabilityResult.as_dict()` 6-khóa (`schemas.py:103`).
- Observer cô lập: một observer hỏng không gãy runtime (`events.py:29`); `args` được deep-copy nên tool không sửa được object của caller (`kernel.py:114`).

## 6. Pitfall / bug sẽ gặp

**P1 — Log raw `args` vào `events.jsonl` (🔴 LIVE).**
**Triệu chứng:** secret/API-key/PII truyền qua tool args nằm nguyên văn dưới `var/agent_runs/<run_id>/events.jsonl`.
**Nguyên nhân:** `tool.requested` publish cả `"args": request.args` (`kernel.py:123-126`, cụ thể dòng `:125`),
logger mirror nguyên vẹn vào JSONL (`event_log.py:110`).
**Cách tránh:** trước khi bật write/MCP tool ở các phase sau, redact — thay `args` bằng `args_digest + safe_preview`.
Hiện chỉ có `echo` nên còn lành; **đừng để qua Phase 3 mà chưa vá** (`kernel.py:125`).

**P2 — Middleware fail-open chạy tool 2 lần (FM-HIGH, ✅ đã vá — đừng làm hỏng).**
**Triệu chứng:** một middleware advisory gọi `nxt` rồi raise → tool **không idempotent** chạy lại lần hai.
**Nguyên nhân:** nếu skip-fallback gọi lại `nxt` thô sau khi nó đã chạy.
**Cách tránh:** giữ `_LatchedNext` — gói `nxt` one-shot, lần gọi sau replay kết quả/exception đầu, **không** re-execute (`kernel.py:24-46`, `_wrap` `:64-72`). Chỉ nhánh `fail_open=True` mới latch; fail-closed (gồm Retry) nhận `nxt` thô (`kernel.py:58`).

**P3 — Sửa config/đăng ký sau khi đã có session.**
**Triệu chứng:** `RuntimeError: Middleware pipeline is frozen...` hoặc tệ hơn, state rò nếu bỏ check.
**Nguyên nhân:** `create_root` gọi `kernel.freeze()` (`session.py:141`); sau đó `use()` (`kernel.py:102`) và `register_*` (`registry.py:56`) ném.
**Cách tránh:** wire **toàn bộ** feature+middleware trong `build_kernel` **trước** session đầu (`bootstrap.py:56`). Không "thêm tool nóng" giữa run.

**P4 — Tool trả về không phải dict / lineage thiếu.**
**Triệu chứng:** caller crash khi đọc `env["data"]`, hoặc event mất `task_id`.
**Nguyên nhân:** quên chuẩn hóa kết quả thô.
**Cách tránh:** cửa đã ép: tool trả non-dict → `kernel_error` envelope (`kernel.py:158`); middleware trả non-dict cũng bị bắt (`kernel.py:205`); lineage `setdefault` vào metadata mọi envelope (`kernel.py:210-213`). Đừng bỏ mấy lớp này.

## 7. Definition of Done (cổng đóng phase)

```bash
python run_smoke.py                              # phải in: CORE_AGENT_SMOKE_OK run_id=...
python -m pytest -q tests/test_kernel.py tests/test_trace_ids.py \
                    tests/test_observability.py tests/test_state.py \
                    tests/test_session.py tests/test_event_concurrency.py
python -m observability.inspect summary latest   # đọc lại run vừa chạy
python -m observability.inspect events latest    # thấy chuỗi tool.requested → tool.completed
```

Test THẬT phải xanh:
- `tests/test_kernel.py` — `test_execute_registered_tool`, `test_unknown_tool_null_fallback`, `test_events_emitted`, `test_describe_capabilities` (`test_kernel.py:7,16,31,40`).
- `tests/test_trace_ids.py` — `test_tool_events_carry_task_id`, `test_envelope_metadata_has_task_and_request_id`, `test_task_id_none_without_accept_is_safe` (`test_trace_ids.py:18,32,41`).
- `tests/test_observability.py` — `test_run_writes_events_and_summary`, `test_disabled_logging_writes_nothing` (`test_observability.py:5,22`).
- `tests/test_state.py` — `test_snapshot_restore_roundtrip`, `test_snapshot_not_affected_by_later_set` (`test_state.py:5,18`).

Đóng phase khi: smoke in `CORE_AGENT_SMOKE_OK`, mỗi run đẻ `events.jsonl`+`summary.json` dưới `var/agent_runs/<run_id>/`, `inspect` CLI đọc lại được.

## 8. Vì sao tổ chức thế này giúp kiểm soát

Một cửa (`execute_tool`) là chỗ duy nhất bạn cần dán observability/safety/envelope — dán một lần, áp cho
*mọi* call hiện tại và tương lai; thêm tool thứ 50 không cần đụng lại cửa. Tách **cái đóng băng** (kernel
chia sẻ, `freeze()`) khỏi **cái thay đổi** (`KernelSession.state`) đảm bảo hai run không bao giờ alias mutable
chung — đây là gốc của "no-state-leak". Lineage gắn ở cửa nghĩa là observability **không phải thứ làm thêm sau**:
mọi byte log đã truy vết được tới task ngay từ event đầu. Bài học vibe coding: dựng **khung + cửa trước**,
feature chỉ là cắm adapter vào port đã có — đó là vì sao kiến trúc này lớn lên mà không mất kiểm soát.

---
*Điều hướng: ← [Index](README.md) · → [Phase 2](phase-2-llm-discipline.md)*
