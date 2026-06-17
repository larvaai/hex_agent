# MAP — chỉ mục module

> Thường TỰ SINH bằng `python tools/gen_map.py` (đọc docstring dòng đầu mỗi module).
> Bản này điền chuẩn bằng file tool (sandbox đọc mount đang lỗi); trên máy bạn cứ chạy `python tools/gen_map.py` để tái tạo sạch.

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
| `discipline/budget.py` | Loop budgets — steps, parse-errors, same-tool repeats. Epic E02. |
| `discipline/condense.py` | Condense large tool results before re-feeding them to the model. Epic E02. |
| `discipline/finish_gate.py` | Finish gate — block a final when code changed but no validation passed. Epic E02. |
| `discipline/json_gate.py` | Parse + repair the model's JSON action; raise JsonGateError on failure. Epic E02. |

## llm/

| module | mục đích |
|---|---|
| `llm/adapter.py` | OpenAI-compatible LLM adapter — JSON-mode, lazy client, injectable for tests. Epic E03. |

## observability/

| module | mục đích |
|---|---|
| `observability/event_log.py` | EventLogger — JSONL event log + summary.json + metrics; subscribes to the EventBus. Epic E04. |
| `observability/inspect.py` | CLI to inspect runs — list / summary / events from the event log. Epic E04. |

## safety/

| module | mục đích |
|---|---|
| `safety/sandbox.py` | Workspace path-jail — resolve a path and ensure it stays inside the workspace. Epic E06. |
| `safety/policy.py` | Safety chokepoint — ToolPolicy + SafeToolPort applied to every toolbox tool. Epic E06. |

## toolbox/

| module | mục đích |
|---|---|
| `toolbox/filesystem.py` | Workspace-sandboxed filesystem tools: fs_read, fs_write, fs_list. Epic E06. |
| `toolbox/terminal.py` | Terminal tool — run an argv (no shell) inside the workspace with a timeout. Epic E06. |
| `toolbox/feature.py` | Register sandboxed fs + terminal tools, each behind the safety chokepoint. Epic E06. |

## graph/

| module | mục đích |
|---|---|
| `graph/state.py` | AgentState for the single-agent graph loop (reused by multi-agent later). Epic E05. |
| `graph/nodes.py` | Graph nodes: agent (LLM → action) and tool (execute via kernel). Epic E05. |
| `graph/runtime.py` | Single-agent graph runtime: agent↔tool loop with discipline, budget, finish-gate, events. Epic E05. |

## tools/

| module | mục đích |
|---|---|
| `tools/gen_map.py` | Regenerate MAP.md from each module's first docstring line. |

## (root)

| file | mục đích |
|---|---|
| `run_smoke.py` | Deterministic Sprint 0 smoke — no LLM, no network. Prints CORE_AGENT_SMOKE_OK. |
