# Bách khoa class — core_agent (Sprint 0 + 1)

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
