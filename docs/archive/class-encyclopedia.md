# Bách khoa class — core_agent

> 📖 **Tra như từ điển.** Tài liệu chia 2 phần:
> - **PHẦN 1 (ngay dưới)** — snapshot **Sprint 0+1**: lõi đầu tiên TRƯỚC `KernelSession` / delegation / control-plane (E21) / LangGraph schema v2. Vài class ở đây đã **đổi vai** (nhất là `AgentKernel`/`StateStore`/`AgentState`) — đọc Phần 2 để biết hiện trạng.
> - **[PHẦN 2](#phần-2--sau-snapshot-sprint-01-kernelsession--delegation--control-plane-e21--multi-agent)** — phủ **mọi class ra đời sau** (core v2, delegation, adapters, control/ E21, middleware, rag, roles/skills, supervisor, orchestrator/graph v2, tools), đối chiếu mã thật branch hiện tại.
>
> Cho runtime flow tổng thể xem [../reference/runtime-flow.md](../reference/runtime-flow.md) + [../reference/assets/class_dependency.mermaid](../reference/assets/class_dependency.mermaid).

> Mọi class trong repo: **ý nghĩa**, API chính, **phụ thuộc vào** (→) và **được dùng bởi** (←), kèm epic.
> Quy ước phụ thuộc: A → B nghĩa là "A cần/biết B". Toàn bộ tạo thành một DAG sạch (không vòng) — xem mục cuối + sơ đồ.

## Đọc nhanh theo tầng phụ thuộc

```
Tầng 0 (không phụ thuộc nội bộ): schemas, events, state, sandbox, Budget, PolicyDecision, AgentState, *Error
Tầng 1: ports → schemas · registry → schemas · ToolPolicy → schemas · EchoTool/Fs*/Terminal → schemas,sandbox
Tầng 2: AgentKernel → registry,events,state,schemas · SafeToolPort → ToolPolicy · EventLogger → events
Tầng 3: bootstrap/loader → kernel · toolbox.feature → kernel,tools,safety · graph.nodes → kernel,discipline
Tầng 4: graph.runtime → kernel,discipline,observability,nodes
```
`discipline/*` và `llm/*` đứng độc lập (chỉ phụ thuộc stdlib) → tái dùng ở mọi tầng.

---

## core/ — lõi (Epic E01)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `TaskEnvelope` | Gói một task của user | fields: `user_request, context, task_id` | — | `AgentKernel.accept_task` |
| `ToolRequest` | Một lời gọi tool | fields: `name, args, request_id` | — | `ToolPort.execute`, kernel, mọi tool, `SafeToolPort` |
| `CapabilityResult` | **Envelope chuẩn** mọi tool trả về | `from_raw(...)`, `as_dict()`; fields `ok,capability,feature,data,error,metadata` | — | `AgentKernel.execute_tool` |
| `FeatureDescriptor` | Mô tả 1 feature (tên, capabilities) | `as_dict()` | — | `CapabilityRegistry.register_feature`; `example_echo.FEATURE`; `toolbox.FEATURE` |
| `ToolPort` (Protocol) | "Khuôn" mọi tool: `.name` + `.execute(req)->dict` | — | `ToolRequest` | **triển khai bởi**: `NullToolPort`, `EchoTool`, `Fs*`, `Terminal`, `SafeToolPort` |
| `ToolResolution` (NamedTuple) | Cặp `(executor, feature)` từ resolve | — | — | `CapabilityRegistry.resolve_tool`, `AgentKernel` |
| `NullToolPort` | Tool rỗng → `missing_capability` (degrade an toàn) | `execute()` | `ToolRequest` | `CapabilityRegistry` (fallback) |
| `CapabilityRegistry` | Sổ đăng ký tool/feature; resolve + fallback + null | `register_tool/_tools/_feature`, `resolve_tool`, `set_fallback_tool_executor`, `list_*` | `NullToolPort`, `FeatureDescriptor` | `AgentKernel`; nạp bởi `features.loader`/feature install |
| `EventBus` | pub/sub tối giản | `subscribe(fn)`, `publish(topic,payload)` | — | `AgentKernel`; subscribe bởi `EventLogger` |
| `StateStore` | Kho state in-memory của run | `get/set/as_dict` | — | `AgentKernel` |
| `AgentKernel` | **Lõi sống**: nhận task, thực thi tool (resolve→execute→envelope→events) | `accept_task`, `execute_tool`, `describe_capabilities` | `CapabilityRegistry`, `EventBus`, `StateStore`, `schemas` | `bootstrap` tạo; `graph.*`, `toolbox.feature`, tests dùng |

## discipline/ — kỷ luật output (Epic E02)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `JsonGateError` | Lỗi khi parse action JSON | `.stage`, `.candidate` | stdlib | raise bởi `parse_action`; catch bởi `graph.agent_node`; `build_retry_message` |
| `Budget` | Ngân sách loop (steps / parse-errors / same-tool); **parse error KHÔNG tốn step** | `record_step/parse_error/tool_call`, `*_exceeded`, `tool_key()` | stdlib | `graph.runtime.run_agent` |

> Hàm kèm (glue, không phải class): `parse_action`, `build_retry_message`, `condense`, `check_finish`, `requires_validation`, `has_passing_validation`.

## llm/ — adapter (Epic E03)

Không có class. Hàm chính: `call_llm(messages, *, model, json_mode, client)` — OpenAI-compatible, **lazy client**, injectable; lỗi → trả final JSON. (`reset_client()` cho test.) Được dùng bởi `graph.runtime` (truyền vào `run_agent`).

## observability/ — quan sát (Epic E04)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `EventLogger` | Ghi `events.jsonl` + `summary.json` + đếm metrics | `emit(kind,**f)`, `count(metric)`, `finish(status)` | stdlib (+`core.events` qua `attach_to_bus`) | `graph.runtime`, `run_smoke` |

> Glue: `attach_to_bus(logger, bus)` (subscribe EventBus → logger); `inspect.py` (`list_runs/read_summary/read_events`, CLI).

## features/ — plugin (Epic E01)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `EchoTool` | Tool mẫu (echo args) + minh hoạ plugin | `execute()` | `ToolRequest` | đăng ký bởi `example_echo.install` |

> Glue: `loader.install_configured_features(kernel, config)` đọc config → import module feature → gọi `install(kernel)`.

## safety/ — chokepoint an toàn (Epic E06)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `SandboxError` | Lỗi path vượt workspace | — | stdlib | raise bởi `resolve_in_workspace`; catch bởi `Fs*` tools |
| `PolicyDecision` | Kết quả gate (`allowed, reason, code, risk`) | dataclass | — | trả bởi `ToolPolicy`/`classify_terminal`; đọc bởi `SafeToolPort` |
| `ToolPolicy` | **Gate an toàn cross-cutting**: chặn terminal nguy hiểm + git mutation | `check(tool_name, args)->PolicyDecision` | `ToolRequest` | `SafeToolPort`; tạo trong `toolbox.feature` |
| `SafeToolPort` | **Chokepoint**: bọc 1 tool, chạy policy trước khi delegate | `execute(req)` (triển khai `ToolPort`) | `ToolPolicy` | bọc `Fs*`/`Terminal`; đăng ký vào kernel bởi `toolbox.feature` |

> Glue: `resolve_in_workspace(path)`, `workspace_dir()` (path-jail), `classify_terminal(argv)`.

## toolbox/ — tool thật, in-process (Epic E06)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `FsRead` | Đọc file trong workspace | `execute()` (triển khai `ToolPort`) | `safety.sandbox`, `ToolRequest` | bọc bởi `SafeToolPort` → kernel |
| `FsWrite` | Ghi file trong workspace (mkdir parents) | `execute()` | `safety.sandbox`, `ToolRequest` | nt |
| `FsList` | Liệt kê thư mục trong workspace | `execute()` | `safety.sandbox`, `ToolRequest` | nt |
| `Terminal` | Chạy `argv` (no shell) trong workspace + timeout | `execute()` | `safety.sandbox.workspace_dir` | bọc bởi `SafeToolPort` → kernel; policy chặn argv nguy hiểm |

> Glue: `feature.install(kernel)` đăng ký 4 tool trên qua `SafeToolPort(... , ToolPolicy())`.

## graph/ — vòng lặp single-agent (Epic E05)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `AgentState` | State một lần chạy agent | fields: `task, messages, step, final, code_changed, validation_passed` | — | `graph.nodes.agent_node`, `graph.runtime.run_agent` |

> Glue: `agent_node(state, llm_call)` (LLM→action qua `parse_action`), `tool_node(action, kernel)` (gọi tool + `condense`), `run_agent(task, kernel, llm_call)` (loop agent↔tool + `Budget` + `check_finish` + `EventLogger`). **Single = 1 agent node + 1 tool node; multi-agent (E10) tái dùng nguyên loop.**

---

## Các "glue function" then chốt (không phải class nhưng là chất kết dính)

| Hàm | Vai trò | Nối |
|---|---|---|
| `core.bootstrap.build_kernel(config)` | **Composition root**: dựng kernel + cài feature từ config | tạo `AgentKernel`, gọi `loader` |
| `features.loader.install_configured_features` | Cài feature enabled trong config | `config` → `feature.install(kernel)` |
| `graph.runtime.run_agent` | Vòng lặp single-agent | nối kernel + discipline + observability + tools |
| `llm.adapter.call_llm` | Gọi LLM (JSON-mode, lazy) | bơm vào `run_agent` |
| `observability.attach_to_bus` | Đổ event kernel vào log | `EventBus` → `EventLogger` |

## Bản đồ gọi (call-site) — class được dùng ở đâu khi chạy & logic

> "Khi làm việc" = đường runtime (bỏ qua tests). Phân biệt **TẠO** (khởi tạo/`new`) vs **GỌI/NHẬN** (dùng instance). Đã đối chiếu bằng grep mã thật.

### Chuỗi gọi runtime của MỘT bước agent (để thấy ai gọi ai)
```
run_agent (graph.runtime)
  → AgentState(task)                         # tạo state
  → EventLogger() + attach_to_bus(.., kernel.events)   # EventBus.subscribe(sink)
  → kernel.accept_task(task)                 # tạo TaskEnvelope → StateStore.set → EventBus.publish("task.accepted")
  → vòng lặp:
     agent_node(state, llm_call)             # gọi llm_call → parse_action() → (JsonGateError? → retry)
     ├─ action=tool → tool_node(action, kernel)
     │     → kernel.execute_tool(name, args)
     │         → ToolRequest(...)            # tạo
     │         → registry.resolve_tool() → ToolResolution(executor, feature)
     │         → executor.execute(request)   # executor = SafeToolPort → ToolPolicy.check()(PolicyDecision) → tool gốc (FsRead/Terminal/EchoTool…)
     │         → CapabilityResult.from_raw(...).as_dict()   # envelope
     │         → EventBus.publish("tool.completed|failed") → EventLogger.emit/count
     │     → condense(result)                # discipline
     ├─ action=final → check_finish(state)   # finish-gate
     └─ Budget.* (đếm step/parse/same-tool)
  → EventLogger.finish()                     # summary.json
```

### Call-site theo từng class (core/)
- **AgentKernel** — TẠO ở `bootstrap.build_kernel`. NHẬN (param `install(kernel)`) ở `features.loader`, `features.example_echo.install`, `toolbox.feature.install` (để feature đăng ký vào `kernel.registry`). GỌI ở `graph.runtime.run_agent` (`accept_task`, `events`) và `graph.nodes.tool_node` (`execute_tool`). → graph là nơi *vận hành* kernel.
- **CapabilityRegistry** — TẠO ở `build_kernel`; field `AgentKernel.registry`. GỌI: `execute_tool→resolve_tool`, `describe_capabilities→list_*`, feature install→`register_feature/register_tool(s)`.
- **NullToolPort** — TẠO+giữ trong `CapabilityRegistry.__init__`; trả ở `resolve_tool` khi không khớp → kernel gọi `.execute` ra envelope `missing_capability`.
- **ToolResolution** — TẠO ở `CapabilityRegistry.resolve_tool` (3 nhánh exact/fallback/null); ĐỌC ở `AgentKernel.execute_tool` (`.executor`, `.feature`).
- **EventBus** — TẠO ở `build_kernel`; field `AgentKernel.events`. `accept_task`/`execute_tool` GỌI `publish(...)`; `observability.attach_to_bus` GỌI `subscribe(sink)` (graph truyền `kernel.events`). → kernel phát, observability nghe.
- **StateStore** — TẠO ở `build_kernel`; `accept_task` GỌI `state.set("current_task", task)`.
- **TaskEnvelope** — TẠO *duy nhất* ở `AgentKernel.accept_task` (gói request user, lưu state, phát event).
- **ToolRequest** — TẠO *duy nhất* ở `AgentKernel.execute_tool`; NHẬN (đọc `.name/.args`) ở mọi `execute(request)`: `NullToolPort`, `EchoTool`, `FsRead/Write/List`, `Terminal`, `SafeToolPort`. → vật mang lời gọi xuyên tầng tool.
- **CapabilityResult** — dùng *duy nhất* ở `AgentKernel.execute_tool` (`from_raw().as_dict()` chuẩn hóa raw → envelope + metadata).
- **FeatureDescriptor** — TẠO làm hằng `FEATURE` ở `example_echo` & `toolbox.feature`; dùng ở `CapabilityRegistry.register_feature`/`list_features`.
- **ToolPort (Protocol)** — *không bị import lúc chạy*; chỉ là **hợp đồng cấu trúc** (kernel duck-type: `executor.execute(...)`, `getattr(executor,"name")`). Mọi tool theo khuôn nhưng KHÔNG kế thừa → điểm "khuôn ngầm" cần biết.

### discipline/
- **JsonGateError** — RAISE ở `json_gate.parse_action`; CATCH ở `graph.nodes.agent_node` (đổi thành action `retry`); param ở `build_retry_message`.
- **Budget** — TẠO & dùng *chỉ* ở `graph.runtime.run_agent`: `record_step/step_exceeded`, `record_parse_error/parse_exceeded`, `record_tool_call/same_tool_exceeded`, `Budget.tool_key`.

### observability/
- **EventLogger** — TẠO ở `run_agent` (nếu chưa truyền) & `run_smoke`; param ở `attach_to_bus`; `run_agent` GỌI `emit/count/finish` xuyên loop.

### features/
- **EchoTool** — TẠO+đăng ký ở `example_echo.install`; `.execute` được `AgentKernel` gọi khi tool `echo` được yêu cầu.

### safety/
- **SandboxError** — RAISE ở `sandbox.resolve_in_workspace`; CATCH ở `FsRead/FsWrite/FsList.execute` (trả envelope lỗi, không ném lên kernel).
- **PolicyDecision** — TẠO ở `classify_terminal` (nhiều nhánh) & `ToolPolicy.check`; ĐỌC ở `SafeToolPort.execute` (`.allowed/.code/.reason/.risk`).
- **ToolPolicy** — TẠO ở `toolbox.feature.install` (1 instance dùng chung) + default trong `SafeToolPort.__init__`; `SafeToolPort.execute` GỌI `check(name,args)`; `check` gọi hàm `classify_terminal` cho tool terminal.
- **SafeToolPort** — TẠO ở `toolbox.feature.install` (bọc từng `Fs*`/`Terminal`) rồi `register_tool` vào kernel. Lúc chạy: `AgentKernel.execute_tool` resolve ra SafeToolPort → gọi `.execute` → policy → delegate tool gốc. → **chokepoint** nằm trên đường kernel→tool.

### toolbox/
- **FsRead/FsWrite/FsList/Terminal** — TẠO ở `toolbox.feature.install` (bọc SafeToolPort); GỌI `sandbox.resolve_in_workspace`/`workspace_dir`; `.execute` chạy *gián tiếp qua SafeToolPort* khi kernel thực thi `fs_*`/`terminal_run`.

### graph/
- **AgentState** — TẠO ở `run_agent` (`AgentState(task=task)`), bị *biến đổi* trong loop (`messages/step/final`); ĐỌC ở `agent_node` (`state.task`, `state.messages`).

> Ghi chú: tests (`tests/test_*.py`) cũng tạo kernel qua `build_kernel(dict)` và gọi `execute_tool`/`run_agent` — đã loại khỏi bản đồ "khi làm việc" ở trên.

## Bất biến quan trọng (để hiểu "vì sao")
- **Mọi tool đều là `ToolPort`** (cùng khuôn `.execute(ToolRequest)->dict`) → kernel xử lý đồng nhất, an toàn được áp bằng cách *bọc* (`SafeToolPort`) chứ không sửa kernel.
- **Mọi kết quả tool đều thành `CapabilityResult`** (envelope) → tầng trên không phải đoán shape.
- **Lõi (`core/`) không phụ thuộc lên trên**: không biết tới safety/toolbox/graph. Phụ thuộc luôn chỉ xuống. Đó là lý do DAG sạch, dễ thêm tính năng mà không đụng lõi.








---------------------------------------------------------------------------------------------------------

# Call-sites từng class — core_agent

> Với MỖI class: (1) **được khởi tạo bởi** ai, (2) **xuất hiện ở** class/hàm nào, (3) **biến/method của nó được dùng** ở class/hàm nào.
> "Khi làm việc" = đường runtime; phần trong `tests/` ghi chú riêng. Đối chiếu bằng grep mã thật (Sprint 0+1). Nên đặt tại `core_agent/docs/CLASS_CALLSITES.md`.

---

## observability/

### class EventLogger
- **Khởi tạo bởi:** `graph.runtime.run_agent` (khi `logger=None`) · `run_smoke.main` · (tests: `test_observability`).
- **Xuất hiện ở:** `observability/event_log.py` (def; hàm `attach_to_bus(logger: EventLogger, bus)`) · `observability/__init__.py` (export) · `graph/runtime.py` (import; param `logger: EventLogger | None`; biến `logger`) · `run_smoke.py` (import; biến `logger`).
- **Biến/method được dùng ở:**
  - `graph.runtime.run_agent`: `logger.count("steps"|"llm_calls"|"parse_errors"|"finish_gate_blocks"|"condensed")`, `logger.emit("MessageEvent"|"ActionEvent"|"StateEvent", …)`, `logger.finish(...)` → đọc `summary["run_id"]`.
  - `observability.attach_to_bus`: `logger.emit("KernelEvent", topic=…, **payload)`, `logger.count("tool_calls"|"tool_failures")`.
  - `run_smoke.main`: `logger.count("steps")`, `logger.finish("completed")`.
  - Nội bộ (method của chính nó): `self.seq, self.metrics, self.run_dir, self.events_path, self.enabled, self.run_id`.

---

## core/

### class AgentKernel
- **Khởi tạo bởi:** `core.bootstrap.build_kernel` (`AgentKernel(registry=, events=, state=, config=)`).
- **Xuất hiện ở:** `core/kernel.py` (def) · `core/bootstrap.py` (import, tạo, return type) · `features/loader.py` (`install_configured_features(kernel: AgentKernel, …)`) · `features/example_echo.py` & `toolbox/feature.py` (`install(kernel: AgentKernel)`) · `graph/nodes.py` (`tool_node(action, *, kernel: AgentKernel)`) · `graph/runtime.py` (param `kernel: AgentKernel`).
- **Biến/method được dùng ở:**
  - `graph.runtime.run_agent`: `kernel.accept_task(task)`, `kernel.events` (truyền cho `attach_to_bus`).
  - `graph.nodes.tool_node`: `kernel.execute_tool(name, args)`.
  - `features.example_echo.install` / `toolbox.feature.install`: `kernel.registry.register_feature/register_tool(s)`.
  - Nội bộ: `self.registry.resolve_tool`, `self.events.publish`, `self.state.set`, `self.registry.list_features/list_tools`.

### class CapabilityRegistry
- **Khởi tạo bởi:** `core.bootstrap.build_kernel` (`CapabilityRegistry()`).
- **Xuất hiện ở:** `core/registry.py` (def) · `core/kernel.py` (import; field `registry: CapabilityRegistry`) · `core/bootstrap.py` (import, tạo).
- **Biến/method được dùng ở:** `AgentKernel.execute_tool` (`registry.resolve_tool`) · `AgentKernel.describe_capabilities` (`list_features/list_tools`) · `example_echo.install` & `toolbox.feature.install` (`register_feature`, `register_tool(s)`). Nội bộ: `_tools, _features, _tool_features, _fallback, _fallback_feature, _null`.

### class NullToolPort
- **Khởi tạo bởi:** `CapabilityRegistry.__init__` (`self._null = null_tool or NullToolPort()`).
- **Xuất hiện ở:** `core/registry.py` (def; dùng trong `__init__`, `resolve_tool`).
- **Biến/method được dùng ở:** `CapabilityRegistry.resolve_tool` trả `self._null`; `AgentKernel.execute_tool` gọi `resolution.executor.execute(request)` (executor = NullToolPort khi miss); `.name` đọc qua `getattr(executor, "name", …)`.

### class ToolResolution (NamedTuple)
- **Khởi tạo bởi:** `CapabilityRegistry.resolve_tool` (3 nhánh: exact / fallback / null).
- **Xuất hiện ở:** `core/registry.py` (def; return type của `resolve_tool`) · `core/kernel.py` (gián tiếp qua `resolve_tool`).
- **Biến/method được dùng ở:** `AgentKernel.execute_tool`: `resolution.executor` (gọi `.execute`), `resolution.feature` (truyền vào `CapabilityResult.from_raw`).

### class EventBus
- **Khởi tạo bởi:** `core.bootstrap.build_kernel` (`EventBus()`).
- **Xuất hiện ở:** `core/events.py` (def) · `core/kernel.py` (import; field `events: EventBus`) · `observability/event_log.py` (import; `attach_to_bus(logger, bus: EventBus)`).
- **Biến/method được dùng ở:** `AgentKernel.accept_task`/`execute_tool`: `self.events.publish(topic, payload)` · `observability.attach_to_bus`: `bus.subscribe(sink)` · `graph.runtime.run_agent`: truyền `kernel.events`. Nội bộ: `self._subscribers`.

### class StateStore
- **Khởi tạo bởi:** `core.bootstrap.build_kernel` (`StateStore()`).
- **Xuất hiện ở:** `core/state.py` (def) · `core/kernel.py` (import; field `state: StateStore`).
- **Biến/method được dùng ở:** `AgentKernel.accept_task`: `self.state.set("current_task", task)`. (`get`/`as_dict` là API, chưa gọi ở runtime hiện tại.)

### class TaskEnvelope
- **Khởi tạo bởi:** `AgentKernel.accept_task` (`TaskEnvelope(user_request=, context=)`) — *nơi tạo duy nhất*.
- **Xuất hiện ở:** `core/schemas.py` (def) · `core/kernel.py` (import; return type của `accept_task`).
- **Biến/method được dùng ở:** `AgentKernel.accept_task`: đọc `task.task_id` (publish `task.accepted`), lưu `task` vào StateStore.

### class ToolRequest
- **Khởi tạo bởi:** `AgentKernel.execute_tool` (`ToolRequest(name=, args=)`) — *nơi tạo duy nhất*.
- **Xuất hiện ở:** `core/schemas.py` (def) · `core/kernel.py` (tạo) · param `execute(request: ToolRequest)` ở: `core/ports.py` (ToolPort), `core/registry.py` (NullToolPort), `features/example_echo.py` (EchoTool), `safety/policy.py` (SafeToolPort), `toolbox/filesystem.py` (FsRead/Write/List), `toolbox/terminal.py` (Terminal).
- **Biến/method được dùng ở:**
  - `AgentKernel.execute_tool`: `request.name`, `request.args`, `request.request_id`.
  - `EchoTool.execute`: `request.args`.
  - `FsRead/FsWrite/FsList.execute`: `request.args.get("path"|"content")`.
  - `Terminal.execute`: `request.args.get("argv"|"timeout")`.
  - `SafeToolPort.execute`: `request.name`, `request.args` (truyền cho `policy.check`).

### class CapabilityResult
- **Khởi tạo bởi:** `AgentKernel.execute_tool` (`CapabilityResult.from_raw(...)`) — *nơi dùng duy nhất*.
- **Xuất hiện ở:** `core/schemas.py` (def; + hàm `is_capability_result`) · `core/kernel.py` (import; `from_raw().as_dict()`).
- **Biến/method được dùng ở:** `AgentKernel.execute_tool`: `CapabilityResult.from_raw(capability=, feature=, result=, metadata=).as_dict()` → envelope dict. Nội bộ `from_raw` dùng `is_capability_result`, đọc key của `result`.

### class FeatureDescriptor
- **Khởi tạo bởi:** `features.example_echo` (`FEATURE = FeatureDescriptor(...)`) · `toolbox.feature` (`FEATURE = FeatureDescriptor(...)`).
- **Xuất hiện ở:** `core/schemas.py` (def) · `core/registry.py` (import; `register_feature(descriptor: FeatureDescriptor)`, `_features: dict[str, FeatureDescriptor]`) · `features/example_echo.py`, `toolbox/feature.py`.
- **Biến/method được dùng ở:** `example_echo.install`/`toolbox.feature.install`: `FEATURE.capabilities`, `FEATURE.name` · `CapabilityRegistry.register_feature` (lưu), `list_features` (`descriptor.as_dict()`).

### class ToolPort (Protocol)
- **Khởi tạo bởi:** *không* (Protocol — không instantiate).
- **Xuất hiện ở:** `core/ports.py` (def). **Không bị import lúc chạy** ở nơi khác.
- **Biến/method được dùng ở:** *không trực tiếp* — chỉ là **hợp đồng cấu trúc**. Kernel duck-type (`executor.execute(...)`, `getattr(executor,"name")`); tool tuân khuôn nhưng không kế thừa/không import.

---

## discipline/

### class JsonGateError (ValueError)
- **Khởi tạo bởi (raise):** `discipline.json_gate.parse_action` (2 nhánh: parse fail, thiếu `action`).
- **Xuất hiện ở:** `discipline/json_gate.py` (def; raise; `build_retry_message(error: JsonGateError)`) · `discipline/__init__.py` (export) · `graph/nodes.py` (import; `except JsonGateError as exc`).
- **Biến/method được dùng ở:** `graph.nodes.agent_node` (catch; `str(exc)`, truyền `exc` vào `build_retry_message`) · `build_retry_message`: `error.stage`.

### class Budget
- **Khởi tạo bởi:** `graph.runtime.run_agent` (`Budget(max_steps=max_steps)`).
- **Xuất hiện ở:** `discipline/budget.py` (def) · `discipline/__init__.py` (export) · `graph/runtime.py` (import, tạo, dùng).
- **Biến/method được dùng ở:** `graph.runtime.run_agent`: `budget.step_exceeded()`, `record_step()`, `record_parse_error()`, `parse_exceeded()`, `record_tool_call(key)`, `same_tool_exceeded(key)`, `Budget.tool_key(tool, args)` (staticmethod). Nội bộ: `steps, parse_errors, _tool_calls, max_steps, max_parse_errors, max_same_tool_calls`.

---

## features/

### class EchoTool
- **Khởi tạo bởi:** `features.example_echo.install` (`EchoTool()` trong `register_tools`).
- **Xuất hiện ở:** `features/example_echo.py` (def + install).
- **Biến/method được dùng ở:** `.execute(request)` được `AgentKernel.execute_tool` gọi (sau resolve) khi tool `echo` được yêu cầu; đọc `request.args`. (`.name = "echo_tool"` không dùng — đăng ký theo capability `"echo"`.)

---

## safety/

### class SandboxError (ValueError)
- **Khởi tạo bởi (raise):** `safety.sandbox.resolve_in_workspace`.
- **Xuất hiện ở:** `safety/sandbox.py` (def + raise) · `safety/__init__.py` (export) · `toolbox/filesystem.py` (import; `except SandboxError` trong FsRead/FsWrite/FsList).
- **Biến/method được dùng ở:** `FsRead/FsWrite/FsList.execute` (catch; `str(exc)` → envelope lỗi).

### class PolicyDecision
- **Khởi tạo bởi:** `safety.policy.classify_terminal` (nhiều nhánh) · `ToolPolicy.check` (nhiều nhánh).
- **Xuất hiện ở:** `safety/policy.py` (def; return type của `classify_terminal`/`ToolPolicy.check`) · `safety/__init__.py` (export).
- **Biến/method được dùng ở:** `SafeToolPort.execute`: `decision.allowed`, `decision.code`, `decision.reason`, `decision.risk`.

### class ToolPolicy
- **Khởi tạo bởi:** `toolbox.feature.install` (`policy = ToolPolicy()`) · `SafeToolPort.__init__` default (`policy or ToolPolicy()`).
- **Xuất hiện ở:** `safety/policy.py` (def; `SafeToolPort.__init__(..., policy: ToolPolicy | None)`) · `safety/__init__.py` (export) · `toolbox/feature.py` (import, tạo).
- **Biến/method được dùng ở:** `SafeToolPort.execute`: `self._policy.check(request.name, request.args)`. Nội bộ `check` gọi hàm `classify_terminal`.

### class SafeToolPort
- **Khởi tạo bởi:** `toolbox.feature.install` (`SafeToolPort(tool.name, tool, policy)` trong vòng lặp).
- **Xuất hiện ở:** `safety/policy.py` (def) · `safety/__init__.py` (export) · `toolbox/feature.py` (import, tạo, `register_tool`).
- **Biến/method được dùng ở:** `AgentKernel.execute_tool` gọi `.execute` (executor resolve ra = SafeToolPort cho `fs_*`/`terminal_run`). Nội bộ `execute`: `self._policy.check`, `self._inner.execute(request)`, `self.name`.

---

## toolbox/

### class FsRead / FsWrite / FsList
- **Khởi tạo bởi:** `toolbox.feature.install` (`FsRead(), FsWrite(), FsList()` — bọc trong `SafeToolPort`).
- **Xuất hiện ở:** `toolbox/filesystem.py` (def) · `toolbox/feature.py` (import, tạo).
- **Biến/method được dùng ở:** `.execute` chạy *gián tiếp qua SafeToolPort* khi kernel thực thi `fs_read|fs_write|fs_list`. Dùng `safety.sandbox.resolve_in_workspace`, `request.args`; `FsWrite`: `path.parent.mkdir`, `path.write_text`; `FsRead`: `path.read_text`; `FsList`: `path.iterdir`.

### class Terminal
- **Khởi tạo bởi:** `toolbox.feature.install` (`Terminal()`).
- **Xuất hiện ở:** `toolbox/terminal.py` (def) · `toolbox/feature.py` (import, tạo).
- **Biến/method được dùng ở:** `.execute` qua SafeToolPort (policy `classify_terminal` gác argv trước). Dùng `safety.sandbox.workspace_dir`, `subprocess.run`, `request.args.get("argv"|"timeout")`.

---

## graph/

### class AgentState
- **Khởi tạo bởi:** `graph.runtime.run_agent` (`AgentState(task=task)`).
- **Xuất hiện ở:** `graph/state.py` (def) · `graph/__init__.py` (export) · `graph/nodes.py` (import; `agent_node(state: AgentState, …)`) · `graph/runtime.py` (import, tạo).
- **Biến/method được dùng ở:**
  - `graph.nodes.agent_node`: đọc `state.task`, `state.messages`.
  - `graph.runtime.run_agent`: `state.step` (++), `state.final` (set), `state.messages.append(...)`, `state.code_changed`/`state.validation_passed` (truyền vào `check_finish`). (`state.last_action` khai báo, chưa dùng runtime.)

---

## Ghi chú
- **`build_kernel` là nơi sinh** 4 thành phần lõi (`AgentKernel`, `CapabilityRegistry`, `EventBus`, `StateStore`) — mọi thứ khác nhận chúng qua kernel.
- **Tests** cũng khởi tạo qua `build_kernel(dict)` / `EventLogger(run_id=...)` và gọi `execute_tool`/`run_agent`/`check`… — đã loại khỏi cột "khi làm việc".
- 3 dataclass schema (`TaskEnvelope`, `ToolRequest`, `CapabilityResult`) mỗi cái **chỉ sinh ở đúng 1 nơi trong `AgentKernel`** → dễ truy vết.
- `ToolPort` là class duy nhất **không xuất hiện lúc chạy** (chỉ là Protocol hợp đồng).


---
---

# PHẦN 2 — Sau snapshot Sprint 0+1 (KernelSession · delegation · control-plane E21 · multi-agent)

> Phủ **mọi class ra đời sau Phần 1**, đối chiếu mã thật (branch hiện tại). Cùng định dạng từ điển: bảng (ý nghĩa · API chính · phụ thuộc → · được dùng bởi ←) + **Call-sites** từng class (khởi tạo bởi / xuất hiện ở / biến-method dùng ở). Quy ước như Phần 1: `A → B` = "A cần/biết B"; phân biệt **TẠO** vs **GỌI**; "(chỉ tests)" = chưa có call-site runtime.

## Thay đổi kiến trúc lớn nhất (đọc trước khi tra)

Snapshot Phần 1 cảnh báo đúng: `AgentKernel` đã **tách đôi**.

- **`AgentKernel` (core/kernel.py)** giờ là **runtime CHUNG, FROZEN** — chỉ giữ `registry` + `events` + `_middlewares` + `config`. **Không còn** state-per-run, không vòng đời task, **không tự tạo session**. `freeze()` đóng băng registry + deep-freeze config trước session đầu tiên → mọi run chia sẻ an toàn **một** kernel.
- **`KernelSession` (core/session.py)** sở hữu **state + scope + vòng đời của MỘT run**: `StateStore` riêng (state đổi vai từ "của kernel" → "do session sở hữu"), `SessionIdentity` (lineage cha + độ sâu ủy thác), `allowed_capabilities` (scope), `execute_tool` (bơm `ToolCallContext`), `complete_task`/`fail_task`. `SessionFactory` là constructor **DUY NHẤT** (root/child/restore) và ép quy tắc **subset-scope** (con không vượt quyền cha).

Hai **chokepoint** tách biệt có chủ đích (xem `runtime-flow.md`):
1. **`AgentKernel.execute_tool`** — MỌI hành động LLM **và** tool đi qua đây (LLM cũng là capability `llm.chat`, không đường tắt). Vòng `ToolMiddleware` (timing→policy→retry→condense) bọc quanh điểm này.
2. **`DelegationServicePort.delegate`** — giao việc cho agent con đi đường **RIÊNG** (không phải method của kernel) → có node `delegate` riêng trong graph.

`AgentState` cũng đổi: từ **dataclass** (Phần 1) → **`TypedDict` serializable** có `schema_version`/`session_identity`/`session_state` + delegation fields + codec; runtime services (kernel/LLM/SQLite) bị loại khỏi state, nodes nhận qua closure → mọi checkpoint restart-safe.

## Legend epic (Phần 2)

| Epic | Tên | Module chính trong Phần 2 |
|---|---|---|
| E01 | Kernel (refactor v2) | `core/` (session, middleware, ports, registry.descriptor) |
| E05 | Single-agent Graph (LangGraph) | `graph/`, `orchestrator/` |
| E07 | Skills | `skills/` |
| E08 | RAG | `rag/` |
| E09 | Roles & Lenses | `roles/` |
| E10 | Multi-agent Graph (Agent O) | `supervisor/`, `delegation/`, `adapters/` |
| E15 | Self-eval & Governance | **đã gộp vào E21** |
| E21 | Realtime Control Plane (gộp E16+E17+E18) | `control/`, `tools/` (harness) |

## Tầng phụ thuộc (v2)

```
Tầng 0 (contracts, không phụ thuộc nội bộ): core.schemas (Delegation*/ToolCallContext) · core.ports · control.events/errors · rag.ports · roles/skills spec · supervisor.contracts/state
Tầng 1 (session lõi): core.session (KernelSession/SessionFactory) → kernel(frozen) + StateStore
Tầng 2 (middleware + features): middleware/* → core.middleware · rag.service/feature → rag.ports · roles.Agent → spec+registries
Tầng 3 (delegation): delegation.manager → registry+store+policy+session · adapters.* triển khai DelegationPort
Tầng 4 (graph single): graph.runtime/nodes/state → session + discipline + delegation-port (tiêm)
Tầng 5 (multi-agent): supervisor.graph/loop → orchestrator(Agent O) + broker + delegation + roles
Tầng 6 (control-plane, cross-cutting): control.emitter → registry+redactor+seq+sink · control.snapshot (read-model) · commands/checkpoint/permission
```
`control/` ngồi **ngang** (cross-cutting): nó *quan sát* (event ra) + *can thiệp* (command/checkpoint vào) chứ **không** nằm trên đường data của tool. `tools/` là **dev harness** (không phải runtime sản phẩm).

---

## core/ — v2: KernelSession (state/lifecycle mỗi run) + delegation contracts trên một AgentKernel chung, frozen (Epic E01 / E10·E15)

> **Ranh giới mới (snapshot cũ cảnh báo đúng):** `AgentKernel` (core/kernel.py) đổi vai thành **runtime chung, bất biến**: chỉ ôm `registry` + `events` + `_middlewares` + `config`, expose `execute_tool(...)`/`freeze()`/`use(...)`/`describe_capabilities()`. Nó **không còn** giữ state-per-run, không còn vòng đời task, **không tự tạo session** (core/session.py:105 nói rõ "AgentKernel never creates sessions"). `StateStore` (core/state.py) đổi vai: từ "state của kernel" thành **state do session sở hữu** (docstring core/state.py:1 "Session-owned"; mỗi `KernelSession` `new StateStore()` riêng tại core/session.py:142,182,198). Toàn bộ STATE-per-run + lifecycle (`current_task`, `last_result`, complete/fail) dời sang `KernelSession`. `freeze()` đóng băng registry + deep-freeze config trước session đầu tiên (core/kernel.py:48), được gọi từ `SessionFactory.create_root/restore` (core/session.py:141,195) → sau freeze mọi run dùng chung 1 kernel an toàn.

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `SessionIdentity` | Lý lịch bất biến của 1 run: định danh + lineage ủy thác (parent/delegation/depth) | `session_id/run_id/task_id/agent_id/parent_session_id/delegation_id/depth`; `as_dict`/`from_dict` (session.py:25,37) | — (stdlib) | `KernelSession.identity`; tạo ở `SessionFactory.create_root/create_child` (session.py:134,173); `orchestrator/loop.py:165,193,197` |
| `KernelSession` | Sở hữu state + scope + vòng đời của **một** task; kernel chỉ là dịch vụ dùng chung | `is_active`; `call_context()`; `execute_tool()`; `complete_task()`/`fail_task()`; fields `kernel/identity/state/allowed_capabilities/_closed` (session.py:59-101) | `AgentKernel` (kernel/events), `StateStore`, `SessionIdentity`, `TaskEnvelope`, `ToolCallContext` | `SessionFactory`; `graph/nodes.py`·`graph/runtime.py`·`graph/state.py`; `delegation/manager.py`·`delegation/policy.py`; `adapters/agents/*`; `supervisor/*`; `orchestrator/loop.py` |
| `SessionFactory` | **Constructor duy nhất** của session gốc/con; ép freeze kernel; thực thi quy tắc subset scope | `create_root()`, `create_child()`, `restore()`; `_effective_root_scope()` (session.py:110-203) | `AgentKernel` (registry/freeze/events), `KernelSession`, `SessionIdentity`, `StateStore`, `TaskEnvelope` | `run_smoke.py:15`; `orchestrator/loop.py`; `graph/runtime.py:13`; `delegation/manager.py` (`self.sessions`) |
| `ToolCallContext` | Lineage + scope bất biến của 1 lần gọi tool; **không bao giờ** truyền như tool-arg | `event_fields()`; fields `run_id/task_id/session_id/parent_session_id/delegation_id/actor_id/allowed_capabilities` (schemas.py:37-56) | — (stdlib) | Sinh tại `KernelSession.call_context()` (session.py:65); tiêu thụ ở `AgentKernel.execute_tool` (kernel.py:68,72,85) cho scope-gate |
| `DelegationSpec` | "Yêu cầu công việc" gửi agent con: mục tiêu + context + (E10) schema kỳ vọng + ràng buộc | `objective/input_context/expected_output_schema/constraints`; `from_dict`/`as_dict` (schemas.py:133-155) | — (stdlib) | `delegation/manager.delegate(spec=...)`; `graph/nodes.py:165`; `supervisor/contracts.py:67` (`to_spec`) |
| `DelegationPolicy` | Trần tài nguyên/quyền của 1 lần ủy thác (max_steps/max_depth/scope) | `max_steps/max_depth/allowed_capabilities`; `from_dict`/`as_dict` (schemas.py:159-178) | — (stdlib) | `delegation/manager.py:78`; validate ở `delegation/policy.DelegationPolicyEngine`; `graph/nodes.py:177`; `supervisor/graph.py:175` |
| `DelegationRequest` | Bản ghi bất biến một lần ủy thác (id + lineage cha + target + spec + policy) | `delegation_id/parent_session_id/parent_task_id/target/spec/policy`; `as_dict` (schemas.py:182-198) | `DelegationSpec`, `DelegationPolicy` | **Nơi tạo:** `delegation/manager.py:82,105`; chữ ký ở `DelegationPort.run`/store; `adapters/agents/*` nhận làm param |
| `ArtifactEnvelope` | Vỏ bọc kết quả/finding của agent con (id + kind + payload + schema_version) | `artifact_id/kind/payload/schema_version`; `as_dict` (schemas.py:202-214) | — (stdlib) | Tạo ở `adapters/agents/scripted.py:34`·`langgraph_agent.py:63`; gom artifacts ở `manager.py:165-168` |
| `DelegationProgress` | Một mốc tiến độ stream của agent con (sequence + event_id + artifact + status) | `delegation_id/sequence/event_id/artifact/status`; `as_dict` (schemas.py:218-232) | `ArtifactEnvelope` | Tạo ở `adapters/agents/*` rồi đẩy qua `progress_sink` → `store.append_progress` (`manager.py:142-147`) |
| `DelegationResult` | Kết quả cuối của ủy thác (outcome + artifacts + summary + error) | `delegation_id/parent_task_id/outcome/artifacts/summary/error`; `as_dict` (schemas.py:236-252) | `ArtifactEnvelope` | Tạo ở `adapters/agents/*` và (re-wrap) `manager.py:98,134,170,179`; trả về từ `DelegationServicePort.delegate` |
| `DelegationPort` | Seam của "một agent con biết chạy": nhận request + child_session + sink, trả result | `name`; `can_handle(target)`; `run(request, child_session, progress_sink)` (ports.py:32-45) | `DelegationRequest`/`DelegationResult`, `KernelSession`, `ProgressSink` | **Không instantiate (Protocol)**; implement bởi `adapters/agents/langgraph_agent.py`·`scripted.py`; resolve qua `delegation/registry.py` |
| `DelegationStorePort` | Seam lưu trữ vòng đời ủy thác (append-only: start→progress→finish→đọc) | `start/append_progress/finish/progress/result` (ports.py:48-62) | `DelegationRequest`/`DelegationProgress`/`DelegationResult` | **Không instantiate (Protocol)**; impl `delegation/store.py`; type-hint ở `manager.py:25` (`self.store`) |
| `DelegationServicePort` | Seam mặt-tiền ủy thác mà graph/orchestrator gọi (liệt kê target + delegate) | `available_targets()`; `delegate(parent_session, target, spec, policy=None)` (ports.py:65-76) | `DelegationSpec`/`DelegationPolicy`/`DelegationResult`, `KernelSession` | **Không instantiate (Protocol)**; impl `DelegationManager`; tạo qua `delegation/bootstrap.py:13`; tiêu thụ `graph/nodes.py:145`·`graph/runtime.py:35`·`orchestrator/loop.py` |
| `ToolMiddleware` | Seam hook quanh `execute_tool`: act before/after, short-circuit, hoặc sửa envelope | `__call__(request, nxt) -> dict` (middleware.py:11-15) | `ToolRequest`, `ToolHandler` | **Không instantiate (Protocol)**; impl `middleware/{policy,retry,condense,budget,timing}.py`; đăng ký qua `AgentKernel.use()` (kernel.py:57), wire ở `core/bootstrap.py:37-52` |
| `ToolDescriptor` | Metadata năng lực cho retry/policy: `kind`(model/read/effect/tool)·`idempotent`·`risk` — effect không idempotent **không được** retry (E10 S10.13) | fields `kind/idempotent/risk` (registry.py:11-17) | — (stdlib) | **Chỉ trong core:** tạo ở `registry.register_tool` (registry.py:81), bọc trong `ToolResolution`; đọc ở `kernel.py:130-132` (ghi vào metadata envelope). Không có call-site runtime ngoài core/ |

> **Glue (hàm, không phải class):** `core/session.py` — không có hàm module-level (tất cả là method). `core/schemas.py::is_capability_result()` (dùng bởi `CapabilityResult.from_raw`). `core/kernel.py::_deep_freeze()` (đóng băng config khi `freeze`), `_wrap()` (bind middleware quanh handler, tránh late-binding closure). `core/ports.py::ProgressSink = Callable[[DelegationProgress], None]` (type alias dùng làm tham số `run(...)` của `DelegationPort`). `core/middleware.py::ToolHandler = Callable[[ToolRequest], dict]` (type alias cho `nxt`).

**Call-sites:**

### `SessionIdentity`
- **Khởi tạo bởi:** `SessionFactory.create_root` (session.py:134) và `create_child` (session.py:173); runtime ngoài core: `orchestrator/loop.py:165,197` (và `from_dict` tại 193 khi resume).
- **Xuất hiện ở:** import `orchestrator/loop.py:11`; field `KernelSession.identity` (session.py:54).
- **Biến/method dùng ở:** `KernelSession.call_context()` đọc `identity.run_id/task_id/session_id/parent_session_id/delegation_id/agent_id` (session.py:66-72); `as_dict`/`from_dict` round-trip ở `orchestrator/loop.py` (chỉ tests cho assert: `tests_audit/test_contract_roundtrips.py:120`).

### `KernelSession`
- **Khởi tạo bởi:** chỉ `SessionFactory` (`create_root` 144, `create_child` 184, `restore` 200). Không nơi nào khác `new` trực tiếp trong runtime.
- **Xuất hiện ở:** import/param/return ở `graph/{state,nodes,runtime}.py`, `delegation/{manager,policy}.py`, `adapters/agents/{langgraph_agent,scripted}.py` (param `child_session`), `supervisor/{graph,loop,llm}.py` (field/param `supervisor_session`/`session`), `orchestrator/loop.py:98,188`.
- **Biến/method dùng ở:** `delegation/manager.delegate` gọi `parent_session.is_active` (manager.py:70), đọc `.identity.session_id/.task_id` (84-85,163), `.kernel.events.publish` (91,114), tạo child qua `self.sessions.create_child` (121) rồi `child.state.set("delegation_policy", ...)` (129) và `child.call_context().event_fields()` (151). `graph/nodes.py` gọi `session.execute_tool`/`complete_task`/`fail_task` (qua các node). `self.*`: `is_active` đọc `self._closed` + `self.state.get("current_task")` (session.py:60-61); `execute_tool` ủy nhiệm `self.kernel.execute_tool(..., context=self.call_context())` (session.py:85); `complete_task` ghi `self.state` + set `_closed` + `self.kernel.events.publish` (91-97).

### `SessionFactory`
- **Khởi tạo bởi:** `run_smoke.py:15` (`SessionFactory(kernel=kernel)`); `orchestrator/loop.py` và `graph/runtime.py:13`; trong `DelegationManager` được tiêm sẵn instance (`self.sessions`, gọi `create_child` ở manager.py:121).
- **Xuất hiện ở:** import `core.session` ở các file trên.
- **Biến/method dùng ở:** `create_root` gọi `self.kernel.registry.list_tools()` (qua `_effective_root_scope`, session.py:111), `self.kernel.freeze()` (141), `self.kernel.events.publish("task.accepted", ...)` (145). `create_child` ép subset scope: raise `PermissionError` nếu `not scope <= parent.allowed_capabilities` (164). `restore` raise `ValueError` nếu scope persisted vượt runtime hiện tại (197).

### `ToolCallContext`
- **Khởi tạo bởi:** **nơi tạo runtime duy nhất** `KernelSession.call_context()` (session.py:65). (`AgentKernel.execute_tool` chỉ nhận nó làm tham số, không tạo.)
- **Xuất hiện ở:** param `context: ToolCallContext | None` ở `AgentKernel.execute_tool` (kernel.py:68); import kernel.py:11. (`ToolRequest.context` cũng kiểu này — schemas.py:32.)
- **Biến/method dùng ở:** `execute_tool` gọi `context.event_fields()` làm `lineage` (kernel.py:72) và đọc `context.allowed_capabilities` để chặn ngoài-scope (kernel.py:85-86). `complete_task`/`execute_tool` của session dùng `call_context().event_fields()` (session.py:83,96).

### `DelegationSpec`
- **Khởi tạo bởi:** `supervisor/contracts.py:69` (`to_spec`), `graph/nodes.py:165` (`from_dict`). (Trong tests delegation truyền trực tiếp.)
- **Xuất hiện ở:** param `delegate(..., spec: DelegationSpec)` ở `manager.py:67` và `DelegationServicePort.delegate` (ports.py:72).
- **Biến/method dùng ở:** `manager.delegate` đọc `spec.objective` (74, dùng làm `user_request`), `spec.input_context` (126); đặt vào `DelegationRequest(spec=spec)` (87,110).

### `DelegationPolicy`
- **Khởi tạo bởi:** `manager.py:78` (`policy or DelegationPolicy()`), `delegation/policy.py:18,28` (engine clamp/produce), `graph/nodes.py:177` (`from_dict`), `supervisor/graph.py:175` (từ `assignment.allowed_capabilities`).
- **Xuất hiện ở:** param `delegate(..., policy=None)` (manager.py:68); `DelegationPolicyEngine.validate(...) -> DelegationPolicy` (policy.py:16-17).
- **Biến/method dùng ở:** `manager.delegate` dùng `active_policy.allowed_capabilities` làm `requested_scope` cho child (manager.py:127), `active_policy.max_steps` để chặn progress vượt mức (manager.py:145), `active_policy.as_dict()` lưu vào child state (manager.py:129).

### `DelegationRequest`
- **Khởi tạo bởi:** **nơi tạo runtime duy nhất** `delegation/manager.py` (82,105 — nhánh reject sớm và nhánh chính).
- **Xuất hiện ở:** param `DelegationPort.run(request, ...)` (ports.py:39; impl `adapters/agents/{scripted,langgraph_agent}.py`), `DelegationStorePort.start(request)` (ports.py:49; `delegation/store.py:18`).
- **Biến/method dùng ở:** `store.start` lưu `self._requests[...] = request` (store.py:13,18); `manager` truyền `request` vào `handler.run(request, child, progress_sink)` (manager.py:160); adapter đọc `request.delegation_id`/`request.parent_task_id` khi dựng kết quả.

### `ArtifactEnvelope`
- **Khởi tạo bởi:** `adapters/agents/scripted.py:34`, `adapters/agents/langgraph_agent.py:63` (mỗi mốc tiến độ); gom (không tạo mới) ở `manager.py:165-168`.
- **Xuất hiện ở:** field `DelegationProgress.artifact` (schemas.py:222) và `DelegationResult.artifacts` (schemas.py:240); list buffer ở adapter (`scripted.py:32`, `langgraph_agent.py:56`).
- **Biến/method dùng ở:** `progress_sink` gọi `progress.artifact.as_dict()` khi publish event (manager.py:155); `manager` dedupe theo `artifact.artifact_id` (manager.py:166-168).

### `DelegationProgress`
- **Khởi tạo bởi:** `adapters/agents/scripted.py:41`, `langgraph_agent.py:74` (agent con stream).
- **Xuất hiện ở:** alias `ProgressSink = Callable[[DelegationProgress], None]` (ports.py:29); param `append_progress` (ports.py:52, `store.py:25`).
- **Biến/method dùng ở:** `manager.progress_sink` đọc `progress.delegation_id` (kiểm khớp, manager.py:143), `progress.sequence` (chặn vượt `max_steps`, 145), `progress.event_id/status/artifact` khi publish `delegation.progress` (148-156), rồi `store.append_progress(progress)` (147).

### `DelegationResult`
- **Khởi tạo bởi:** `adapters/agents/scripted.py:48`·`langgraph_agent.py:83` (kết quả từ agent con); `delegation/manager.py:98,134,170,179` (reject/fail wrap + re-wrap gộp artifacts).
- **Xuất hiện ở:** return-type `DelegationPort.run` (ports.py:44), `DelegationServicePort.delegate` (ports.py:75), `DelegationStorePort.finish/result` (ports.py:55,61).
- **Biến/method dùng ở:** `manager` kiểm `result.delegation_id`/`result.parent_task_id` khớp request (manager.py:161-164), đọc `result.artifacts/outcome/summary/error` để re-wrap (170-177); `store.finish(result)` ghi `self._results[...]` (store.py:40).

### `DelegationPort`
- **Khởi tạo bởi:** không (Protocol). Implement bởi `LangGraphDelegationAgent` (adapters/agents/langgraph_agent.py — docstring "Concrete DelegationPort") và `scripted.py`.
- **Xuất hiện ở:** import + type ở `delegation/registry.py:6,11,15,27` (list `self._handlers: list[DelegationPort]`, `register`, `resolve -> DelegationPort`).
- **Biến/method dùng ở:** `manager` lấy `handler = self.registry.resolve(target)` rồi `handler.run(request, child, progress_sink)` (manager.py:120,160); `registry.resolve` lọc theo `handler.can_handle(target)`. (`isinstance(..., DelegationPort)` chỉ tests: `tests/test_supervisor_loop.py:144`.)

### `DelegationStorePort`
- **Khởi tạo bởi:** không (Protocol). Impl `delegation/store.py`.
- **Xuất hiện ở:** import + param `store: DelegationStorePort` ở `DelegationManager.__init__` (manager.py:6,25).
- **Biến/method dùng ở:** `manager` gọi `self.store.start(request)` (90,113), `self.store.append_progress(progress)` (147), `self.store.progress(delegation_id)` (165,183), và `finish` (qua `_finish`).

### `DelegationServicePort`
- **Khởi tạo bởi:** không (Protocol). Impl là `DelegationManager`; instance tạo qua `delegation/bootstrap.create_delegation_service(kernel)` (bootstrap.py:13).
- **Xuất hiện ở:** type-hint `delegation_service: DelegationServicePort | None` ở `graph/nodes.py:145`, `graph/runtime.py:35`, `orchestrator/loop.py:99,218`; comment `supervisor/graph.py:42`.
- **Biến/method dùng ở:** graph node gọi `delegation_service.delegate(parent_session, target, spec, policy)` để chạy ủy thác (graph/nodes.py); `available_targets()` để gợi ý prompt (`orchestrator/loop.py:29` `_delegation_prompt`).

### `ToolMiddleware`
- **Khởi tạo bởi:** không (Protocol). Các impl cụ thể: `TimingLog`, `PolicyGate`, `Retry`, `CondenseResult`, `BudgetGuard` (middleware/*.py), khởi tạo và đăng ký ở `core/bootstrap.py:37-52`.
- **Xuất hiện ở:** chỉ tên trong docstring `AgentKernel.use` (kernel.py:58); pipeline lưu ở `AgentKernel._middlewares` (kernel.py:45).
- **Biến/method dùng ở:** `AgentKernel.use(middleware)` append vào `_middlewares` (kernel.py:61, raise nếu `_frozen`); `execute_tool` bọc ngược qua `_wrap(mw, handler)` (kernel.py:137-138) rồi `handler(request)` (140) — mỗi mw nhận `(request, nxt)`.

### `ToolDescriptor`
- **Khởi tạo bởi:** `core/registry.py:20` (`DEFAULT_DESCRIPTOR`) và `register_tool` (registry.py:81: `ToolDescriptor(kind=..., idempotent=..., risk=...)`). Không tạo ở đâu khác trong runtime.
- **Xuất hiện ở:** field `ToolResolution.descriptor` (registry.py:26), dict `self._descriptors` (registry.py:50,108).
- **Biến/method dùng ở:** chỉ trong core — `resolve_tool` gắn descriptor vào `ToolResolution` (registry.py:108); `AgentKernel.execute_tool` đọc `resolution.descriptor.kind/idempotent/risk` ghi vào metadata envelope (kernel.py:130-132). Không có call-site runtime ngoài core/ (retry middleware đọc qua metadata envelope, không trực tiếp tham chiếu class).

## delegation/ — chokepoint giao việc cho agent con: policy → child session → progress → events → result (Epic E10/E15)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `DelegationRegistry` | giải `target` → đúng 1 handler `DelegationPort`, fail tường minh khi không/đa khớp; freeze sau khi compose để bất biến lúc chạy | `register(handler)`, `freeze()`, `resolve(target)→DelegationPort`, `targets()→tuple[str,...]`; field `_handlers`, `_frozen`, `_lock` (RLock) | `core.ports.DelegationPort`; `threading` | tạo ở `delegation/bootstrap.py:18`; `DelegationManager.__init__` gọi `.freeze()` (manager.py:32), `.resolve()` (manager.py:120), `.targets()` (manager.py:35) |
| `InMemoryDelegationStore` | source-of-truth v1 cho 1 delegation: request/progress/result; ghi progress **có thứ tự + idempotent** (theo `sequence` và `event_id`); thread-safe | `start(request)`, `append_progress(progress)`, `finish(result)`, `progress(id)→tuple`, `result(id)→DelegationResult\|None`; field `_requests/_progress/_results/_lock` | `core.schemas.DelegationProgress/DelegationRequest/DelegationResult`; `threading` (implement `DelegationStorePort`) | tạo ở `delegation/bootstrap.py:23`; truyền vào `DelegationManager(store=...)`, gọi qua `self.store` trong manager.py |
| `DelegationPolicyEngine` | enforce trần depth/budget/capability-scope trước khi giao việc; clamp policy yêu cầu về policy hợp lệ; raise `PermissionError` khi vượt depth/scope | `validate(parent, requested)→DelegationPolicy`; field `max_steps` (mặc định 100), `max_depth` (mặc định 8) | `core.schemas.DelegationPolicy`; `core.session.KernelSession` | tạo mặc định trong `DelegationManager.__init__` (manager.py:31) hoặc inject; gọi `self.policy.validate()` (manager.py:80) |
| `DelegationManager` | chokepoint tuần tự một-lượt-giao-việc: validate policy → start store → event started → resolve handler → tạo child session → chạy handler với progress_sink → gộp artifacts → finish (store + event finished); implement `DelegationServicePort` | `available_targets()→tuple[str,...]`, `delegate(parent, target, spec, policy=None)→DelegationResult`; static `_event_fields`, `_finish`; field `registry/sessions/store/policy` | `DelegationRegistry`, `DelegationPolicyEngine`, `core.ports.DelegationStorePort`, `core.session.KernelSession/SessionFactory`, `core.schemas.Delegation*`; `uuid` | tạo ở `delegation/bootstrap.py:20`; ở runtime gọi `.delegate()` từ `graph/nodes.py:173` (delegation_node) và `supervisor/graph.py:176`; `.available_targets()` từ `orchestrator/loop.py:32` |

> Glue (hàm, KHÔNG phải class): `create_delegation_service(kernel)` (bootstrap.py:13) — composition root của module: trả `None` nếu `kernel.config["delegation"].enabled` falsy; ngược lại tạo `DelegationRegistry`, đăng ký `LangGraphDelegationAgent(target)` (mặc định target `"agent:general"`), rồi dựng `DelegationManager` với `SessionFactory(kernel=...)` + `InMemoryDelegationStore()`. Trả kiểu `DelegationServicePort | None`.

**Call-sites:**

### `DelegationRegistry`
- **Khởi tạo bởi:** `create_delegation_service` (delegation/bootstrap.py:18). Trong test: `tests/conftest.py:121`, `tests/test_delegation.py:15/75/151`, `tests_audit/test_session_delegation_state_machine.py:156/209`.
- **Xuất hiện ở:** export tại `delegation/__init__.py:4`; import trong `bootstrap.py:9`, `manager.py:16`; tham số `registry: DelegationRegistry` trong `DelegationManager.__init__` (manager.py:23).
- **Biến/method dùng ở:** runtime chỉ qua `DelegationManager`: `self.registry.freeze()` (manager.py:32), `self.registry.resolve(target)` (manager.py:120), `self.registry.targets()` (manager.py:35). `.register(handler)` được gọi ở `bootstrap.py:19` (runtime) và trong các test. Nội bộ: `resolve` lọc bằng `handler.can_handle(target)` và dùng `handler.name` để báo lỗi đa khớp.

### `InMemoryDelegationStore`
- **Khởi tạo bởi:** `create_delegation_service` (delegation/bootstrap.py:23). Trong test: `tests/conftest.py:130`, `tests/test_delegation.py:17/76/156`, `tests_audit/test_session_delegation_state_machine.py:174/186/211`.
- **Xuất hiện ở:** export tại `delegation/__init__.py:5`; import trong `bootstrap.py:10`. Truyền cho `DelegationManager(store=...)`; bên trong manager dùng qua kiểu trừu tượng `DelegationStorePort` (manager.py:6,25), không gắn cứng tên class này.
- **Biến/method dùng ở:** runtime qua `DelegationManager.self.store`: `.start(request)` (manager.py:90,113), `.finish(result)` (manager.py:51 trong `_finish`), `.append_progress(progress)` (manager.py:147 trong `progress_sink`), `.progress(delegation_id)` (manager.py:165,183 để gộp artifacts). Method `.result(id)` không có call-site runtime (chỉ dùng ở tests). Nội bộ: `append_progress` bỏ qua trùng `event_id` (idempotent) và ép `sequence == len(items)+1`.

### `DelegationPolicyEngine`
- **Khởi tạo bởi:** `DelegationManager.__init__` khi `policy is None` → `DelegationPolicyEngine()` (manager.py:31). `bootstrap.py` không truyền `policy` nên dùng mặc định này (runtime). Khởi tạo trực tiếp chỉ trong `tests_audit/test_session_delegation_state_machine.py:139/145`.
- **Xuất hiện ở:** import trong `manager.py:15`; tham số `policy: DelegationPolicyEngine | None` của `DelegationManager.__init__` (manager.py:26). Không export ở `delegation/__init__.py`.
- **Biến/method dùng ở:** runtime: `self.policy.validate(parent_session, requested_policy)` trong `delegate` (manager.py:80); nếu raise → nhánh `outcome="rejected"`. Đọc field `max_steps/max_depth` chỉ nội bộ `validate`. `validate` đọc `parent.identity.depth` và `parent.allowed_capabilities` của `KernelSession`.

### `DelegationManager`
- **Khởi tạo bởi:** `create_delegation_service` (delegation/bootstrap.py:20). Trong test: `tests/conftest.py:129`, `tests/test_delegation.py:18/77/153`, `tests_audit/...:212`.
- **Xuất hiện ở:** export tại `delegation/__init__.py:3`; import trong `bootstrap.py:8`. Là implementation của `DelegationServicePort`; ở runtime nó được truyền dưới kiểu `DelegationServicePort | None` qua: `ui/server.py:242→250` → `orchestrator/loop.py` (param `delegation_service`, loop.py:99/218) / `graph/runtime.py:35` / `graph/nodes.py:145` (`delegation_node`) / `supervisor/graph.py:42` & `supervisor/loop.py`.
- **Biến/method dùng ở:** runtime gọi `.delegate(parent, target, spec, policy)` ở `graph/nodes.py:173` (delegation_node) và `supervisor/graph.py:176`; `.available_targets()` ở `orchestrator/loop.py:32` (`_delegation_prompt`). Nội bộ `delegate`: dùng `self.policy.validate`, `self.store.start/append_progress/finish/progress`, `self.registry.resolve`, `self.sessions.create_child(...)`, `handler.run(request, child, progress_sink)`; publish event `delegation.started`/`delegation.progress`/`delegation.finished` qua `parent.kernel.events.publish` / `child.kernel.events.publish`; đóng child bằng `child.complete_task(...)` / `child.fail_task(...)`.

Hai implementation runtime của `DelegationPort` (handler được `registry.resolve` trả về và `DelegationManager` gọi `.run`): `LangGraphDelegationAgent` (adapters/agents/langgraph_agent.py:21, đăng ký ở bootstrap.py:19) và `ScriptedDelegationAgent` (adapters/agents/scripted.py:17, dùng trong tests). `InMemoryDelegationStore` là implementation runtime của `DelegationStorePort`; `DelegationManager` là implementation runtime của `DelegationServicePort`.

## adapters/ — agent con triển khai `DelegationPort` (Scripted deterministic + LangGraph thật) (Epic E10/E15)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `ScriptedDelegationAgent` | Hiện thực `DelegationPort` xác định (deterministic) cho test/smoke run: phát ra danh sách artifact định sẵn không gọi LLM/graph (`scripted.py:17`) | `__init__(target, artifacts)`; fields `name`/`target`/`artifacts`; `can_handle(target)→bool` (`:23`); `run(request, child_session, progress_sink)→DelegationResult` (`:26`) | `core.schemas` (`ArtifactEnvelope`/`DelegationProgress`/`DelegationRequest`/`DelegationResult`), `core.ports.ProgressSink`, `core.session.KernelSession`, `uuid` | `tests/conftest.py:124` (worker mặc định), `tests/test_delegation.py:16`, `tests_audit/...:46` (`registry.register(...)`) — **chỉ tests** |
| `LangGraphDelegationAgent` | Hiện thực `DelegationPort` "thật": chạy agent con bằng LangGraph session-bound, stream từng bước thành artifact `agent_step` (`langgraph_agent.py:21`) | `__init__(target="agent:general")`; fields `name`/`target`; `can_handle(target)→bool` (`:28`); `run(request, child_session, progress_sink)→DelegationResult` (`:31`) | `graph.runtime.build_agent_graph`/`COMPAT_SYSTEM_PROMPT`, `graph.state` (`new_agent_state`/`budget_from_state`/`AgentState`), `discipline.Budget`, `langgraph...InMemorySaver`, `core.schemas`, `core.ports.ProgressSink`, `core.session.KernelSession` | `delegation/bootstrap.py:19` (`registry.register(...)` — **đường runtime**); `tests/test_delegation.py:152`, `tests/test_supervisor_loop.py:144` |

> Glue (hàm, KHÔNG phải class): module `adapters/agents/` chỉ tái-export qua `adapters/agents/__init__.py` (`__all__ = ["LangGraphDelegationAgent", "ScriptedDelegationAgent"]`); không có hàm tự do. Cả hai class đều duck-type khớp Protocol `core.ports.DelegationPort` (`core/ports.py:33`, yêu cầu field `name`, `can_handle`, `run`).

**Luồng dữ liệu chung:** cả hai nhận `DelegationRequest` (đọc `request.delegation_id`, `request.parent_task_id`, `request.target`, `request.spec.objective`; LangGraph thêm `request.policy.max_steps`), phát `DelegationProgress` (bọc `ArtifactEnvelope`) qua `progress_sink` cho từng bước, và trả về `DelegationResult` (chứa `artifacts: tuple[ArtifactEnvelope]`). Không class nào tự sinh `DelegationRequest`/`DelegationResult` — đó là schema của `core.schemas` do `DelegationManager` truyền vào.

**Call-sites:**

### `ScriptedDelegationAgent`
- **Khởi tạo bởi:** chỉ trong test — `tests/conftest.py:124` (`ScriptedDelegationAgent(agent_id, ...)` làm worker fallback), `tests/test_delegation.py:16`, `tests_audit/test_acceptance_evidence_adversarial.py:46`. Không có call-site runtime.
- **Xuất hiện ở:** def tại `adapters/agents/scripted.py:17`; re-export `adapters/agents/__init__.py:2,4`; import ở `tests/test_delegation.py:2`, `tests/conftest.py:11`, `tests_audit/...:15`.
- **Biến/method dùng ở:** `register(...)` của `DelegationRegistry` đọc field `.name` (`delegation/registry.py:19`), gọi `.can_handle(target)` khi `resolve` (`:30`); `DelegationManager` gọi `handler.run(request, child, progress_sink)` (`delegation/manager.py:160`). Mọi luồng tới class này hiện **chỉ tests** (đăng ký vào registry trong test). Nội bộ `run` đọc `self.artifacts`, `request.delegation_id`, `request.parent_task_id`, `request.target`, `request.spec.objective`, `child_session.identity.session_id`.

### `LangGraphDelegationAgent`
- **Khởi tạo bởi:** runtime tại `delegation/bootstrap.py:19` — `create_delegation_service` gọi `registry.register(LangGraphDelegationAgent(target))` với `target` lấy từ `config["delegation"]["default_target"]` (mặc định `"agent:general"`). Ngoài ra `tests/test_delegation.py:152`, `tests/test_supervisor_loop.py:144`.
- **Xuất hiện ở:** def tại `adapters/agents/langgraph_agent.py:21`; re-export `adapters/agents/__init__.py:1,4`; import runtime ở `delegation/bootstrap.py:4`; import test ở `tests/test_delegation.py:2`, `tests/test_supervisor_loop.py:8`.
- **Biến/method dùng ở:** sau khi `register`, `DelegationRegistry.resolve(target)` lọc qua `.can_handle` rồi `DelegationManager.run_to_completion` gọi `handler.run(request, child, progress_sink)` (`delegation/manager.py:120,160`) — đây là đường runtime. Nội bộ `run` đọc `request.spec.objective`, `request.policy.max_steps`, `request.delegation_id`, `request.parent_task_id`, `request.target`, `child_session.identity.session_id`; dựng graph qua `build_agent_graph(session=child_session, checkpointer=InMemorySaver(), delegation_service=None)` (delegation đệ quy bị tắt ở v1), stream `stream_mode="values"`, dùng `budget_from_state(...).steps` để gắn `agent_step`, và suy `outcome`/`error` từ `final_state.get("status")`.

## control/ (A) — đường PHÁT event đã validate/redact/đánh số (Epic E21)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `Actor` | Ai/cái gì gây ra event (`type`∈ACTOR_TYPES, `id`); frozen dataclass, validate ở `__post_init__` | `type`, `id`; `as_dict`/`from_dict` | `ControlContractError`; `ACTOR_TYPES` (events.py) | runtime: `SupervisorContext.emit` tạo `Actor(type="runtime", id="supervisor")` (supervisor/graph.py:67); là field của `RuntimeEvent` |
| `TraceContext` | Trace/span của event để nối nhân-quả (`trace_id`/`span_id`/`parent_span_id`) | `as_dict`/`from_dict`; `new_root()`, `child()` | `ControlContractError` | runtime: `TraceContext.new_root()` (supervisor/graph.py:62), field của `RuntimeEvent`; export `control` (graph.py:14) |
| `RedactionInfo` | Metadata độ-nhạy đính kèm event (`level`∈VISIBILITY_LEVELS, `has_secret`, `redacted_fields`) | `as_dict`/`from_dict` | `ControlContractError`; `VISIBILITY_LEVELS` (events.py) | runtime: `EventEmitter.emit` tạo placeholder `RedactionInfo()` (emitter.py:83); `Redactor.apply` tạo bản thật (redaction.py:68) |
| `RuntimeEvent` | Envelope DUY NHẤT của control-plane; tách `payload` (raw) khỏi `ui_payload` (đã redact); validate toàn bộ ở `__post_init__` | fields (`event_type`,`session_id`,`actor`,`trace`,`redaction`,`seq`,`ui_payload`,...); `as_dict`/`from_dict`; auto `event_id`/`created_at` | `Actor`,`TraceContext`,`RedactionInfo`,`ControlContractError`,`utc_now` | runtime: tạo trong `EventEmitter.emit` (emitter.py:78) và `FakeControlServer` (tools/fake_control_server.py:129); là tham số của `EventSinkPort.emit`, `Redactor.apply`, `BusEventSink.emit` |
| `SessionSeq` | Bộ cấp số thứ tự đơn điệu mỗi session (thread-safe) để UI sắp/khử trùng | `next(session_id)`, `peek(session_id)` | stdlib (`threading`) | runtime: `EventEmitter.__init__` mặc định `SessionSeq()` (emitter.py:51), gọi `.next()` ở `emit_event` (emitter.py:57) |
| `EventTypeSpec` | Khai báo 1 event_type: `visibility`/`durable`/`redact_for_ui`/`checkpoint_candidate` | `as_dict` | stdlib | nơi tạo: `parse_event_registry` (event_registry.py:86); trả về bởi `EventTypeRegistry.get` |
| `EventTypeRegistry` | Catalog trung tâm — chặn event_type "tự bịa"; cổng validate trước khi publish | `assert_known`, `get`, `visibility`, `types`, `__contains__` | `ControlContractError`,`EventTypeSpec` | runtime: `EventEmitter.__init__` mặc định `load_event_registry()` (emitter.py:49), gọi `.get()` ở `emit_event` (emitter.py:56) |
| `BusEventSink` | Adapter `EventBus` → `EventSinkPort`: publish dict envelope dưới `topic=event_type` cho subscriber cũ (EventLogger) | `emit(event)` → `bus.publish(event.event_type, event.as_dict())` | `EventBus` (core.events), `RuntimeEvent` | runtime: `bus_emitter` tạo `BusEventSink(bus)` (emitter.py:95) |
| `EventEmitter` | Đường publish DUY NHẤT đã validate+seq+redact rồi fan-out tới sinks | `emit_event(event)` (validate→seq→redact→fan-out); `emit(...)` builder tiện dụng | `EventTypeRegistry`,`Redactor`,`SessionSeq`,`EventSinkPort`,`RuntimeEvent`,`Actor`/`TraceContext`/`RedactionInfo`,`replace` | runtime: `SupervisorContext.emitter` (supervisor/graph.py:48) gọi `.emit()` (graph.py:64); luồng vào qua `supervisor/loop.py` (param `emitter`); tạo bởi `bus_emitter` |
| `Redactor` | Biên an-toàn-bí-mật: tách `payload`→`ui_payload` + `RedactionInfo`, mask đệ quy theo SECRET_KEYS, không sửa bản gốc | `redact(payload)`→(copy, paths); `apply(event, level=)`→RuntimeEvent mới | `RedactionInfo`,`RuntimeEvent`,`replace`; `SECRET_KEYS`/`REDACTED` | runtime: `EventEmitter.__init__` mặc định `Redactor()` (emitter.py:50), gọi `.apply()` ở `emit_event` (emitter.py:58); `FakeControlServer` gọi `.apply()` (tools/fake_control_server.py:138) |
| `EventSinkPort` | Seam transport/storage emitter đẩy event tới (Protocol — Kafka/Redis sau này thay được) | `emit(event: RuntimeEvent) -> None` | `RuntimeEvent` | không (Protocol); impl runtime = `BusEventSink`; là kiểu của `EventEmitter._sinks` (emitter.py:42) |
| `ControlContractError` | Lỗi hợp đồng chung E21 (subtype `ValueError`) — object control-plane sai thì không bao giờ tồn tại/publish | (chỉ là exception) | stdlib (`ValueError`) | raise ở mọi `__post_init__` của events.py + `EventTypeRegistry.assert_known` + `parse_event_registry` |
| `EventReplayBuffer` | Ring buffer (D4: 2048/session) trên event dict — dedup theo `event_id`, catch-up Last-Event-ID, tín hiệu resync khi rớt khỏi ring (reconnect) | `append`, `load_jsonl`, `events`, `oldest_seq`/`newest_seq`, `needs_resync`, `events_after` | stdlib (`deque`,`json`,`Path`) | runtime: `FakeControlServer` tạo `EventReplayBuffer()` rồi gọi `needs_resync`/`events_after` (tools/fake_control_server.py:60,80,83) |

> Glue (hàm, KHÔNG phải class): `utc_now()` (events.py:28) — sinh timestamp ISO-UTC cho `RuntimeEvent.created_at`. `parse_event_registry(data, source=)` (event_registry.py:64) — dựng `EventTypeRegistry` từ dict YAML, ép event_type phải dotted + visibility hợp lệ. `load_event_registry(path=)` (event_registry.py:96) — đọc `config/runtime_event_types.yaml` rồi gọi `parse_event_registry`; là default registry của `EventEmitter`. `bus_emitter(bus, **kwargs)` (emitter.py:93) — factory dựng `EventEmitter([BusEventSink(bus)])` (mặc định v1 in-process).

**Call-sites:**

### `Actor`
- **Khởi tạo bởi:** runtime `SupervisorContext.emit` (supervisor/graph.py:67) `Actor(type="runtime", id="supervisor")`; `EventEmitter.emit` nhận `actor` đã dựng. Khác: tools/gen_t1_fixture.py:43, tools/fake_control_server.py:132 (công cụ/fake); còn lại tests.
- **Xuất hiện ở:** def control/events.py:33; export control/__init__.py; import supervisor/graph.py:14, control/emitter.py:22; field của `RuntimeEvent.actor`; param của `EventEmitter.emit`.
- **Biến/method dùng ở:** `RuntimeEvent.as_dict` gọi `actor.as_dict()` (events.py:164); `from_dict` gọi `Actor.from_dict` (events.py:177). `__post_init__` đọc `self.type`/`self.id`.

### `TraceContext`
- **Khởi tạo bởi:** runtime `TraceContext.new_root()` ở `SupervisorContext.emit` (supervisor/graph.py:62, lưu vào `ctx.trace`). Khác: tools/gen_t1_fixture.py:44.
- **Xuất hiện ở:** def control/events.py:54; import supervisor/graph.py:14, control/emitter.py:22; field `RuntimeEvent.trace`; param `EventEmitter.emit`; `SupervisorContext.trace` (graph.py:49).
- **Biến/method dùng ở:** `new_root()`/`child()` cấp trace mới; `RuntimeEvent.as_dict`→`trace.as_dict()` (events.py:165); `child()` đọc `self.trace_id`/`self.span_id` (chỉ định nghĩa ở đây, chưa thấy call-site runtime của `child`).

### `RedactionInfo`
- **Khởi tạo bởi:** runtime placeholder `RedactionInfo()` trong `EventEmitter.emit` (emitter.py:83); bản thật trong `Redactor.apply` (redaction.py:68).
- **Xuất hiện ở:** def control/events.py:86; import control/emitter.py:22, control/redaction.py:13; field `RuntimeEvent.redaction`.
- **Biến/method dùng ở:** `Redactor.apply` đọc `event.redaction.level` làm fallback (redaction.py:69); `RuntimeEvent.as_dict`→`redaction.as_dict()` (events.py:168).

### `RuntimeEvent`
- **Khởi tạo bởi:** nơi tạo runtime DUY NHẤT trên đường publish = `EventEmitter.emit` (control/emitter.py:78). Ngoài ra `FakeControlServer.publish` (tools/fake_control_server.py:129) và `RuntimeEvent.from_dict` (deserialise). 
- **Xuất hiện ở:** def control/events.py:114; export control/__init__.py; import control/emitter.py:22, control/redaction.py:13, control/ports.py:11; return-type của `EventEmitter.emit`/`emit_event`/`Redactor.apply`; param của `EventSinkPort.emit`/`BusEventSink.emit`/`Redactor.apply`.
- **Biến/method dùng ở:** `EventEmitter.emit_event` đọc `event.event_type`/`event.seq`/`event.session_id` rồi `replace(event, seq=...)` (emitter.py:56-58); `BusEventSink.emit` gọi `event.event_type`+`event.as_dict()` (emitter.py:36); `Redactor.apply` đọc `event.payload`/`event.redaction` (redaction.py:67-69).

### `SessionSeq`
- **Khởi tạo bởi:** runtime `EventEmitter.__init__` mặc định `seq or SessionSeq()` (emitter.py:51). (Tests truyền `SessionSeq()` rõ ràng.)
- **Xuất hiện ở:** def control/events.py:193; export control/__init__.py; import control/emitter.py:22; param `EventEmitter.__init__` (`seq: SessionSeq | None`).
- **Biến/method dùng ở:** `EventEmitter.emit_event` gọi `self._seq.next(event.session_id)` (emitter.py:57). `peek` chỉ dùng ở tests. Nội bộ `self._lock`/`self._counters`.

### `EventTypeSpec`
- **Khởi tạo bởi:** nơi tạo DUY NHẤT = `parse_event_registry` (event_registry.py:86).
- **Xuất hiện ở:** def control/event_registry.py:23; export control/__init__.py; type của `EventTypeRegistry._specs`/return `get`.
- **Biến/method dùng ở:** runtime `EventEmitter.emit_event` đọc `spec.visibility` (emitter.py:58, qua `registry.get(...).visibility`); `EventTypeRegistry.visibility` đọc `.visibility` (event_registry.py:58).

### `EventTypeRegistry`
- **Khởi tạo bởi:** runtime `load_event_registry`→`parse_event_registry`→`EventTypeRegistry(specs)` (event_registry.py:93); `EventEmitter.__init__` mặc định `load_event_registry()` (emitter.py:49). Khác: tools/fake_control_server.py:53 (param).
- **Xuất hiện ở:** def control/event_registry.py:40; export control/__init__.py; import control/emitter.py:21; param `EventEmitter.__init__` (`registry`).
- **Biến/method dùng ở:** runtime `EventEmitter.emit_event` gọi `self._registry.get(event.event_type)` (emitter.py:56) — đây là cổng chặn event lạ. `assert_known`/`__contains__`/`types` chủ yếu ở tests/command-path. Nội bộ `get`→`assert_known`→đọc `self._specs`.

### `BusEventSink`
- **Khởi tạo bởi:** runtime `bus_emitter` → `EventEmitter([BusEventSink(bus)])` (emitter.py:95).
- **Xuất hiện ở:** def control/emitter.py:28; export control/__init__.py:32,104.
- **Biến/method dùng ở:** `EventEmitter.emit_event` gọi `sink.emit(final)` (emitter.py:60) qua giao diện `EventSinkPort`. Nội bộ `self._bus.publish(...)` (emitter.py:36).

### `EventEmitter`
- **Khởi tạo bởi:** runtime qua factory `bus_emitter` (emitter.py:95); instance được tiêm vào `SupervisorContext.emitter` (supervisor/graph.py:48) và luồng qua các builder ở supervisor/loop.py (param `emitter`, lines 57/67/85/95/119/141). Repo không có nơi gọi `bus_emitter` ngoài tools/tests → emitter được caller/host bên ngoài wire vào.
- **Xuất hiện ở:** def control/emitter.py:39; export control/__init__.py:32,103; import supervisor/graph.py:14; type `SupervisorContext.emitter` (graph.py:48).
- **Biến/method dùng ở:** runtime `SupervisorContext.emit` gọi `self.emitter.emit(topic, session_id=..., actor=..., trace=..., payload=..., task_id=...)` (graph.py:64). Nội bộ `emit`→`emit_event`→`self._registry.get`/`self._seq.next`/`self._redactor.apply`/`sink.emit`.

### `Redactor`
- **Khởi tạo bởi:** runtime `EventEmitter.__init__` mặc định `redactor or Redactor()` (emitter.py:50); `FakeControlServer` cũng tạo `Redactor` (tools/fake_control_server.py, gọi `.apply` line 138).
- **Xuất hiện ở:** def control/redaction.py:37; export control/__init__.py; import control/emitter.py:23; param `EventEmitter.__init__` (`redactor`).
- **Biến/method dùng ở:** runtime `EventEmitter.emit_event` gọi `self._redactor.apply(staged, level=spec.visibility)` (emitter.py:58). Nội bộ `apply`→`self.redact`→`self._walk` (đệ quy dict/list), đọc `self.secret_keys`.

### `EventSinkPort`
- **Khởi tạo bởi:** không (Protocol, `@runtime_checkable`). Impl cụ thể runtime = `BusEventSink`.
- **Xuất hiện ở:** def control/ports.py:15; export control/__init__.py:51,106; import control/emitter.py:23; param `EventEmitter.__init__` (`sinks: Iterable[EventSinkPort]`, emitter.py:42).
- **Biến/method dùng ở:** `EventEmitter.emit_event` lặp `for sink in self._sinks: sink.emit(final)` (emitter.py:59-60) — chỉ dựa vào method `emit`.

### `ControlContractError`
- **Khởi tạo bởi:** raise (không instantiate-để-giữ) ở mọi `__post_init__` của `Actor`/`TraceContext`/`RedactionInfo`/`RuntimeEvent` (events.py); `EventTypeRegistry.assert_known` (event_registry.py:49); `parse_event_registry` (event_registry.py:66,69,74,79,82).
- **Xuất hiện ở:** def control/errors.py:11; import control/events.py:21, control/event_registry.py:16 (và các module control khác như commands/command_registry).
- **Biến/method dùng ở:** dùng như exception type — caller bắt được cả `ControlContractError` lẫn `ValueError`. Runtime gate: event_type lạ ở `EventEmitter.emit_event` ném qua `registry.get` (emitter.py:56).

### `EventReplayBuffer`
- **Khởi tạo bởi:** runtime `FakeControlServer.__init__` tạo `EventReplayBuffer()` (tools/fake_control_server.py:60). (Tests dựng với `maxlen=` riêng.)
- **Xuất hiện ở:** def control/replay.py:23; import tools/fake_control_server.py:37, tests/test_fake_control_server.py:19.
- **Biến/method dùng ở:** `FakeControlServer` gọi `buffer.needs_resync(last_seq)` (fake_control_server.py:80) và `buffer.events_after(last_seq)` (line 83) khi client reconnect; `append`/`load_jsonl` nạp event. Nội bộ `append` quản `self._events` (deque) + `self._ids` (khử trùng theo `event_id`); `events_after`/`needs_resync` đọc `seq`.

## control/ (B) — NHẬN lệnh người-dùng/UI + approval-gate + snapshot read-model (Epic E21)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `IssuedBy` | Danh tính người ra lệnh (human/agent/system) — đính kèm mọi `RuntimeCommand` cho authz + audit; tồn tại để "lệnh nào cũng biết ai bấm" | fields `type`/`user_id`/`agent_id`; `__post_init__` ép `type ∈ ISSUER_TYPES` + human cần user_id, agent cần agent_id; `as_dict`/`from_dict` | `control.errors.ControlContractError`; `ISSUER_TYPES` | `RuntimeCommand.issued_by` (control/commands.py:60,95); `gen_ts_contracts.py` (sinh .d.ts) |
| `RuntimeCommand` | Shape DUY NHẤT cho mọi can thiệp UI/human (pause/resume/inject…); UI không sửa state trực tiếp mà submit cmd này | fields `command_type`/`session_id`/`issued_by`/`idempotency_key`/`payload`/`command_id`/`schema_version`; `as_dict`/`from_dict`; validate non-empty + `issued_by` là IssuedBy | `IssuedBy`; `ControlContractError`; stdlib `uuid`/`datetime` | `parse_command` (commands.py:161); `fake_control_server.submit_command` (qua parse_command, tools/fake_control_server.py:104); `gen_ts_contracts.py` |
| `CommandAck` | Biên nhận đồng bộ của POST /api/commands: `received` (đã xếp hàng) hoặc `rejected` (có reason); `seq` nối vào SSE | fields `command_id`/`status`/`seq`/`rejection_reason`; validate `status ∈ ACCEPT_STATUSES` + rejected phải có reason; `as_dict`/`from_dict` | `ControlContractError`; `ACCEPT_STATUSES` | `fake_control_server.submit_command` (tạo cả 2 nhánh received/rejected, tools/fake_control_server.py:109,118); `gen_ts_contracts.py` |
| `CommandTypeSpec` | Một dòng khai báo lệnh: `apply_at` (khi áp dụng) + `requires_permission` (quyền cần) | fields `command_type`/`apply_at`/`requires_permission`; `as_dict` | `—` (dataclass thuần) | `CommandTypeRegistry._specs`; `parse_command_registry` (nơi tạo duy nhất, command_registry.py:84) |
| `CommandTypeRegistry` | Bảng tra "lệnh nào hợp lệ, áp dụng khi nào, cần quyền gì"; lệnh lạ bị từ chối tại gateway | `assert_known`/`get`/`apply_at`/`requires_permission`/`types`/`__contains__` | `CommandTypeSpec`; `ControlContractError` | `parse_command_registry`/`load_command_registry` (tạo); `FakeControlServer.command_registry` + `.assert_known` gate (tools/fake_control_server.py:62,105) |
| `RuntimeCheckpoint` | Hợp đồng approval-gate: điểm runtime PAUSE chờ người duyệt trước hành động rủi ro; bắt đầu `waiting`, chỉ resolve một lần | fields `checkpoint_type`/`session_id`/`risk_level`/`status`/`payload`; `is_waiting`; `with_status` (ép transition waiting→terminal); `as_dict`/`from_dict` | `ControlContractError`; `CHECKPOINT_STATUSES`/`RESOLVED_STATUSES`/`RISK_LEVELS`; stdlib `uuid`/`replace` | `gen_ts_contracts.py` (sinh .d.ts, tools/gen_ts_contracts.py:44). Runtime khác chỉ tham chiếu qua event `checkpoint.reached` trong `build_snapshot`, không instantiate trực tiếp |
| `Permission` | Hồ sơ năng lực per-agent người sửa được (allowed_tools + cờ can_*), có biên `effective_from`; immutable, `patched` sinh bản kế tiếp | fields cờ + `allowed_tools` + `effective_from`; `allows_tool`; `patched` (patch một phần, chặn key lạ qua `_FIELDS`); `as_dict`/`from_dict` | `ControlContractError`; `EFFECTIVE_FROM`; `_FIELDS`; stdlib `replace` | `gen_t1_fixture.py` (tạo fixture, tools/gen_t1_fixture.py:51); `gen_ts_contracts.py`. (Persist/PolicyGate là B5 — chưa có call-site runtime trong repo này) |
| `AgentView` | Một node trong Agent Graph + thân Inspector; fields optional (permission/allowed_tools/context_packet) chỉ sáng khi event mang theo (F6) | fields `agent_id`/`role`/`status`/`round_no`/`allowed_tools`/`last_output_summary`/`context_packet`/`permission`; validate `status ∈ AGENT_STATUSES`; `as_dict`/`from_dict` | `ControlContractError`; `AGENT_STATUSES` | `build_snapshot` (tạo từng node, control/snapshot.py:305); `TaskLoopSnapshot.agents`; `gen_ts_contracts.py` |
| `TaskLoopSnapshot` | Read-model UI render cho một session (status/round/orchestrator/agents/tool_calls/checkpoints/acceptance); là projection chứ không phải state | fields kể trên; `as_dict`/`from_dict`; chỉ validate `session_id` non-empty | `AgentView`; `ControlContractError`; stdlib | `build_snapshot` (nơi tạo runtime, control/snapshot.py:318); `FakeControlServer` GET /api/snapshot (qua build_snapshot, tools/fake_control_server.py:73); `gen_ts_contracts.py` |

> Glue (hàm, KHÔNG phải class): `parse_command` (commands.py:151) — cổng validate dict→RuntimeCommand, thiếu `idempotency_key`/`issued_by` thì raise để gateway từ chối trước khi vào queue. `parse_command_registry`/`load_command_registry` (command_registry.py:63,92) — parse/nạp `config/runtime_command_types.yaml` thành registry. `build_snapshot` (snapshot.py:189) — fold chuỗi `loop.*` event → `TaskLoopSnapshot`; chỉ đọc `ui_payload` đã redact cho field free-form (F2), suy status agent (done/running/waiting/pending) theo turn/decision/checkpoint. Các helper nội bộ `_fields`/`_tool_status`/`_norm_call`/`see` phục vụ riêng fold này.

**Call-sites:**

### `IssuedBy`
- **Khởi tạo bởi:** nội bộ qua `RuntimeCommand.from_dict` → `IssuedBy.from_dict(...)` (control/commands.py:95). Runtime đường gateway tạo gián tiếp khi `parse_command`. Trong test: `tests/test_control_contracts.py:100,123`.
- **Xuất hiện ở:** def `control/commands.py:29`; export `control/__init__.py:28,76`; import + danh sách contract trong `tools/gen_ts_contracts.py:27,41`; type của field `RuntimeCommand.issued_by` (commands.py:60).
- **Biến/method dùng ở:** `RuntimeCommand.__post_init__` kiểm `isinstance(self.issued_by, IssuedBy)` (commands.py:71); `RuntimeCommand.as_dict` gọi `issued_by.as_dict()` (commands.py:84). `__post_init__` của chính nó tự kiểm `type`/`user_id`/`agent_id`.

### `RuntimeCommand`
- **Khởi tạo bởi:** `RuntimeCommand.from_dict` (commands.py:92), bản thân được gọi bởi `parse_command` (commands.py:161) → dùng trong `fake_control_server.submit_command` (tools/fake_control_server.py:104). Test: `tests/test_control_contracts.py:97`.
- **Xuất hiện ở:** def `control/commands.py:57`; export `control/__init__.py:29,73`; import `tools/gen_ts_contracts.py:27,42`. Docstring module commands.py + control/__init__.py:4 mô tả vai trò "shape duy nhất".
- **Biến/method dùng ở (runtime):** `fake_control_server` đọc `cmd.command_type` (gate registry), `cmd.session_id`/`cmd.idempotency_key` (khóa dedup), `cmd.command_id` (emit `command.received` + dựng `CommandAck`) tại tools/fake_control_server.py:105,112,117-118.

### `CommandAck`
- **Khởi tạo bởi (runtime):** `fake_control_server.submit_command` tạo nhánh `rejected` (tools/fake_control_server.py:109) và nhánh `received` (tools/fake_control_server.py:118). Test: `tests/test_control_contracts.py:128,130`; `tests_audit/test_contract_roundtrips.py:174-175`.
- **Xuất hiện ở:** def `control/commands.py:104`; export `control/__init__.py:27,74`; import `tools/fake_control_server.py:32`, `tools/gen_ts_contracts.py:27,43`.
- **Biến/method dùng ở (runtime):** `ack.as_dict()` trả body HTTP cho POST /api/commands (tools/fake_control_server.py:110,119); ack được cache vào `self._dedup` để trả lại y hệt khi idempotent (tools/fake_control_server.py:119).

### `CommandTypeSpec`
- **Khởi tạo bởi:** nơi tạo duy nhất là `parse_command_registry` (control/command_registry.py:84), một spec mỗi dòng YAML.
- **Xuất hiện ở:** def `control/command_registry.py:23`; export `control/__init__.py:20,81`; type của `CommandTypeRegistry.__init__(specs)` (command_registry.py:37) và return của `.get` (command_registry.py:49).
- **Biến/method dùng ở:** `CommandTypeRegistry.get/apply_at/requires_permission` đọc `spec.apply_at`/`spec.requires_permission` (command_registry.py:54,57). `as_dict` của nó: không thấy call-site runtime (chỉ phục vụ serialize/test).

### `CommandTypeRegistry`
- **Khởi tạo bởi:** `parse_command_registry` (command_registry.py:89) ← `load_command_registry` (command_registry.py:95). Runtime: `FakeControlServer.__init__` `command_registry or load_command_registry()` (tools/fake_control_server.py:62). Test: `tests/test_control_contracts.py:146,158`.
- **Xuất hiện ở:** def `control/command_registry.py:36`; export `control/__init__.py:19,80`; import + param type `tools/fake_control_server.py:31,54`.
- **Biến/method dùng ở (runtime):** `submit_command` gọi `self.command_registry.assert_known(cmd.command_type)` làm registry-gate F4 (tools/fake_control_server.py:105). `apply_at`/`requires_permission`/`types`/`get` chưa có call-site runtime ngoài đó (mới chỉ test/contract).

### `RuntimeCheckpoint`
- **Khởi tạo bởi:** `RuntimeCheckpoint.from_dict` (checkpoint.py:82). Runtime instantiate trực tiếp: chỉ trong `tools/gen_ts_contracts.py` để sinh .d.ts (gen_ts_contracts.py:44, qua import :26). Test: `tests/test_control_contracts.py:166,180`; `tests/test_gen_ts_contracts.py:55`.
- **Xuất hiện ở:** def `control/checkpoint.py:28`; export `control/__init__.py:15,86`; import `tools/gen_ts_contracts.py:26`.
- **Biến/method dùng ở:** trong runtime read-model, checkpoint của vòng đời thực đi qua event `checkpoint.reached` và được `build_snapshot` gom vào `snapshot.checkpoints` dưới dạng dict view (control/snapshot.py:296-301) — KHÔNG dựng instance `RuntimeCheckpoint`. `with_status`/`is_waiting` hiện chỉ được gọi trong tests.

### `Permission`
- **Khởi tạo bởi:** `Permission.from_dict` (permission.py:63). Runtime: `tools/gen_t1_fixture.py:51` dựng fixture; `tools/gen_ts_contracts.py:45` để sinh .d.ts. Test: `tests/test_control_contracts.py:185`. (B5 persist + PolicyGate/DelegationPolicy đọc bản mới nhất — mô tả trong docstring permission.py nhưng chưa có call-site trong repo này.)
- **Xuất hiện ở:** def `control/permission.py:20`; export `control/__init__.py:50,91`; import `tools/gen_t1_fixture.py:24`, `tools/gen_ts_contracts.py:29`.
- **Biến/method dùng ở:** `patched` (sinh bản kế tiếp cho `UpdateAgentPermission`, chặn key lạ qua `_FIELDS`) và `allows_tool` hiện chỉ thấy gọi trong tests (`tests/test_control_contracts.py:187-188`); runtime mới dùng constructor + `as_dict`. Snapshot chỉ truyền permission dạng dict (không phải instance Permission) qua `ui_payload` (snapshot.py:266-283).

### `AgentView`
- **Khởi tạo bởi:** `build_snapshot` dựng từng node (control/snapshot.py:305) và `AgentView.from_dict` trong `TaskLoopSnapshot.from_dict` (snapshot.py:128). Test: `tests/test_control_snapshot.py:117,119`; `tests_audit/test_contract_roundtrips.py:187-188`.
- **Xuất hiện ở:** def `control/snapshot.py:37`; export `control/__init__.py:53,99`; type của `TaskLoopSnapshot.agents` (snapshot.py:96); import `tools/gen_ts_contracts.py:30,46`.
- **Biến/method dùng ở (runtime):** `TaskLoopSnapshot.as_dict` gọi `a.as_dict()` cho mỗi agent (snapshot.py:113). `build_snapshot` đổ `meta[aid]` (role/round_no/allowed_tools/last_output_summary/context_packet/permission) vào constructor và suy `status` (snapshot.py:305-314).

### `TaskLoopSnapshot`
- **Khởi tạo bởi:** `build_snapshot` (nơi tạo runtime chính, control/snapshot.py:318) và `TaskLoopSnapshot.from_dict` (snapshot.py:122). Runtime: `FakeControlServer` GET /api/snapshot gọi `build_snapshot(self.buffer.events, session_id=...)` (tools/fake_control_server.py:73). Test: `tests/test_control_snapshot.py`; `tests_audit/test_contract_roundtrips.py:181`.
- **Xuất hiện ở:** def `control/snapshot.py:89`; export `control/__init__.py:53,98`; import `tools/gen_ts_contracts.py:30,47`; return-type của `build_snapshot` (snapshot.py:191).
- **Biến/method dùng ở (runtime):** fake server serialize qua `.as_dict()` để trả body /api/snapshot (đường tools/fake_control_server.py:73 → handler). `as_dict` gọi đệ quy `AgentView.as_dict` + copy các tuple field (pending_agent_calls/tool_calls/checkpoints/acceptance_status) tại snapshot.py:107-119.

## middleware/ — vòng pre/post (ToolMiddleware) bao quanh `AgentKernel.execute_tool` (Epic E02/E06/E10)

Mỗi class là một `ToolMiddleware` (protocol `core/middleware.py:11`) — một callable `(request: ToolRequest, nxt) -> dict`. Kernel ráp chuỗi tại `core/kernel.py:136-138`: `for mw in reversed(self._middlewares): handler = _wrap(mw, handler)`, nên **thứ tự đăng ký = ngoài → trong**. `_install_middleware` (`core/bootstrap.py:28-53`) đăng ký theo trật tự `timing → policy → retry → condense` ⇒ **TimingLog ngoài cùng** (bọc cả chuỗi), **PolicyGate** chặn trước khi `nxt` chạy, **Retry** re-invoke `nxt` khi kết quả non-ok, **CondenseResult** trong cùng (gần `core` nhất). Mỗi lần `kernel.use` chỉ `append` (`core/kernel.py:57-61`).

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `PolicyGate` | chokepoint deny-list; chặn một tool TRƯỚC khi chạy (E06) | `__init__(deny, on_block)`; `__call__(request, nxt)`; fields `deny`, `on_block`; trả envelope `metadata.policy_block=True` khi chặn | `core.schemas.ToolRequest` | `core/bootstrap.py:42` `kernel.use(PolicyGate(deny=...))` (khi `middleware.policy.enabled`) |
| `BudgetGuard` | chặn lặp lại tool y hệt; tái dùng `discipline.Budget` (E02/E06) | `__init__(budget, on_block)`; `__call__` gọi `Budget.tool_key`, `budget.record_tool_call`, `budget.same_tool_exceeded`; `metadata.budget_block=True` | `core.schemas.ToolRequest`, `discipline.Budget` | **Không wire ở runtime** (cố ý — counter per-run; xem ghi chú `core/bootstrap.py:31-32`). Chỉ khởi tạo trong tests |
| `TimingLog` | đo wall-time quanh tool; đăng ký NGOÀI CÙNG (E04) | `__init__(sink)`; `__call__` đo `time.perf_counter` quanh `nxt`, đẩy `{tool, ok, ms}` vào `sink`; nuốt exception của sink | `core.schemas.ToolRequest`, stdlib `time` | `core/bootstrap.py:37` `kernel.use(TimingLog())` (khi `middleware.timing.enabled`) — đăng ký đầu tiên ⇒ ngoài cùng |
| `CondenseResult` | thu gọn `data` của kết quả trước khi nạp lại model; tái dùng `discipline.condense`; bỏ qua `llm.*` (E02) | `__init__(max_chars=2000, max_list=10, on_condense)`; `__call__` gọi `condense(env["data"], ...)` SAU `nxt`, set lại `env["data"]`, gọi `on_condense` khi thực sự co lại | `core.schemas.ToolRequest`, `discipline.condense` | `core/bootstrap.py:52` `kernel.use(CondenseResult(...))` (khi `middleware.condense.enabled`) — đăng ký cuối ⇒ trong cùng |
| `Retry` | re-invoke handler khi kết quả non-ok (E06/E10 S10.13) | `__init__(attempts=2)`; `__call__` lặp `nxt(request)` tới `attempts` lần khi `not env["ok"]` và `_retryable(env)`; field `attempts` | `core.schemas.ToolRequest` | `core/bootstrap.py:47` `kernel.use(Retry(attempts=...))` (khi `middleware.retry.enabled`) |

> Glue (hàm, KHÔNG phải class): `middleware/retry.py:_retryable(env)` — quyết định một envelope có được retry không: chặn `metadata.policy_block` và chặn effect không idempotent (`metadata.kind=="effect"` và `idempotent is False`) để tránh double-apply; cho phép read/model/idempotent. (Ráp chuỗi `_wrap`/đảo thứ tự nằm ở `core/kernel.py`, không thuộc module này.)

**Call-sites:**

### `PolicyGate`
- **Khởi tạo bởi:** `core/bootstrap.py:42` trong `_install_middleware`, gard bởi `policy.get("enabled")`; `deny` lấy từ config `middleware.policy.deny`.
- **Xuất hiện ở:** export tại `middleware/__init__.py:3,7`; def `middleware/policy.py:9`. Tham chiếu ý niệm (comment, không import) ở `control/permission.py:4`.
- **Biến/method dùng ở:** runtime gọi `__call__` qua `_wrap` (`core/kernel.py:24,137-140`); đọc `request.name` so với `self.deny`, gọi `self.on_block`. Test wiring/semantics: `tests/test_middleware.py:18,28`, `tests_audit/test_middleware_exact_semantics.py:26,79`.

### `BudgetGuard`
- **Khởi tạo bởi:** **không ở runtime** — `core/bootstrap.py:31-32` ghi rõ BudgetGuard cố ý KHÔNG wire ở đây vì counter same-tool là per-run; instance theo vòng đời kernel sẽ rò qua các run, nên phải wire per-run. Hiện chỉ instantiate trong tests (`tests/test_middleware.py:76`, `tests_audit/test_middleware_exact_semantics.py:61`).
- **Xuất hiện ở:** export `middleware/__init__.py:1,7`; def `middleware/budget.py:10`.
- **Biến/method dùng ở:** trong `__call__` gọi `Budget.tool_key(request.name, request.args)` (`discipline/budget.py:39`), `self.budget.record_tool_call(key)` (`:31`), `self.budget.same_tool_exceeded(key)` (`:35`), rồi `self.on_block`. **(chỉ tests đối với call-site khởi tạo.)**

### `TimingLog`
- **Khởi tạo bởi:** `core/bootstrap.py:37` `kernel.use(TimingLog())` (không truyền `sink` ⇒ `sink=None`), gard bởi `middleware.timing.enabled`. Là middleware đăng ký đầu tiên ⇒ ngoài cùng.
- **Xuất hiện ở:** export `middleware/__init__.py:5,7`; def `middleware/timing.py:10`.
- **Biến/method dùng ở:** runtime gọi `__call__` qua chuỗi `_wrap`; đo quanh `nxt(request)`, đọc `env.get("ok")`, đẩy dict vào `self.sink` (nuốt mọi Exception để sink không biến tool thành lỗi). Sink thật: tests (`tests_audit/test_middleware_exact_semantics.py:37,53`); thứ tự ngoài cùng được khẳng định ở `:26`.

### `CondenseResult`
- **Khởi tạo bởi:** `core/bootstrap.py:52` `kernel.use(CondenseResult(max_chars=..., max_list=...))`, gard bởi `middleware.condense.enabled`; đăng ký cuối ⇒ trong cùng.
- **Xuất hiện ở:** export `middleware/__init__.py:2,7`; def `middleware/condense.py:11`.
- **Biến/method dùng ở:** trong `__call__` (sau `nxt`): nếu `request.name.startswith("llm.")` trả nguyên (để JSON action của model tới parser nguyên vẹn); ngược lại gọi `condense(env["data"], max_chars=self.max_chars, max_list=self.max_list)` (`discipline/condense.py`), set lại `env["data"]`, gọi `self.on_condense` chỉ khi giá trị thực sự co lại. Tests: `tests/test_middleware.py:64`, `tests_audit/test_middleware_exact_semantics.py:91`.

### `Retry`
- **Khởi tạo bởi:** `core/bootstrap.py:47` `kernel.use(Retry(attempts=int(retry.get("attempts", 2))))`, gard bởi `middleware.retry.enabled`.
- **Xuất hiện ở:** export `middleware/__init__.py:4,7`; def `middleware/retry.py:23`; cùng hàm module-level `_retryable` (`:14`).
- **Biến/method dùng ở:** `__call__` lặp `nxt(request)` tới `self.attempts` lần khi `isinstance(env, dict) and not env.get("ok")` và `_retryable(env)`; `_retryable` đọc `env["metadata"]` các khoá `policy_block`, `kind`, `idempotent` (những giá trị này do kernel stamp ở `core/kernel.py:130-131` từ `descriptor.kind`/`descriptor.idempotent`). Tests: `tests/test_middleware.py:97`, `tests/test_capability_kind.py:27` (integration: kernel stamp kind, Retry tôn trọng), `tests_audit/test_middleware_exact_semantics.py:121,129`.

## rag/ — local RAG: health-gated ingest/search behind ports, offline fakes + Qdrant (Epic E08)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `Chunk` | value type 1 đoạn văn bản đã (chưa) embed; đơn vị upsert | fields `source`/`chunk_index`/`text`/`vector` (frozen dataclass) | — (stdlib `dataclass`) | `RagService.ingest` (service.py:70 tạo); `InMemoryVectorStore`/`QdrantVectorStore.upsert`/`delete_by_source` đọc field |
| `Hit` | value type 1 kết quả search có `score` | fields `source`/`chunk_index`/`text`/`score` (frozen) | — | store `.search` tạo (stores.py:54, stores_qdrant.py:141); `RagService.search` đọc để dựng envelope (service.py:106-109) |
| `EmbedderPort` | port: hợp đồng embedder (text→vector) tách logic khỏi infra | field `dim`; `embed(texts)->list[list[float]]` (Protocol `runtime_checkable`) | — | `RagService.__init__` nhận type (service.py:16); không instantiate |
| `VectorStorePort` | port: hợp đồng vector store (health/upsert/search/delete) | `health()`, `delete_by_source`, `upsert`, `search` (Protocol) | `Chunk`, `Hit` (signatures) | `RagService.__init__` nhận type (service.py:16); không instantiate |
| `RagConfig` | config bất biến của feature (collection/model/chunk/threshold/qdrant) | fields + `from_dict(data)` classmethod (ports.py:53) | — | `build_service` tạo qua `from_dict` (feature.py:29); đọc bởi `RagService` (`self._cfg`) và `QdrantVectorStore` |
| `RagService` | logic health-gated ingest/search trên 2 port; trả dict envelope `{"ok":...}` | `health()`, `ingest(raw_path)`, `search(query,top_k,score_threshold)`, `_require_healthy()` | `Chunk`, `EmbedderPort`, `VectorStorePort`, `RagConfig`; `rag.chunking` (`chunk_text`/`collect_files`); `safety.sandbox` (`resolve_in_workspace`/`SandboxError`) | `build_service` tạo (feature.py:34,41); 3 tool gọi qua `self._service` (feature.py:75,84,94) |
| `InMemoryVectorStore` | adapter offline (cosine xác định) cho acceptance suite; `health()` bật/tắt được để test S08.1 | `set_healthy`, `health`, `delete_by_source`, `upsert`, `search`; fields `collection`/`_chunks` | `Chunk`, `Hit`; `_cosine` (stores.py:15) | `build_service` backend `memory` tạo (feature.py:32) |
| `QdrantVectorStore` | adapter production trên qdrant-client; collection tạo lazy, point id xác định, `health()` không raise | `health`/`delete_by_source`/`upsert`/`search` + `_ensure_collection`/`_source_filter` | `Chunk`, `Hit`, `RagConfig`; `qdrant_client` (import lazy), `_point_id` (stores_qdrant.py:28) | `build_service` backend `qdrant` tạo (feature.py:39) |
| `FakeEmbedder` | embedder offline xác định (BoW-hash chuẩn hóa), không model/mạng | `embed(texts)`; field `dim=64`; `_embed_one` | `_tokenize`/`_bucket`/`_normalize` (embedders.py) | `build_service` backend `memory` tạo (feature.py:33) |
| `FastEmbedEmbedder` | embedder production bọc `fastembed` (import lazy, probe `dim`) | `embed(texts)`; field `dim`; ctor `(model)` | `fastembed.TextEmbedding` (import lazy) | `build_service` backend `qdrant` tạo (feature.py:36,40) |
| `_RagTool` | base 3 tool: giữ `service`+`publish`, phát event `rag.*` với lineage | `__init__(name,service,publish)`, `_emit(request,result,**extra)`; field `topic=""`, `name`, `_service`, `_publish` | `RagService`, `core.schemas.ToolRequest` (`request.context.event_fields`) | base của 3 tool dưới (feature.py:71,80,89); không tạo trực tiếp |
| `RagHealthTool` | tool `rag_health` → `service.health()` + emit `rag.health` | `execute(request)->dict`; `topic="rag.health"` | `_RagTool`, `RagService` | `install` tạo + register (feature.py:114) |
| `RagIngestTool` | tool `rag_ingest` → `service.ingest(args["path"])` + emit `rag.ingest` | `execute(request)`; `topic="rag.ingest"` | `_RagTool`, `RagService` | `install` tạo + register (feature.py:117) |
| `RagSearchTool` | tool `rag_search` → `service.search(query,top_k,score_threshold)` + emit `rag.search` | `execute(request)`; `topic="rag.search"` | `_RagTool`, `RagService` | `install` tạo + register (feature.py:120) |

> Glue (hàm, KHÔNG phải class): `rag.feature.build_service(config)` — đọc `RagConfig.from_dict` + `backend` (`memory`/`qdrant`), lắp store+embedder thành `RagService` (feature.py:27). `rag.feature.install(kernel, *, service=None)` — entrypoint feature: `build_service` từ `kernel.config['rag']`, `register_feature(FEATURE)` + `register_tool` 3 tool với `kernel.events.publish` (feature.py:109). `rag.ports._point_id`→KHÔNG ở ports; `rag.stores._cosine` — cosine similarity (stores.py:15). `rag.stores_qdrant._point_id` — `uuid5(source::chunk_index)` để re-upsert ghi đè (stores_qdrant.py:28). `rag.embedders._tokenize`/`_bucket`/`_normalize` — bag-of-words hash cho `FakeEmbedder`. `rag.chunking.collect_files`/`chunk_text` — liệt kê file + cắt đoạn cho `RagService.ingest`.

**Call-sites:**

### `Chunk`
- **Khởi tạo bởi:** `RagService.ingest` (service.py:70, nơi tạo runtime duy nhất). Trong test: tests_audit/test_rag_qdrant_adapter_contract.py, tests/test_rag_qdrant.py.
- **Xuất hiện ở:** import ở service.py:11, stores.py:12, stores_qdrant.py:22, rag/__init__.py:10 (export `__all__`); param type của `VectorStorePort.upsert`, `InMemoryVectorStore.upsert/delete_by_source`, `QdrantVectorStore.upsert/delete_by_source`.
- **Biến/method dùng ở:** đọc field `.source`/`.chunk_index`/`.text`/`.vector` trong `InMemoryVectorStore.search`/`delete_by_source` (stores.py:40,50-54) và `QdrantVectorStore.upsert`/`delete_by_source` (stores_qdrant.py:106-120).

### `Hit`
- **Khởi tạo bởi:** `InMemoryVectorStore.search` (stores.py:54), `QdrantVectorStore.search` (stores_qdrant.py:141).
- **Xuất hiện ở:** import service.py (gián tiếp qua ports), stores.py:12, stores_qdrant.py:22, rag/__init__.py:10; return-type `VectorStorePort.search`/store `.search`.
- **Biến/method dùng ở:** `RagService.search` đọc `.source`/`.chunk_index`/`.text`/`.score` để dựng envelope `hits` (service.py:106-109).

### `EmbedderPort`
- **Khởi tạo bởi:** không (Protocol `runtime_checkable`).
- **Xuất hiện ở:** def ports.py:24; import service.py:11; type của `RagService.__init__(embedder: EmbedderPort)` (service.py:16); export rag/__init__.py:10.
- **Biến/method dùng ở:** `RagService` gọi `self._embedder.embed(...)` (service.py:63,97); field `dim` đọc bởi adapter cụ thể, không qua port.

### `VectorStorePort`
- **Khởi tạo bởi:** không (Protocol `runtime_checkable`).
- **Xuất hiện ở:** def ports.py:31; import service.py:11; type của `RagService.__init__(store: VectorStorePort)` (service.py:16); export rag/__init__.py:10.
- **Biến/method dùng ở:** `RagService` gọi `self._store.health()` (service.py:23,32), `.delete_by_source` (service.py:71), `.upsert` (service.py:72), `.search` (service.py:98).

### `RagConfig`
- **Khởi tạo bởi:** `build_service` qua `RagConfig.from_dict(config)` (feature.py:29, nơi tạo runtime duy nhất). Test tạo trực tiếp với kwargs.
- **Xuất hiện ở:** def ports.py:39; import feature.py:16, service.py:11, stores_qdrant.py:22, rag/__init__.py:10; type của `QdrantVectorStore.__init__(config)` (stores_qdrant.py:35).
- **Biến/method dùng ở:** `RagService` đọc `self._cfg.chunk_size`/`chunk_overlap`/`top_k`/`score_threshold` (service.py:58-59,91,94); `build_service` đọc `cfg.collection`/`cfg.model` (feature.py:32,40); `QdrantVectorStore` đọc `config.collection`/`qdrant_url`/`qdrant_timeout` (stores_qdrant.py:37,47-48).

### `RagService`
- **Khởi tạo bởi:** `build_service` (feature.py:34 backend memory, feature.py:41 backend qdrant). `install` cũng nhận `service` injected tùy chọn (feature.py:110).
- **Xuất hiện ở:** def service.py:15; import feature.py:17, rag/__init__.py:11; type của `_RagTool.__init__(service: RagService)` (feature.py:56), `build_service`/`install` return/param (feature.py:27,109).
- **Biến/method dùng ở:** 3 tool gọi `self._service.health()` (feature.py:75), `.ingest(...)` (feature.py:84), `.search(...)` (feature.py:94). Nội bộ: `_require_healthy` gọi trước mỗi ingest/search (service.py:43,85).

### `InMemoryVectorStore`
- **Khởi tạo bởi:** `build_service` backend `memory` (feature.py:32).
- **Xuất hiện ở:** def stores.py:24; import feature.py:18. Trong test: tests/test_rag.py, tests_audit (kèm `_cosine`).
- **Biến/method dùng ở:** dùng qua `VectorStorePort` bởi `RagService` (health/upsert/search/delete). `set_healthy` chỉ được gọi trong tests (chuyển trạng thái health). Nội bộ `search` gọi `_cosine` (stores.py:52).

### `QdrantVectorStore`
- **Khởi tạo bởi:** `build_service` backend `qdrant` (feature.py:39, dưới `# pragma: no cover`). Test: tests/test_rag_qdrant.py:56,101, tests_audit/test_rag_qdrant_adapter_contract.py:100 (inject `client`).
- **Xuất hiện ở:** def stores_qdrant.py:32; import lazy trong `build_service` (feature.py:37).
- **Biến/method dùng ở:** dùng qua `VectorStorePort` bởi `RagService`. Nội bộ: `upsert`→`_ensure_collection` (stores_qdrant.py:115); `delete_by_source`/`_ensure_collection`→`_source_filter`; `_point_id` dựng id point (stores_qdrant.py:118). Ngoài `build_service`, chỉ tests gọi method trực tiếp.

### `FakeEmbedder`
- **Khởi tạo bởi:** `build_service` backend `memory` (feature.py:33). Test: tests/test_rag.py, tests/test_rag_qdrant.py, tests_audit (kèm `dim=` tùy chỉnh).
- **Xuất hiện ở:** def embedders.py:33; import feature.py:15.
- **Biến/method dùng ở:** dùng qua `EmbedderPort` bởi `RagService.embed`. Field `dim` không đọc trong runtime rag (chỉ trong test/qdrant probe). Nội bộ `_embed_one`→`_tokenize`/`_bucket`/`_normalize`.

### `FastEmbedEmbedder`
- **Khởi tạo bởi:** `build_service` backend `qdrant` (feature.py:40, import lazy feature.py:36, `# pragma: no cover`).
- **Xuất hiện ở:** def embedders.py:49; import lazy trong `build_service`. Không xuất hiện trong tests (cần fastembed).
- **Biến/method dùng ở:** dùng qua `EmbedderPort` bởi `RagService.embed`; `self.dim` probe trong ctor (embedders.py:57).

### `_RagTool`
- **Khởi tạo bởi:** không trực tiếp (base class); chỉ tạo gián tiếp qua 3 subclass trong `install` (feature.py:114,117,120).
- **Xuất hiện ở:** def feature.py:53; base của `RagHealthTool`/`RagIngestTool`/`RagSearchTool`.
- **Biến/method dùng ở:** 3 subclass gọi `self._service.*` và `self._emit(...)` trong `execute` (feature.py:76,85,99). `_emit` đọc `request.context.event_fields()` rồi gọi `self._publish(self.topic, payload)` (feature.py:62-68).

### `RagHealthTool`
- **Khởi tạo bởi:** `install` (feature.py:114), register tool `rag_health`.
- **Xuất hiện ở:** def feature.py:71.
- **Biến/method dùng ở:** `execute` được kernel gọi qua chokepoint (`execute_tool`); gọi `self._service.health()` + `_emit` với `collection`/`count` (feature.py:75-76).

### `RagIngestTool`
- **Khởi tạo bởi:** `install` (feature.py:117), register tool `rag_ingest`.
- **Xuất hiện ở:** def feature.py:80.
- **Biến/method dùng ở:** `execute` gọi `self._service.ingest(request.args["path"])` + `_emit` với `files`/`chunks` (feature.py:84-85).

### `RagSearchTool`
- **Khởi tạo bởi:** `install` (feature.py:120), register tool `rag_search`.
- **Xuất hiện ở:** def feature.py:89.
- **Biến/method dùng ở:** `execute` gọi `self._service.search(query, top_k, score_threshold)` từ `request.args` + `_emit` với `count`/`top_k`/`score_threshold` (feature.py:92-105).

## roles/ — vai trò (role) buộc với skills/lenses, ép allowlist năng lực (Epic E09)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `Agent` (roles/agent.py:20) | role đã resolve thành runtime: tính allowlist một lần, dựng prompt scoped, giữ 2 guard cho vòng lặp ép allowlist + separation-of-duties | `__init__(spec, *, skills, lenses, core_tools)`; `allowed_tools` (field, set khi init qua `spec.allowed_tools`); `is_tool_allowed`; `guard_tool_call`; `guard_finish`; `build_prompt` | `RoleSpec` (đọc field + gọi `spec.allowed_tools`, `spec.test_ownership`, `spec.lenses`, `spec.allowed_skills`, `spec.system_prompt`); `SkillRegistry` (gọi `.render(...,mode="contract")`); `LensRegistry` (gọi `.render`) | `AgentRegistry.build_agent` (roles/registry.py:60) — đường runtime duy nhất tạo Agent. (Trực tiếp `Agent(...)` chỉ ở tests_audit) |
| `TestOwnership` (roles/spec.py:22) | dataclass frozen đánh dấu separation-of-duties: role không sở hữu validation phải `must_handoff_to` thay vì tự chứng nhận | field `owns_validation: bool=True`, `must_handoff_to: str\|None=None` | — (chỉ stdlib dataclass) | tạo trong `parse_role` (roles/spec.py:109) và là default_factory của `RoleSpec.test_ownership`; đọc bởi `Agent.__init__` (chặn role thiếu handoff) và `Agent.guard_finish` |
| `RoleView` (roles/spec.py:31) | projection mỏng (canonical→view) mà orchestrator E10 đọc: chỉ `agent_id`/`role`/`system_prompt`/`default_scope` | 4 field frozen | — (chỉ stdlib) | nơi tạo duy nhất: `AgentRegistry.role_view` (roles/registry.py:69), trả qua `list_roles`; runtime consumer: `supervisor/graph.py:54` (`SupervisorContext.role_catalog` đọc `v.agent_id`, `v.role`) |
| `RoleSpec` (roles/spec.py:41) | định nghĩa role canonical (1 nguồn sự thật, dùng chung E05+E10); nơi duy nhất hợp nhất explicit_tools + skill tools + core, trừ forbidden | field `name/role/department/system_prompt/explicit_tools/allowed_skills/may_route_to/test_ownership/lenses`; method `allowed_tools(skills, core_tools)` (forbidden wins) | `SkillRegistry` (trong `allowed_tools` gọi `skills.get(name).allowed_tools/.forbidden_tools`); `TestOwnership` | tạo ở `parse_role`/`load_role_file` (roles/spec.py); lưu trong `AgentRegistry._roles`; đọc bởi `Agent` và `AgentRegistry.role_view`/`build_agent` |
| `AgentRegistry` (roles/registry.py:18) | một role store duy nhất chia sẻ cho single-path (E05) và multi-path (E10); giữ RoleSpec + skill/lens registry + core tools | `register`/`load_file`/`load_dir`; `get`/`names`/`__contains__`; `build_agent(name)→Agent`; `role_view(name)→RoleView`; `list_roles()→tuple[RoleView]` | `Agent`, `RoleSpec`, `RoleView`, `load_role_file`, `LensRegistry`, `SkillRegistry` (import + giữ trong field) | runtime: truyền vào `SupervisorContext.agent_registry` (duck-typed `Any`, supervisor/graph.py:45) và gọi `list_roles()`. Khởi tạo cụ thể `AgentRegistry(...)` hiện chỉ thấy ở tests/tests_audit |

> Glue (hàm, KHÔNG phải class): `parse_role(data, *, source)` / `load_role_file(path)` (roles/spec.py:90,117) — nguồn sự thật biến YAML→RoleSpec, raise ValueError có tên file+field; `_as_tuple`/`_sequence_tuple`/`_mapping` (roles/spec.py) — chuẩn hoá/validate field YAML.

## roles/lenses.py — lăng kính review chèn vào prompt agent (Epic E09)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `LensSpec` (roles/lenses.py:15) | dataclass frozen: một góc nhìn review có tên (vd "correctness"/"security") gồm purpose + allowed/forbidden tools + output_schema; biết tự render thành block markdown | field `name/purpose/allowed_tools/forbidden_tools/output_schema`; method `render()` | — (chỉ stdlib) | tạo ở `parse_lens` (roles/lenses.py:43); lưu trong `LensRegistry._lenses`; `render()` được gọi qua `LensRegistry.render` |
| `LensRegistry` (roles/lenses.py:64) | kho lens; chỉ những lens role khai báo mới được render vào prompt (S09.5) | `register`/`load_file`/`load_dir`; `get`; `render(name)`; `__contains__` | `LensSpec`, `parse_lens` | runtime: `Agent.build_prompt` gọi `self._lenses.render(lens_name)` (roles/agent.py:76); giữ trong `AgentRegistry._lenses`. Khởi tạo `LensRegistry()` runtime chưa thấy ngoài tests |

> Glue: `parse_lens(data, *, source)` (roles/lenses.py:43) — nguồn sự thật YAML→LensSpec, raise ValueError thiếu `name`/`purpose`; `_as_tuple` — chuẩn hoá list tool.

## skills/ — kỹ năng = operating contract role-agnostic + progressive disclosure (Epic E07)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `SkillSpec` (skills/spec.py:26) | dataclass frozen, immutable, role-agnostic: contract của một skill — chỉ khai báo tool theo tên canonical (allowed/forbidden) + Steps/Report; KHÔNG tham chiếu role (cycle-break E07↔E09) | field `name/description/triggers/allowed_tools/forbidden_tools/steps_md/report_md` | — (chỉ stdlib) | nơi tạo: `parse_skill` (skills/spec.py:98); lưu trong `SkillRegistry._skills`; đọc bởi `SkillRegistry.render`/`union_tools`/`lint` và bởi `RoleSpec.allowed_tools` (qua `skills.get(name)`) |
| `SkillRegistry` (skills/registry.py:17) | nạp SKILL.md và render progressive disclosure: `mode="contract"` chỉ desc+Allowed+Forbidden; `mode="full"` thêm Steps+Report khi skill được chọn cho step active; cung cấp `union_tools` cho derivation E09 | `register`/`load_text`/`load_file`/`load_dir`; `get`/`names`/`__contains__`/`__len__`; `render(name,*,mode)`; `union_tools(names)→frozenset`; `lint(has_tool)` | `SkillSpec`, `parse_skill` | runtime: `Agent.build_prompt` gọi `self._skills.render(skill,mode="contract")` (roles/agent.py:83); `RoleSpec.allowed_tools` gọi `skills.get(...)` (roles/spec.py:60); giữ trong `AgentRegistry._skills`. Khởi tạo `SkillRegistry()` runtime chưa thấy ngoài tests |

> Glue: `parse_skill(text)` (skills/spec.py:98) — nguồn sự thật SKILL.md→SkillSpec (tách frontmatter YAML + section markdown); `_split_frontmatter`/`_split_sections`/`_find_section`/`_bullets`/`_triggers` (skills/spec.py) — bóc field; `_render_bullets` (skills/registry.py:102) — render danh sách tool.

**Call-sites:**

### `Agent`
- **Khởi tạo bởi:** `AgentRegistry.build_agent` (roles/registry.py:60) là đường runtime duy nhất tạo Agent (truyền `skills`/`lenses`/`core_tools` từ registry). Khởi tạo trực tiếp `Agent(spec, skills=..., lenses=...)` chỉ ở tests_audit/test_roles_skills_config_integrity.py:188,208 (chỉ tests).
- **Xuất hiện ở:** import `from roles.agent import Agent` ở roles/registry.py:12, roles/__init__.py:12 (re-export `__all__`); return-type của `build_agent`.
- **Biến/method dùng ở:** chưa thấy runtime ngoài E09 gọi `guard_tool_call`/`guard_finish`/`build_prompt`/`allowed_tools` (vòng lặp E05/E10 wiring là việc module khác chưa nối — comment roles/agent.py:7 nói "Graph wiring là việc E10"); các guard này hiện chỉ được gọi ở tests/test_roles.py (chỉ tests). Nội bộ self.*: `__init__` đọc `spec.test_ownership.owns_validation/must_handoff_to`, set `self.allowed_tools=spec.allowed_tools(skills,core_tools)`; `build_prompt` lặp `self.spec.lenses`→`self._lenses.render`, `self.spec.allowed_skills`→`self._skills.render`.

### `TestOwnership`
- **Khởi tạo bởi:** `parse_role` (roles/spec.py:109) là nơi tạo runtime; cũng là `default_factory` của `RoleSpec.test_ownership` (roles/spec.py:50). Khởi tạo trực tiếp khác chỉ ở tests_audit (alias `Ownership`).
- **Xuất hiện ở:** import/re-export ở roles/__init__.py:15 (`__all__`), import từ roles.spec ở roles/agent.py qua `spec.test_ownership`; param mặc định của `RoleSpec`.
- **Biến/method dùng ở:** `Agent.__init__` đọc `.owns_validation`/`.must_handoff_to` (roles/agent.py:31) để chặn role thiếu handoff; `Agent.guard_finish` đọc `ownership.owns_validation`/`ownership.must_handoff_to` (roles/agent.py:59-67).

### `RoleView`
- **Khởi tạo bởi:** `AgentRegistry.role_view` (roles/registry.py:69) — nơi tạo duy nhất; `list_roles` chỉ map qua nó.
- **Xuất hiện ở:** định nghĩa roles/spec.py:31; import roles/registry.py:14 và roles/__init__.py:15 (`__all__`); return-type `role_view`/`list_roles`.
- **Biến/method dùng ở:** runtime — `supervisor/graph.py:54` (`SupervisorContext.role_catalog`) lặp `self.agent_registry.list_roles()` đọc `v.agent_id`, `v.role` để dựng role catalog cho Agent O. (Lưu ý: supervisor nhận registry qua field `agent_registry: Any` duck-typed, không import trực tiếp `AgentRegistry`.) Ngoài ra chỉ tests đọc `default_scope`/`system_prompt`.

### `RoleSpec`
- **Khởi tạo bởi:** `parse_role` (roles/spec.py:101), gọi qua `load_role_file` (roles/spec.py:117) → `AgentRegistry.load_file`/`load_dir` (roles/registry.py:38-43). Khởi tạo trực tiếp `RoleSpec(...)` khác chỉ ở tests_audit (chỉ tests).
- **Xuất hiện ở:** định nghĩa roles/spec.py:41; import roles/agent.py:13, roles/registry.py:14, roles/__init__.py:15 (`__all__`); param `Agent.__init__(spec)`; giá trị trong `AgentRegistry._roles`.
- **Biến/method dùng ở:** runtime — `Agent` đọc nhiều field + gọi `spec.allowed_tools(skills,core_tools)` (roles/agent.py:39); `AgentRegistry.role_view` gọi `spec.allowed_tools(...)` và đọc `spec.name/role/system_prompt` (roles/registry.py:71-75); `AgentRegistry.register` đọc `spec.name` (roles/registry.py:33). Nội bộ: `allowed_tools` lặp `self.allowed_skills`, gọi `skills.get(skill_name).allowed_tools/.forbidden_tools`.

### `AgentRegistry`
- **Khởi tạo bởi:** runtime chưa thấy nơi nào `AgentRegistry(...)` ngoài tests/tests_audit; được tiêu thụ runtime qua field `SupervisorContext.agent_registry` (supervisor/graph.py:45, type `Any | None`, comment "E09 AgentRegistry (for the role catalog)") — supervisor không tự xây mà nhận injected.
- **Xuất hiện ở:** định nghĩa roles/registry.py:18; re-export roles/__init__.py:14,23 (`__all__`); tham chiếu bằng comment/duck-type ở supervisor/graph.py:45.
- **Biến/method dùng ở:** runtime — `SupervisorContext.role_catalog` gọi `agent_registry.list_roles()` (supervisor/graph.py:54). `build_agent`/`role_view`/`get`/`names`/`register` còn lại được gọi ở tests (chỉ tests). Nội bộ self.*: giữ `_skills`/`_lenses`/`_core_tools`/`_roles`; `build_agent` truyền chúng vào `Agent`; `role_view` truyền `_skills`,`_core_tools` vào `spec.allowed_tools`.

### `LensSpec`
- **Khởi tạo bởi:** `parse_lens` (roles/lenses.py:55) — nơi tạo runtime (qua `LensRegistry.load_file`/`load_dir`). Khởi tạo trực tiếp khác chỉ ở tests_audit.
- **Xuất hiện ở:** định nghĩa roles/lenses.py:15; import/re-export roles/__init__.py:13,24 (`__all__`); return-type `LensRegistry.register`/`load_file`/`load_dir`/`get`.
- **Biến/method dùng ở:** `LensRegistry.render` gọi `self.get(name).render()` (roles/lenses.py:90). `render()` nội bộ đọc `self.name/purpose/allowed_tools/forbidden_tools/output_schema`.

### `LensRegistry`
- **Khởi tạo bởi:** runtime chưa thấy `LensRegistry()` ngoài tests; được truyền vào `AgentRegistry.__init__(lenses=...)` và giữ ở `_lenses`.
- **Xuất hiện ở:** định nghĩa roles/lenses.py:64; import roles/registry.py:13, roles/__init__.py:13,25 (`__all__`); param kw-only `lenses` của `AgentRegistry.__init__` và `Agent.__init__`.
- **Biến/method dùng ở:** runtime — `Agent.build_prompt` gọi `self._lenses.render(lens_name)` (roles/agent.py:76). Nội bộ: `render`→`get`→`LensSpec.render`.

### `SkillSpec`
- **Khởi tạo bởi:** `parse_skill` (skills/spec.py:109) — nơi tạo duy nhất runtime (qua `SkillRegistry.load_text`/`load_file`/`load_dir`). Khởi tạo trực tiếp `SkillSpec(...)` khác chỉ ở tests_audit.
- **Xuất hiện ở:** định nghĩa skills/spec.py:26; import skills/registry.py:14, skills/__init__.py:13 (`__all__`); return-type `SkillRegistry.register`/`get`/`load_*`.
- **Biến/method dùng ở:** runtime — `RoleSpec.allowed_tools` đọc `skills.get(name).allowed_tools`/`.forbidden_tools` (roles/spec.py:61-62); `SkillRegistry.render` đọc `spec.name/description/allowed_tools/forbidden_tools/steps_md/report_md` (skills/registry.py:61-75); `union_tools` đọc `.allowed_tools` (skills/registry.py:88); `lint` đọc `.allowed_tools/.forbidden_tools` (skills/registry.py:95).

### `SkillRegistry`
- **Khởi tạo bởi:** runtime chưa thấy `SkillRegistry()` ngoài tests; truyền vào `AgentRegistry.__init__(skills=...)` và giữ ở `_skills`; cũng là param kw-only `skills` của `Agent.__init__` và `RoleSpec.allowed_tools`.
- **Xuất hiện ở:** định nghĩa skills/registry.py:17; import skills/__init__.py:12 (`__all__`); import (TYPE_CHECKING) roles/agent.py:17, roles/spec.py:17; import roles/registry.py:15.
- **Biến/method dùng ở:** runtime — `Agent.build_prompt` gọi `self._skills.render(skill_name, mode="contract")` (roles/agent.py:83); `RoleSpec.allowed_tools` gọi `skills.get(skill_name)` (roles/spec.py:60); `AgentRegistry` chuyển tiếp `_skills` vào `Agent`/`spec.allowed_tools`. `union_tools`/`lint`/`mode="full"` còn lại chỉ thấy ở tests (chỉ tests).

## supervisor/ (A) — Blackboard state + hợp đồng quyết định cho 1 lần chạy multi-agent (Epic E10 + E21 S21.33)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `TaskLoopStatus` | enum 8 trạng thái vòng đời 1 run (`created`…`finished`/`blocked`/`failed`); nền cho `TERMINAL` & `is_terminal` | members `CREATED`/`TEAM_SELECTED`/`IN_DISCUSSION`/`WAITING_TOOL`/`REVIEWING_AC`/`FINISHED`/`BLOCKED`/`FAILED`; `.value` | stdlib `str, Enum` (—) | `loop.py:_drive/_terminate` (đặt status), `graph.py` các node (`o6_decide` đặt `.value`), module-level `TERMINAL` |
| `AcceptanceCheck` | 1 tiêu chí nghiệm thu trên Blackboard; mang evidence-type gate (S21.33) qua `evidence_ids` + `is_satisfied` | `is_satisfied` (passed ∧ có evidence), `as_dict`/`from_dict` | stdlib `dataclass` (—) | `TaskLoopState.acceptance_checks`, `loop.py:_criteria` (tạo), `graph.py:judge_acceptance` (set status/evidence) |
| `AgentTurn` | bản ghi 1 lượt worker đã chạy (round, agent, packet, artifacts) — append-only, nguồn cho resume | `as_dict`/`from_dict`; fields `round_no/agent_id/packet_id/artifact_ids` | stdlib `dataclass` (—) | `TaskLoopState.turns`, `graph.py:run_round` (tạo lúc append) |
| `TaskLoopState` | **Blackboard serializable** = nguồn sự thật của 1 run multi-agent để checkpoint/resume; chỉ primitive | `add_artifact`, `acceptance_by_id`, `all_accepted`, `is_terminal`, `acceptance_snapshot` | `AcceptanceCheck`, `AgentTurn`, `TaskLoopStatus`, `TERMINAL` | `loop.py:run_task_loop` (tạo), mọi node `graph.py`, `checkpoint.py` (save/load), `evidence.py:record_ac_report` |
| `AgentSelection` | 1 dòng "chọn agent + lý do" trong kế hoạch team (frozen) | field `agent_id/reason` | stdlib (—) | thành phần của `SessionPlan.selected`; `contracts.py:parse_session_plan` (tạo) |
| `SessionPlan` | kết quả Agent O chọn team (S10.1) — bộ `AgentSelection` | `agent_ids()`, `as_dict()` | `AgentSelection` | `graph.py:compose_team` (return-type, từ `parse_session_plan`) |
| `AgentAssignment` | giao việc O→worker 1 round; **chủ sở hữu scope** qua `allowed_capabilities` (S10.14) | fields `agent_id/objective/scope_of_work/allowed_capabilities` | stdlib (—) | `OrchestratorDecision.next_agent_calls`; `parse_decision` (tạo); `broker.py`/`llm.py` (tham số `write_packet`); `graph.py:StoreSliceProvider`/`default_store_slice` |
| `OrchestratorDecision` | quyết định O mỗi round (`continue`/`need_tool`/`finished`/`blocked`/`failed`) + calls/tools/acceptance | fields `decision/next_agent_calls/tool_requests/acceptance_status/progress_made/final_output` | `AgentAssignment` | `graph.py:o_decide` (return, từ `parse_decision`); `loop.py:_drive`/`_decision_signature` (đọc `.decision`); `run_round`/`run_tool`/`judge_acceptance` (tiêu thụ) |
| `ContextPacket` | gói Context Broker cho 1 lượt worker; **KHÔNG có scope** (O/policy mới owns) | `to_spec()` → `DelegationSpec`; fields `target_agent_id/objective/briefing/source_ids/expected_output_schema` | `core.schemas.DelegationSpec` | `broker.py`/`llm.py:write_packet` (tạo, return-type); `graph.py:run_round` (gọi `to_spec`) |
| `SqliteTaskLoopStore` | checkpoint SQLite (1 db/run) lưu `TaskLoopState` mới nhất — truth để resume (S10.10) | `save(state)`, `load()`; guard `run_id` 1-segment | `sqlite3`/`json`, `observability.event_log.runs_dir`, `encode/decode_taskloop_state`, `TaskLoopState` | `loop.py` qua `ctx.checkpoint_store`/`ctx.save`; `resume_task_loop` (gọi `.load()`); export ở `__init__.py` |

> Glue (hàm, KHÔNG phải class):
> - `state.py:encode_taskloop_state` / `decode_taskloop_state` — serialize/deserialize Blackboard ↔ dict (dùng bởi `checkpoint.py:save/load` và `loop.py:_result`).
> - `state.py:TERMINAL` (set) — tập trạng thái kết thúc; nền cho `is_terminal`.
> - `contracts.py:parse_session_plan` / `parse_decision` — cổng JSON (reuse `discipline.parse_json_object`/`JsonGateError`) sinh `SessionPlan`/`OrchestratorDecision` từ output thô của O.
> - `evidence.py:evidence_type_of` — phân loại 1 artifact theo `kind` thành evidence-type hay `None` (gate S21.33); `EVIDENCE_TYPES`/`NON_EVIDENCE_KINDS` là từ vựng.
> - `evidence.py:record_ac_report` — snapshot toàn bộ AC + evidence thành 1 artifact `ac_report` (id keyed theo `session_id`, idempotent khi resume — AC6; bản thân nằm trong `NON_EVIDENCE_KINDS` nên không tự citable — AC5).
> - `checkpoint.py:taskloop_db_path(run_id)` — đường dẫn db dưới `runs_dir()/run_id`.

**Call-sites:**

### `TaskLoopStatus`
- **Khởi tạo bởi:** enum, không instantiate; dùng members + `.value`.
- **Xuất hiện ở:** `state.py` (def + `TERMINAL`), import ở `graph.py:28`, `loop.py:26`; export `__init__.py:28`.
- **Biến/method dùng ở (runtime):** `loop.py:_drive` (`BLOCKED`/`FAILED`/`FINISHED`) và `_terminate` (`status.value`); `graph.py` set `.TEAM_SELECTED/IN_DISCUSSION/WAITING_TOOL/REVIEWING_AC .value`; `state.py:is_terminal` so `TaskLoopStatus(self.status) in TERMINAL`. (Tests: `test_supervisor_resume.py`, `test_supervisor_adversarial_matrix.py`.)

### `AcceptanceCheck`
- **Khởi tạo bởi (runtime):** `loop.py:_criteria` (L32-38, từ instance/dict/tuple); `decode_taskloop_state` (`from_dict`, L137).
- **Xuất hiện ở:** field `TaskLoopState.acceptance_checks`; import `graph.py:28`, `loop.py:26`; export `__init__.py:55`.
- **Biến/method dùng ở (runtime):** `graph.py:judge_acceptance:237` lấy qua `state.acceptance_by_id`, set `check.status`/`check.evidence_ids`; `state.py:all_accepted` đọc `is_satisfied`; `encode_taskloop_state` gọi `as_dict`. (Tests: `test_evidence.py`, `tests_audit/*`.)

### `AgentTurn`
- **Khởi tạo bởi (runtime):** `graph.py:run_round:200` (`AgentTurn(round_no=…, agent_id=…, packet_id=…, artifact_ids=…)`); `decode_taskloop_state` (`from_dict`, L140).
- **Xuất hiện ở:** field `TaskLoopState.turns`; import `graph.py:28`; export `__init__.py:56`.
- **Biến/method dùng ở:** `encode_taskloop_state:123` gọi `as_dict`. Ngoài tạo ở `run_round`, chỉ đọc khi serialize. (Tests: `test_supervisor_resume.py:61`, `tests_audit/test_contract_roundtrips.py:208`.)

### `TaskLoopState`
- **Khởi tạo bởi (runtime):** `loop.py:run_task_loop:97` (nơi tạo chính, từ `supervisor_session.identity`); `decode_taskloop_state:132` (khi resume/load).
- **Xuất hiện ở:** type của hầu hết hàm `graph.py` (`compose_team`/`o_decide`/`run_round`/`run_tool`/`judge_acceptance`/`_state_view`/`_next_id`/`default_store_slice`/`SupervisorContext.save`/`checkpoint`), `loop.py` (`_drive`/`_terminate`/`_result`), `checkpoint.py:save/load`, `evidence.py:record_ac_report`; import + export `__init__.py:27/53`.
- **Biến/method dùng ở (runtime):** `loop.py:_drive` đọc `is_terminal`/`round_no`/`max_rounds`/`artifacts`/`acceptance_snapshot`/`all_accepted`/`final_output`, set `acceptance_checks`/`reason`/`status`; `graph.py` các node gọi `add_artifact`/`acceptance_by_id`, append `turns`; `checkpoint.SqliteTaskLoopStore.save` encode, `load` decode. (Tests: nhiều ở `tests/`, `tests_audit/`.)

### `AgentSelection`
- **Khởi tạo bởi (runtime):** `contracts.py:parse_session_plan:89` (nơi tạo duy nhất runtime).
- **Xuất hiện ở:** thành phần `SessionPlan.selected`; export `__init__.py:47`.
- **Biến/method dùng ở:** `SessionPlan.agent_ids`/`as_dict` đọc `s.agent_id`/`s.reason`. Không có call-site runtime khác ngoài bên trong `SessionPlan`.

### `SessionPlan`
- **Khởi tạo bởi (runtime):** `parse_session_plan:95` (nơi tạo duy nhất).
- **Xuất hiện ở:** return-type `graph.py:compose_team:87`; import `graph.py:22`; export `__init__.py:46`.
- **Biến/method dùng ở (runtime):** `graph.py:compose_team` dùng `plan` (từ `parse_session_plan`) để set `state.selected_agents` (xem L88+). self: `agent_ids`/`as_dict` đọc `selected`. (Tests: `tests_audit/test_supervisor_adversarial_matrix.py:76`.)

### `AgentAssignment`
- **Khởi tạo bởi (runtime):** `parse_decision:126` (trong vòng dựng `next_agent_calls`).
- **Xuất hiện ở:** field `OrchestratorDecision.next_agent_calls`; tham số `write_packet` ở `broker.py:20/35` + `llm.py:102`; type `StoreSliceProvider`/`default_store_slice` `graph.py:31/34`; import `broker.py:14`, `llm.py:23`, `graph.py:20`; export `__init__.py:48`.
- **Biến/method dùng ở (runtime):** `broker.py`/`llm.py:write_packet` đọc `assignment.objective` (và tạo `ContextPacket`); `graph.py:run_round` lặp `decision.next_agent_calls`. (Tests: `test_context_broker.py`, `test_supervisor_llm.py`, `tests_audit/*`.)

### `OrchestratorDecision`
- **Khởi tạo bởi (runtime):** `parse_decision:145` (nơi tạo duy nhất runtime).
- **Xuất hiện ở:** return-type `graph.py:o_decide:108`; tham số `run_round`/`run_tool`/`judge_acceptance` (`graph.py:136/214/230`); `loop.py:_decision_signature:42`; import `graph.py:21`, `loop.py:15`; export `__init__.py:49`.
- **Biến/method dùng ở (runtime):** `loop.py:_drive:171-187` đọc `decision.decision`, `.final_output`, `.reason`; `_decision_signature` băm decision; `graph.py:judge_acceptance:236` lặp `decision.acceptance_status`; `run_tool` đọc `tool_requests`; `run_round` đọc `next_agent_calls`. (Tests: `tests_audit/*`.)

### `ContextPacket`
- **Khởi tạo bởi (runtime):** `broker.py:49` (`StaticBroker.write_packet`) và `llm.py:131` (`LLMBroker.write_packet`).
- **Xuất hiện ở:** return-type `write_packet` (Protocol `broker.py:21` + impl); import `broker.py:14`, `llm.py:23`; export `__init__.py:50`.
- **Biến/method dùng ở (runtime):** `graph.py:run_round` gọi `packet.to_spec()` → `DelegationSpec` để delegate; `to_spec` đọc `objective`/`briefing`/`source_ids`/`expected_output_schema`. (Tests: `test_context_broker.py:17`, `tests_audit/test_supervisor_adversarial_matrix.py:173`.)

### `SqliteTaskLoopStore`
- **Khởi tạo bởi (runtime):** không tạo bên trong `supervisor/` — caller bên ngoài dựng rồi truyền vào `run_task_loop`/`resume_task_loop` qua tham số `checkpoint_store` (gắn vào `ctx.checkpoint_store`, gọi qua `ctx.save`). `control/checkpoint.py:3` chỉ tham chiếu trong docstring để phân biệt.
- **Xuất hiện ở:** def `checkpoint.py:22`; import + export `__init__.py:11/36`.
- **Biến/method dùng ở (runtime):** `loop.py:resume_task_loop:122` gọi `checkpoint_store.load()` và đọc `checkpoint_store.run_id`; `loop.py` lưu qua `ctx.save(state)` (mỗi round boundary L191, mỗi node, `_terminate`) → `store.save`; self gọi `_conn`. (Tests: `test_supervisor_resume.py:24/48/78`, `tests_audit/test_supervisor_adversarial_matrix.py:217/223/240`.)

Files: `/Users/uspro/Desktop/Namson/hex_agent/supervisor/state.py`, `/Users/uspro/Desktop/Namson/hex_agent/supervisor/contracts.py`, `/Users/uspro/Desktop/Namson/hex_agent/supervisor/checkpoint.py`, `/Users/uspro/Desktop/Namson/hex_agent/supervisor/evidence.py` (call-sites: `supervisor/loop.py`, `supervisor/graph.py`, `supervisor/broker.py`, `supervisor/llm.py`, `supervisor/__init__.py`).

## supervisor/ (B) — Agent O (orchestrator/judge) + Context Broker + LLM (Epic E10)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `ChatLLM` (llm.py:53) | Protocol 1-method cho lớp gọi model — tách Agent O/Broker khỏi cách chạm model | `complete(messages) -> str` | — (Protocol, stdlib `typing`) | param type của `LLMOrchestrator.__init__`, `LLMBroker.__init__` (llm.py:74,97) |
| `KernelChatLLM` (llm.py:57) | Hiện thực `ChatLLM` chạm model qua kernel chokepoint (`llm.chat`) nên mọi call bị quan sát/kỷ luật như tool | `complete()` gọi `session.execute_tool("llm.chat", {messages, model, json_mode:True})`; field `_session`,`_model` | `core.session.KernelSession` (`execute_tool`) | caller bọc vào `LLMOrchestrator(KernelChatLLM(...))` (chỉ tests/test_supervisor_llm.py:59,78) |
| `LLMOrchestrator` (llm.py:71) | Agent O thật chạy bằng LLM; phát JSON thô để json-gate parse (giống Scripted) | `compose_team(task, available_roles)`, `decide(state_view)` → str; field `_llm` | `ChatLLM` (`_llm.complete`), `COMPOSE_SYSTEM`/`DECIDE_SYSTEM`, `json` | truyền vào `run_task_loop(orchestrator=...)` (chỉ tests) |
| `LLMBroker` (llm.py:94) | Context Broker chạy bằng LLM, NHƯNG guardrail nằm trong CODE: provenance (`source_ids` ∩ slice ids), size cap (`char_budget`), không có scope field | `write_packet(assignment, store_slice) -> ContextPacket`; field `_llm`,`char_budget` | `ChatLLM`, `discipline.parse_json_object`/`JsonGateError`, `supervisor.contracts.AgentAssignment`/`ContextPacket`, `BROKER_SYSTEM` | truyền vào `run_task_loop(broker=...)` (chỉ tests/test_supervisor_llm.py:88,113,138) |
| `OrchestratorPort` (orchestrator.py:16) | Hợp đồng Agent O (compose+decide) để loop chấp nhận cả bản Scripted lẫn LLM | `compose_team(...)`, `decide(...)` → str | — (Protocol) | field type `SupervisorContext.orchestrator` (graph.py:43); import bởi graph.py:27 |
| `ScriptedOrchestrator` (orchestrator.py:21) | O xác định cho test offline: compose canned + hàng đợi decisions; cạn hàng đợi → emit `blocked` thay vì loop vô hạn | `compose_team`/`decide`; counter `compose_calls`,`decide_calls`; field `_compose`,`_decisions` | `json` (fallback `blocked`) | khởi tạo bởi tests/conftest.py:137, tests_audit/* (chỉ tests) |
| `BrokerPort` (broker.py:18) | Hợp đồng Broker (`write_packet`) để loop chấp nhận Deterministic/LLM | `write_packet(assignment, store_slice) -> ContextPacket` | `supervisor.contracts` (ContextPacket) | field type `SupervisorContext.broker` (graph.py:44); import bởi graph.py:18 |
| `DeterministicBroker` (broker.py:24) | Broker offline: briefing chỉ ráp từ slice đã cho + provenance + size cap; KHÔNG phát scope field (bất biến S10.14) | `write_packet(...)`; field `char_budget` | `supervisor.contracts.AgentAssignment`/`ContextPacket` | khởi tạo bởi tests/conftest.py:138, tests/test_context_broker.py:83, tests_audit/* (chỉ tests) |
| `SupervisorContext` (graph.py:40, dataclass) | Gom mọi dependency runtime cho các node graph; cũng định tuyến event (raw publish hoặc qua EventEmitter B1) và checkpoint | field `supervisor_session`,`delegation_service`,`orchestrator`,`broker`,`agent_registry`,`store_slice_provider`,`checkpoint`,`emitter`,`trace`; method `role_catalog()`,`emit(topic,payload)`,`save(state)` | `KernelSession`, `OrchestratorPort`, `BrokerPort`, `control.Actor/EventEmitter/TraceContext`, `StoreSliceProvider` | **nơi tạo runtime duy nhất:** `loop.py:_make_ctx` (loop.py:59); đọc bởi mọi node graph.py (`ctx.orchestrator`,`ctx.broker`,`ctx.emit`,`ctx.save`) |

> Glue (hàm, KHÔNG phải class):
> - graph.py `compose_team` (gọi `ctx.orchestrator.compose_team`, validate trùng/unknown agent vs role catalog, set `selected_agents`), `o_decide` (gọi `ctx.orchestrator.decide`, parse+repair JSON theo `Budget`, None khi cạn parse-budget), `run_round` (authority-check assignment ∈ selected; mỗi assignment → `ctx.store_slice_provider` → `ctx.broker.write_packet` → `delegation_service.delegate`; chặn Broker đổi target; skip turn đã chạy khi resume), `run_tool` (chạy `tool_requests` qua `supervisor_session.execute_tool` — O không tự gọi tool), `judge_acceptance` (chỉ honour `passed` khi mọi evidence id resolve + ≥1 là evidence type thật, S21.33), `default_store_slice` (mặc định ground Broker trên toàn artifacts), `_state_view`, `_next_id`.
> - loop.py `run_task_loop`/`resume_task_loop` (facade công khai: dựng `SupervisorContext` + `TaskLoopState`, gọi `compose_team` rồi `_drive`; resume kiểm tra khớp session/task identity của checkpoint), `_drive` (vòng compose→decide→round/tool→judge→guard tới terminal; guard cơ học: max_rounds, no-progress, lặp decision), `_make_ctx`, `_terminate`, `_result`.

**Call-sites:**

### `ChatLLM`
- **Khởi tạo bởi:** không (Protocol).
- **Xuất hiện ở:** def llm.py:53; param type của `LLMOrchestrator.__init__`/`LLMBroker.__init__` (llm.py:74,97); export supervisor/__init__.py:21,42.
- **Biến/method dùng ở:** `LLMOrchestrator.compose_team`/`decide` và `LLMBroker.write_packet` gọi `self._llm.complete(...)` (llm.py:78,86,105).

### `KernelChatLLM`
- **Khởi tạo bởi:** caller, bọc trong `LLMOrchestrator(KernelChatLLM(env.supervisor_session))` — chỉ tests (tests/test_supervisor_llm.py:59,78). Không có runtime call-site khởi tạo trong repo.
- **Xuất hiện ở:** def llm.py:57; export supervisor/__init__.py:21,43; import tests/test_supervisor_llm.py:11.
- **Biến/method dùng ở:** `complete()` đọc `self._session.execute_tool`, `self._model` (llm.py:65); trả `data.content`.

### `LLMOrchestrator`
- **Khởi tạo bởi:** caller truyền vào `run_task_loop(orchestrator=...)` — chỉ tests (tests/test_supervisor_llm.py:59,78).
- **Xuất hiện ở:** def llm.py:71; export supervisor/__init__.py:21,44.
- **Biến/method dùng ở:** `compose_team`/`decide` được gọi gián tiếp qua `ctx.orchestrator.*` trong graph.py `compose_team`(:88)/`o_decide`(:112) khi instance này là `ctx.orchestrator`; nội bộ đọc `self._llm` (llm.py:78,86).

### `LLMBroker`
- **Khởi tạo bởi:** caller `LLMBroker(llm, char_budget=...)` truyền vào `run_task_loop(broker=...)` — chỉ tests (tests/test_supervisor_llm.py:88,113,138).
- **Xuất hiện ở:** def llm.py:94; export supervisor/__init__.py:21,45.
- **Biến/method dùng ở:** `write_packet` gọi gián tiếp qua `ctx.broker.write_packet` trong graph.py `run_round`(:155); nội bộ đọc `self._llm`,`self.char_budget`; áp guardrail `source_ids ∩ slice_ids`, cắt `[:self.char_budget]` (llm.py:128,134).

### `OrchestratorPort`
- **Khởi tạo bởi:** không (Protocol).
- **Xuất hiện ở:** def orchestrator.py:16; import graph.py:27; field type `SupervisorContext.orchestrator` (graph.py:43); export supervisor/__init__.py:23,38.
- **Biến/method dùng ở:** `ctx.orchestrator.compose_team(...)` (graph.py:88), `ctx.orchestrator.decide(...)` (graph.py:112) — runtime gọi qua field này.

### `ScriptedOrchestrator`
- **Khởi tạo bởi:** tests/conftest.py:137, tests_audit/test_supervisor_adversarial_matrix.py:47,131,250, tests_audit/test_acceptance_evidence_adversarial.py:59,105 (chỉ tests).
- **Xuất hiện ở:** def orchestrator.py:21; export supervisor/__init__.py:23,39; field type trong harness test conftest.py:67.
- **Biến/method dùng ở:** `compose_team`/`decide` gọi qua `ctx.orchestrator.*` ở graph.py khi instance là `ctx.orchestrator`; nội bộ tăng `self.compose_calls`/`self.decide_calls`, pop `self._decisions` (orchestrator.py:31,36).

### `BrokerPort`
- **Khởi tạo bởi:** không (Protocol).
- **Xuất hiện ở:** def broker.py:18; import graph.py:18; field type `SupervisorContext.broker` (graph.py:44); export supervisor/__init__.py:10,40.
- **Biến/method dùng ở:** `ctx.broker.write_packet(assignment=..., store_slice=...)` (graph.py:155) — runtime gọi qua field này.

### `DeterministicBroker`
- **Khởi tạo bởi:** tests/conftest.py:138, tests/test_context_broker.py:83, tests/test_supervisor_llm.py:60,79, tests_audit/test_supervisor_adversarial_matrix.py:59,251, tests_audit/test_acceptance_evidence_adversarial.py:63,106 (chỉ tests).
- **Xuất hiện ở:** def broker.py:24; export supervisor/__init__.py:10,41; field type conftest.py:68.
- **Biến/method dùng ở:** `write_packet` gọi qua `ctx.broker.write_packet` ở graph.py `run_round`(:155); nội bộ đọc `self.char_budget`, ráp `lines`/`source_ids` từ `store_slice` (broker.py:37-54).

### `SupervisorContext`
- **Khởi tạo bởi:** **runtime duy nhất** `loop.py:_make_ctx` (loop.py:59), được `run_task_loop`(:87) và `resume_task_loop`(:133) gọi. Ngoài ra tests_audit/test_supervisor_adversarial_matrix.py:55, tests/test_control_emitter.py:119 (tests).
- **Xuất hiện ở:** def graph.py:40; import loop.py:18; param type của mọi node graph.py (`compose_team`,`o_decide`,`run_round`,`run_tool`,`judge_acceptance`) và loop.py `_drive`/`_terminate`.
- **Biến/method dùng ở (runtime):** node graph.py đọc `ctx.orchestrator`(:88,112), `ctx.broker`(:155), `ctx.role_catalog()`(:88,94), `ctx.store_slice_provider`(:154), `ctx.delegation_service.delegate`(:176), `ctx.supervisor_session.execute_tool`(:218), `ctx.emit(...)` (nhiều node), `ctx.save(state)`(:209); loop.py gọi `ctx.save`/`ctx.emit` trong `_drive`/`_terminate`. Nội bộ `emit()` dùng `self.emitter`/`self.trace`/`self.supervisor_session.identity` (graph.py:60-75); `save()` dùng `self.checkpoint` (graph.py:78); `role_catalog()` dùng `self.agent_registry.list_roles()` (graph.py:54).

## orchestrator/ + graph/ + features/ — facade run/resume + LangGraph state v2 (Epic E05 / E03-04)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `Checkpoint` (`orchestrator/checkpoint.py:60`) | Read-model JSON ổn định cho UI — projection của run-state, KHÔNG dùng để resume graph (SQLite mới là authoritative); `backend` phân biệt `"langgraph"` vs `"legacy-json"` | `to_json`/`from_json`; `from_graph_state(state)` dựng từ `AgentState`; field `run_id` `task` `messages` `budget` `state` `step` `status` `backend` `schema_version=2` | `core.schemas.TaskEnvelope`, `graph.state.AgentState`/`decode_session_state` | `save_graph_projection` (loop ghi mỗi step), `_legacy_state` (resume đọc checkpoint cũ) trong `orchestrator/loop.py` |
| `AgentState` (`graph/state.py:12`) | State serializable checkpointed cho 1 run — `TypedDict(total=False)`, KHÁC AgentState dataclass snapshot cũ: không ôm kernel/LLM/SQLite (nodes nhận qua closure), thêm `schema_version` + `session_identity`/`session_state` + delegation fields (`active_delegation_id`, `last_delegation_result`) + codec; giữ `kernel_state` chỉ để migrate schema v1 | TypedDict keys; codec `encode_session_state`/`decode_session_state`; `new_agent_state(...)` (nơi tạo state mới `schema_version=2`); `budget_from_state` | `core.schemas.TaskEnvelope`, `core.session.KernelSession`, `discipline.Budget` | `StateGraph(AgentState)` ở `graph/runtime.py:38`; mọi node `graph/nodes.py`; `orchestrator/loop.py`; `adapters/agents/langgraph_agent.py:18` |
| `_CallableLLMTool` (`graph/runtime.py:69`) | Adapter tương thích bọc callable `llm_call(...)` thành tool `llm.chat` cho seam test `run_agent` cũ; `name="callable_llm_tool"` | `execute(request: ToolRequest)` gọi `self.llm_call(messages, model=...)` trả `{"ok", "content"}` | `core.schemas.ToolRequest` | Khởi tạo duy nhất ở `run_agent` (`graph/runtime.py:97`) qua `kernel.registry.register_tool("llm.chat", ...)` |
| `LLMChatTool` (`features/llm_chat.py:17`) | LLM phơi ra như capability `llm.chat` để đi qua `execute_tool` → envelope + events như mọi tool; `client` tiêm được (None → lazy client của adapter); `name="llm_chat_tool"` | `execute(request)` gọi `llm.adapter.call_llm(messages, model, temperature, json_mode, client)` trả `{"ok","content","model"}`; module-level `install(kernel, client=None)` đăng ký `FEATURE` + tool | `core.schemas.ToolRequest`/`FeatureDescriptor`, `llm.adapter.call_llm`, `core.kernel.AgentKernel` | Runtime: `install()` gọi từ `features/loader.py:install_configured_features` (đọc `config/features.yaml:5` → `module: features.llm_chat`); ngoài ra chỉ tests |

> Glue (hàm, KHÔNG phải class):
> - `orchestrator/loop.py`: `run()` (`:89`) — khởi facade công khai: tạo/validate `KernelSession`, dựng `new_agent_state`, mở `open_checkpointer`, `build_agent_graph`, `_stream`; `resume()` (`:213`) — tiếp tục node pending kế tiếp trên cùng `thread_id=run_id`: nếu chưa có SQLite thì migrate qua `_legacy_state`/`_restore_persisted_session`, ngược lại đọc thẳng saver + `graph.get_state`; `_stream` (`:65`) — drive `graph.stream(stream_mode="values")`, ghi projection mỗi giá trị, snapshot khi lỗi; `_outcome`/`_sync_budget`/`_config` helper.
> - `graph/runtime.py`: `build_agent_graph(session, checkpointer, delegation_service)` (`:31`) — compile graph session-bound duy nhất (`partial(node, session=...)`, delegation là port tiêm vào node `delegate`); `run_agent(...)` (`:85`) — facade tương thích ngược trên cùng StateGraph; `_route` đọc `state["route"]`.
> - `graph/nodes.py`: `guard_node` (chặn khi hết step budget), `agent_node` (gọi `llm.chat`, parse 1 action, cập nhật budget/parse-error), `tool_node` (chạy tool qua kernel, chặn lặp tool), `delegation_node` (chokepoint delegation port-neutral), `finish_node` (finish gate + `complete_task`/`fail_task`), `fail_node` (đóng run lỗi qua kernel lifecycle).
> - `orchestrator/checkpoint.py`: `open_checkpointer` (SqliteSaver per-run), `save_graph_projection`/`save_checkpoint` (ghi atomic JSON projection), `load_checkpoint`, `checkpoint_db_path`/`checkpoint_path`.
> - `features/llm_chat.py`: `install(kernel, client=None)` — đăng ký feature `llm` + tool `LLMChatTool` lên registry.

**Call-sites:**

### `Checkpoint`
- **Khởi tạo bởi:** `Checkpoint.from_graph_state(state)` trong `save_graph_projection` (`orchestrator/checkpoint.py:135`), gọi từ `_stream` mỗi step (`orchestrator/loop.py:76,81`); `Checkpoint.from_json(...)` trong `load_checkpoint` (`:143`), `load_checkpoint` được `_legacy_state` dùng (`orchestrator/loop.py:148`).
- **Xuất hiện ở:** def `orchestrator/checkpoint.py:60`; import `from orchestrator.checkpoint import ... save_graph_projection` ở `orchestrator/loop.py:15`. Class `Checkpoint` không được import trực tiếp bởi runtime ngoài module checkpoint.py — loop chỉ dùng qua helper `save_graph_projection`/`load_checkpoint`.
- **Biến/method dùng ở:** `.to_json()` đọc trong `save_checkpoint` (`:129`); field `.backend`/`.status`/`.state`/`.messages`/`.budget`/`.task` đọc trong `_legacy_state` (`orchestrator/loop.py:149-181`). Khởi tạo trực tiếp `Checkpoint(...)` chỉ ở tests (`tests/test_resume.py:68`, `tests/test_checkpoint.py:9`, `tests_audit/test_graph_resume_matrix.py:194`). Lưu ý: `control/checkpoint.py:RuntimeCheckpoint` là class KHÁC (Epic E21), không liên quan.

### `AgentState`
- **Khởi tạo bởi:** không instantiate trực tiếp (TypedDict); dict được sinh ở `new_agent_state` (`graph/state.py:70`) — nơi tạo state khởi đầu duy nhất, gọi từ `orchestrator/loop.py:117`, `graph/runtime.py:107`, `adapters/agents/langgraph_agent.py`. Các node trả về `dict[str, Any]` partial-update được LangGraph merge vào state.
- **Xuất hiện ở:** def `graph/state.py:12`; dùng làm type cho `StateGraph(AgentState)` (`graph/runtime.py:38`), param/return mọi node (`graph/nodes.py:40,51,106,142,202,243`), `_stream`/`_outcome`/`_sync_budget`/`_legacy_state`/`_restore_persisted_session` (`orchestrator/loop.py`), `from_graph_state` (`orchestrator/checkpoint.py:104`), `adapters/agents/langgraph_agent.py:18,54`; export `graph/__init__.py:4`.
- **Biến/method dùng ở:** keys đọc/ghi khắp nodes (`route`, `messages`, `budget`, `session_state`, `last_action`, `status`, `final`, `outcome`); `state.get("session_state") or state.get("kernel_state")` (migrate v1) ở `graph/nodes.py:21`, `orchestrator/loop.py:189`, `orchestrator/checkpoint.py:112`; `budget_from_state`/`decode_session_state` đọc `budget`/`session_state`.

### `_CallableLLMTool`
- **Khởi tạo bởi:** `run_agent` tại `graph/runtime.py:97` — `kernel.registry.register_tool("llm.chat", _CallableLLMTool(llm_call), ...)`; nơi tạo duy nhất.
- **Xuất hiện ở:** def `graph/runtime.py:69`; không import nơi khác. `run_agent` (chủ thể tạo nó) được dùng runtime ở `ui/server.py:24` (nhưng `ui/server.py` import `orchestrator.run` chứ KHÔNG phải `graph.runtime.run_agent` — đây là 2 hàm khác tên trùng alias); `graph.runtime.run_agent` chỉ được gọi trực tiếp ở `tests/test_graph.py`.
- **Biến/method dùng ở:** `.execute(request)` được kernel/registry gọi khi node `agent` thực thi `llm.chat`; `self.llm_call`, `self.name` dùng nội bộ. Thực tế chỉ kích hoạt qua đường `run_agent` (chủ yếu tests).

### `LLMChatTool`
- **Khởi tạo bởi:** `install(kernel, client=None)` tại `features/llm_chat.py:37` — `register_tools(FEATURE.capabilities, LLMChatTool(client=client), ...)`. Runtime: `install()` được gọi từ `features/loader.py:install_configured_features` (`:25`) dựa trên `config/features.yaml` (`llm_chat → module: features.llm_chat`).
- **Xuất hiện ở:** def `features/llm_chat.py:17`; import runtime gián tiếp qua loader (`importlib.import_module`); import trực tiếp `from features.llm_chat import LLMChatTool` chỉ ở tests (`tests/conftest.py:18`, `tests/test_delegation.py:7`, `tests/test_llm_capability.py:4`, `tests/test_orchestrator.py:5`, `tests/test_resume.py:4`, `tests/test_middleware.py:54`, `tests_audit/conftest.py:12`, `tests_audit/test_graph_resume_matrix.py:14`).
- **Biến/method dùng ở:** `.execute(request)` được registry/kernel gọi khi `agent_node` thực thi `session.execute_tool("llm.chat", ...)` (`graph/nodes.py:55`); nội bộ đọc `self._client`, `request.args` (`messages`/`model`/`temperature`/`json_mode`). `FEATURE` (cùng module) đăng ký capability `llm.chat`.

## tools/ — dev/test harness: sinh fixture, fake control server, codegen TS/MAP (Epic E21)

> (dev tooling, KHÔNG nằm trên đường runtime sản phẩm — đây là harness phát triển cho E21/contracts; mọi call-site instantiate/gọi đều ở `tests/`.)

| Class | Ý nghĩa | API chính | Phụ thuộc → | Được dùng bởi ← |
|---|---|---|---|---|
| `_Collect` (`gen_t1_fixture.py:30`) | sink ghi lại từng event đã finalize (seq-stamped + redacted), để dump fixture qua pipeline thật thay vì viết tay JSON | `emit(event)`, field `events: list[RuntimeEvent]` | `control.events.RuntimeEvent` (type) | `build_events()` (`gen_t1_fixture.py:41`) — nơi tạo duy nhất |
| `FakeControlPlane` (`fake_control_server.py:43`) | logic contract thuần (no HTTP) sau 3 endpoint snapshot/stream/commands; dùng lại Redactor + parse_command + build_snapshot thật để UI build trên seam thật | `snapshot()`, `stream()`, `submit_command()`, `_emit()`, `_next_seq()`, `_visibility()`, prop `emitted_types`; fields `buffer`, `event_registry`, `command_registry`, `redactor`, `_dedup` | `control.replay.EventReplayBuffer`, `control.redaction.Redactor`, `control.snapshot.build_snapshot`, `control.commands.parse_command`/`CommandAck`, `control.command_registry`/`event_registry`, `control.events.*`, `control.errors.ControlContractError` | `main()` (`:231`) + `build_server()` (`:215`); `_Handler._cp()` (`:149`). Test: `tests/test_fake_control_server.py:48` |
| `_Handler` (`fake_control_server.py:148`) | adapter HTTP mỏng (stdlib `BaseHTTPRequestHandler`) gắn vào `ThreadingHTTPServer`, ánh xạ GET/POST → method thuần của `FakeControlPlane` | `do_GET()`, `do_POST()`, `_stream()`, `_json()`, `_cp()`, `log_message()` (im lặng) | `FakeControlPlane` (qua `self.server.control_plane`) | `build_server()` (`fake_control_server.py:216`) truyền vào `ThreadingHTTPServer`. (KHÔNG liên quan `_Handler` trùng tên ở `tests_audit/test_delegation_bootstrap_rigor.py:40`) |

> Glue (hàm, KHÔNG phải class):
> - `gen_t1_fixture.build_events()` / `main()` — đẩy 9 `RuntimeEvent` qua `EventEmitter` thật (registry-validate + SessionSeq + Redactor; 1 event mang `api_key=sk-DEMO-LEAK` để chứng minh redaction reachable), ghi `fixtures/control_plane/t1_scenario.events.jsonl`.
> - `fake_control_server.build_server()` / `main()` — dựng `ThreadingHTTPServer` (daemon_threads), load fixture vào `cp.buffer`, serve 3 endpoint; `--no-reality` tắt inject latency cho test xác định.
> - `gen_ts_contracts.render_dts()` / `ts_type()` / `_annotation()` / `main()` — introspect `@dataclass` trong `control/` (`SHAPES`) sinh `ui/control-plane/src/contracts/generated.d.ts`; `ts_type` chỉ map theo whitelist, `raise SystemExit` nếu gặp type lạ (không bao giờ emit `any`); `--check` là drift-guard CI (diff vs file commit, exit 1).
> - `gen_map.first_doc()` / `packages()` / `main()` — đọc dòng docstring đầu mỗi module sinh `MAP.md` (DENY loại `tools`, `tests`, ...).

**Call-sites:**

### `_Collect`
- **Khởi tạo bởi:** `build_events()` tại `gen_t1_fixture.py:41` (`sink = _Collect()`) — nơi tạo duy nhất.
- **Xuất hiện ở:** chỉ `tools/gen_t1_fixture.py` (def `:30`, dùng `:41`).
- **Biến/method dùng ở:** `EventEmitter([sink])` gọi `sink.emit(event)` (qua `EventSinkPort`); `build_events` đọc `sink.events` ở `:83` (`[e.as_dict() for e in sink.events]`). Không dùng ngoài tooling.

### `FakeControlPlane`
- **Khởi tạo bởi:** `main()` tại `fake_control_server.py:231`. Test: `tests/test_fake_control_server.py:48` (`_load_server().FakeControlPlane(token="tok", session_id="t1", **kw)`).
- **Xuất hiện ở:** `tools/fake_control_server.py` (def `:43`; param/return-type của `_Handler._cp()` `:149` và `build_server(cp: FakeControlPlane, ...)` `:215`). Test: `tests/test_fake_control_server.py` (`:48`).
- **Biến/method dùng ở:** `_Handler.do_GET/_stream/do_POST` gọi `cp.snapshot()`/`cp.stream()`/`cp.submit_command()`; `_stream` đọc `cp.inject_reality` (`:181`); `build_server` set `httpd.control_plane = cp` (`:218`) còn `_cp()` đọc lại (`:150`). Nội bộ self.*: `submit_command` dùng `_dedup`/`_next_seq`/`_emit`; `_emit` dùng `redactor.apply` + `buffer.append`; prop `emitted_types` đọc `_emitted`. Ngoài tooling/test: không.

### `_Handler`
- **Khởi tạo bởi:** không khởi tạo trực tiếp — truyền class vào `ThreadingHTTPServer((host, port), _Handler)` tại `fake_control_server.py:216` (server tự instantiate mỗi request).
- **Xuất hiện ở:** chỉ `tools/fake_control_server.py` (def `:148`, dùng `:216`). Test driver dùng gián tiếp qua `build_server` (`tests/test_fake_control_server.py:194`).
- **Biến/method dùng ở:** `do_GET`/`do_POST` được `BaseHTTPRequestHandler` gọi; nội bộ gọi `self._cp()` → `self.server.control_plane`, `self._json()`, `self._stream()`, đọc `self.headers` (`Last-Event-ID`, `X-Auth-Token`/`Authorization`, `Content-Length`). Chỉ chạy trong tooling/test (server demo + `tests/test_fake_control_server.py`).
