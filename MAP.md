# MAP — chỉ mục module

> Thường TỰ SINH bằng `python tools/gen_map.py` (đọc docstring dòng đầu mỗi module).
> Bản này điền chuẩn bằng file tool (sandbox đọc mount đang lỗi); trên máy bạn cứ chạy `python tools/gen_map.py` để tái tạo sạch.
>
> **Lưu ý kiến trúc:** chỉ còn một runtime agent: `orchestrator/` là public facade và
> `graph/` là compiled LangGraph theo `KernelSession`. LLM/tool đi qua `AgentKernel.execute_tool`;
> delegation đi qua `DelegationManager` được inject, không phải kernel method;
> SQLite là checkpoint thật, còn `checkpoint.json` chỉ là projection cho UI.

## adapters/

| module | mục đích |
|---|---|
| `adapters/agents/langgraph_agent.py` | Concrete DelegationPort implemented by the existing session-bound LangGraph. |
| `adapters/agents/scripted.py` | Deterministic delegation adapter for tests and local architecture smoke runs. |

## core/

| module | mục đích |
|---|---|
| `core/bootstrap.py` | Build a kernel and install features + middleware from config. Epic E01/E06. |
| `core/events.py` | Thread-safe subscriber registry with detached event delivery. |
| `core/kernel.py` | Shared, frozen capability runtime; per-run state and lifecycle live in KernelSession. |
| `core/middleware.py` | ToolMiddleware protocol — pre/post hook around execute_tool. Epic E01/E06. |
| `core/ports.py` | Framework-neutral tool, delegation, store, and service protocols. |
| `core/registry.py` | CapabilityRegistry + NullToolPort — resolve a tool name to an executor, with graceful fallback. Epic E01. |
| `core/schemas.py` | Task/tool/session-context and structured delegation data contracts. |
| `core/session.py` | Per-run state/lifecycle isolation over a shared, frozen AgentKernel. |
| `core/state.py` | Session-owned in-memory state with detached snapshot/restore for persistence. |

## delegation/

| module | mục đích |
|---|---|
| `delegation/bootstrap.py` | Composition helper for the default local delegation target. |
| `delegation/manager.py` | Sequential delegation chokepoint: policy, child session, progress, events, result. |
| `delegation/policy.py` | Delegation depth, budget, and capability-scope enforcement. |
| `delegation/registry.py` | Target-to-port resolution with explicit ambiguity failure. |
| `delegation/store.py` | Thread-safe delegation store with ordered, idempotent progress writes. |

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
| `graph/nodes.py` | Session-bound LangGraph nodes; tool and delegation use separate chokepoints. |
| `graph/runtime.py` | Compile the session-bound LangGraph; delegation remains an injected application port. |
| `graph/state.py` | Serializable LangGraph state and codec for isolated KernelSession state. |

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
| `observability/event_log.py` | Thread-safe JSONL event log, summaries, and tool/graph/delegation metrics. |
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
