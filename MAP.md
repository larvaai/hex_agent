# MAP — chỉ mục module

> Thường TỰ SINH bằng `python tools/gen_map.py` (đọc docstring dòng đầu mỗi module).
> Bản này điền chuẩn bằng file tool (sandbox đọc mount đang lỗi); trên máy bạn cứ chạy `python tools/gen_map.py` để tái tạo sạch.
>
> **Lưu ý kiến trúc:** chỉ còn một runtime agent: `orchestrator/` là public facade và
> `graph/` là compiled LangGraph. LLM/tool đều đi qua `AgentKernel.execute_tool`;
> SQLite là checkpoint thật, còn `checkpoint.json` chỉ là projection cho UI.

## core/

| module | mục đích |
|---|---|
| `core/bootstrap.py` | Build a kernel and install features + middleware from config. Epic E01/E06. |
| `core/events.py` | EventBus — minimal pub/sub that the observability layer subscribes to. Epic E01/E04. |
| `core/kernel.py` | AgentKernel — minimal core: state, events, capability chokepoint, task lifecycle. Epic E01/E05. |
| `core/middleware.py` | ToolMiddleware protocol — pre/post hook around execute_tool. Epic E01/E06. |
| `core/ports.py` | ToolPort protocol — the seam every concrete tool implements. Epic E01. |
| `core/registry.py` | CapabilityRegistry + NullToolPort — resolve a tool name to an executor, with graceful fallback. Epic E01. |
| `core/schemas.py` | Core data contracts: TaskEnvelope, ToolRequest, CapabilityResult envelope, FeatureDescriptor. Epic E01. |
| `core/state.py` | StateStore — in-memory run state held by the kernel; snapshot/restore for persistence. Epic E01/E07. |

## discipline/

| module | mục đích |
|---|---|
| `discipline/budget.py` | Loop budgets — steps, parse-errors, same-tool repeats. Epic E02. |
| `discipline/condense.py` | Condense large tool results before re-feeding them to the model. Epic E02. |
| `discipline/finish_gate.py` | Finish gate — block a final when code changed but no validation passed. Epic E02. |
| `discipline/json_gate.py` | Parse + repair the model's JSON action; raise JsonGateError on failure. Epic E02. |

## features/

| module | mục đích |
|---|---|
| `features/example_echo.py` | Example feature — an echo tool used by smoke/tests and as the plugin pattern. Epic E01. |
| `features/llm_chat.py` | LLM exposed as a capability — flows through execute_tool -> envelope + events like any tool. Epic E03/E04. |
| `features/loader.py` | Install the features that are enabled in config['features']. Epic E01. |

## graph/

| module | mục đích |
|---|---|
| `graph/nodes.py` | LangGraph nodes; every external action still crosses AgentKernel.execute_tool. |
| `graph/runtime.py` | Compile the single-agent LangGraph; no handwritten agent loop lives here. |
| `graph/state.py` | Serializable LangGraph state and the codec for the microkernel's in-memory state. |

## llm/

| module | mục đích |
|---|---|
| `llm/adapter.py` | OpenAI-compatible LLM adapter — JSON-mode, lazy client, retry/backoff on transient errors, injectable. Epic E03. |

## middleware/

| module | mục đích |
|---|---|
| `middleware/budget.py` | BudgetGuard — block repeated identical tool calls; reuses discipline.Budget. Epic E02/E06. |
| `middleware/condense.py` | CondenseResult — shrink a tool result before re-feeding the model; reuses discipline.condense. |
| `middleware/policy.py` | PolicyGate — deny-list chokepoint; blocks a tool before it runs. Epic E06. |
| `middleware/retry.py` | Retry — re-invoke the inner handler on a non-ok result (never on a policy block). Epic E06. |
| `middleware/timing.py` | TimingLog — measure wall-time around a tool call; register outermost. Epic E04. |

## observability/

| module | mục đích |
|---|---|
| `observability/event_log.py` | EventLogger — JSONL event log + summary.json + metrics; subscribes to the EventBus. Epic E04. |
| `observability/inspect.py` | CLI to inspect runs — list / summary / events from the event log. Epic E04. |

## orchestrator/

| module | mục đích |
|---|---|
| `orchestrator/checkpoint.py` | LangGraph SQLite persistence plus a JSON run-state projection for the local UI. |
| `orchestrator/loop.py` | Public run/resume facade backed by the single compiled LangGraph. |

## safety/

| module | mục đích |
|---|---|
| `safety/policy.py` | Safety chokepoint — ToolPolicy + SafeToolPort applied to every toolbox tool. Epic E06. |
| `safety/sandbox.py` | Workspace path-jail — resolve a path and ensure it stays inside the workspace. Epic E06. |

## toolbox/

| module | mục đích |
|---|---|
| `toolbox/feature.py` | Register sandboxed fs + terminal tools, each behind the safety chokepoint. Epic E06. |
| `toolbox/filesystem.py` | Workspace-sandboxed filesystem tools: fs_read, fs_write, fs_list. Epic E06. |
| `toolbox/terminal.py` | Terminal tool — run an argv (no shell) inside the workspace with a timeout. Epic E06. |

## tools/

| module | mục đích |
|---|---|
| `tools/gen_map.py` | Regenerate MAP.md from each module's first docstring line. |

## (root)

| file | mục đích |
|---|---|
| `run_smoke.py` | Deterministic Sprint 0 smoke — no LLM, no network. Prints CORE_AGENT_SMOKE_OK. |
