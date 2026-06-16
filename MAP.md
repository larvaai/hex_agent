# MAP — chỉ mục module

> Thường TỰ SINH bằng `python tools/gen_map.py` (đọc docstring dòng đầu mỗi module).
> Bản này điền chuẩn bằng file tool do mount sandbox đang đọc lỗi; trên máy bạn cứ chạy `python tools/gen_map.py` để tái tạo.

## core/

| module | mục đích |
|---|---|
| `core/bootstrap.py` | Build a kernel and install features from config/features.yaml. Epic E01. |
| `core/events.py` | EventBus — minimal pub/sub that the observability layer subscribes to. Epic E01/E04. |
| `core/kernel.py` | AgentKernel — minimal core owning state, events, and capability execution. Epic E01. |
| `core/ports.py` | ToolPort protocol — the seam every concrete tool implements. Epic E01. |
| `core/registry.py` | CapabilityRegistry + NullToolPort — resolve a tool name to an executor, with graceful fallback. Epic E01. |
| `core/schemas.py` | Core data contracts: TaskEnvelope, ToolRequest, CapabilityResult envelope, FeatureDescriptor. Epic E01. |
| `core/state.py` | StateStore — in-memory run state held by the kernel. Epic E01. |

## discipline/

| module | mục đích |
|---|---|
| `discipline/budget.py` | Loop budgets — steps, parse-errors, same-tool repeats (parse errors do not consume steps). Epic E02. |
| `discipline/condense.py` | Condense large tool results before re-feeding them to the model. Epic E02. |
| `discipline/finish_gate.py` | Finish gate — block a final when code changed but no validation passed. Epic E02. |
| `discipline/json_gate.py` | Parse + repair the model's JSON action; raise JsonGateError on failure. Epic E02. |

## features/

| module | mục đích |
|---|---|
| `features/example_echo.py` | Example feature — an echo tool used by smoke/tests and as the plugin pattern. Epic E01. |
| `features/loader.py` | Install the features that are enabled in config['features']. Epic E01. |

## llm/

| module | mục đích |
|---|---|
| `llm/adapter.py` | OpenAI-compatible LLM adapter — JSON-mode, lazy client, injectable for tests. Epic E03. |

## observability/

| module | mục đích |
|---|---|
| `observability/event_log.py` | EventLogger — JSONL event log + summary.json + metrics; subscribes to the EventBus. Epic E04. |
| `observability/inspect.py` | CLI to inspect runs — list / summary / events from the event log. Epic E04. |

## tools/

| module | mục đích |
|---|---|
| `tools/gen_map.py` | Regenerate MAP.md from each module's first docstring line. |

## (root)

| file | mục đích |
|---|---|
| `run_smoke.py` | Deterministic Sprint 0 smoke — no LLM, no network. Prints CORE_AGENT_SMOKE_OK. |
