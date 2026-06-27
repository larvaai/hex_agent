---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Codebase map — `drag_from_zero`

Scope: `drag_from_zero/` (~5.6k LOC total, ~2.3k core). Read-only comprehension. 2026-06-26.

## One sentence

A dynamically-composable multi-agent runtime where **the event log is the only state** and everything else (execution tree, UI, eval scores) is a *pure projection* of it — built slice-by-slice on a deterministic FakeLLM so the harness is testable before real weights ever run.

## The load-bearing idea: two graphs, never merged

| | Đồ thị 1 — Topology | Đồ thị 2 — Execution tree |
|---|---|---|
| time | design-time | run-time |
| nature | static, authored (drag-drop / JSON) | emergent, orchestrator-grown |
| node | Agent / Tool / Router / Memory / Hook | task instance + live status |
| is | **config** (`topology.py`) | **projection of the event log** (`read_model.reduce`) |

`wiring.build_runtime(topology, llm)` is the bridge: config → runnable `Orchestrator`. The orchestrator emits events; `reduce` folds them back into the tree. The UI, CLI view, and eval are all just consumers of the same event stream.

## Module key (core = `dragzero/`)

| File | LOC | Responsibility |
|---|---|---|
| `events.py` | 68 | `EventType` enum (13 types) + append-only `EventLog` (stamps `seq`, fan-out to subscribers). **Single source of truth.** |
| `contracts.py` | 87 | First-class dataclasses: `DelegationDecision` (solo/delegate), `PlanSpec`/`PlanStep`, `ToolCall`, `TaskStatus`. All `to_dict`/`from_dict`. Delegation is an *artifact*, not a hidden call. |
| `read_model.py` | 75 | `reduce(events) -> (root, nodes)` — stateless fold → `TaskNode` tree (Đồ thị 2). |
| `orchestrator.py` | 275 | **The engine.** Pausable FIFO work-queue + bounded ReAct loop. Routes, spawns children, gates on budget/hooks, settles parents. Emits every event. |
| `agent.py` | 57 | Thin actor: `step()` calls `llm.complete(ctx)` → either a tool action or a terminal decision. No policy of its own. |
| `llm.py` | 39 | The **LLM port** (`Protocol`) + `FakeLLM` (scripted) + `by_role` responder dispatcher. |
| `registries.py` | 83 | Empty-by-default gates: `HookRegistry`, `RuleRegistry`, `ToolRegistry`, `Budget` (disabled until a limit is set). Ships the cổng, not the luật. |
| `roster.py` | 34 | Live agent registry, `by_role_or_id` lookup; mutated mid-session. |
| `builtins.py` | 48 | Named catalogs the topology references: `BUILTIN_HOOKS` (deny_delegation/deny_all), `BUILTIN_RULES` (by_keyword/always). |
| `topology.py` | 122 | Đồ thị 1 as pure data — node palette + edges + budget, JSON round-trip + `validate()`. Imports zero runtime. |
| `wiring.py` | 89 | `build_runtime(topology, llm)` → `Runtime(orchestrator, entry)`. Unknown capability name → `TopologyError`. LLM injected, not in topology. |
| `tools.py` | 27 | Tool **port**: `Tool` protocol, `ToolResult`, `SandboxError`. |
| `live_view.py` | 61 | CLI renderer of the projection (`render_tree`/`render_log`). Proof the projection is self-sufficient. |
| `server.py` | 415 | Slice 6a HTTP+WS (stdlib only) serving `ui/`. `build_graph` (tree→UI shape) + `translate_event` (our vocab→UI vocab). Read-only on the log; run on a daemon thread. |
| `adapters/llm_local.py` | 267 | Real local LLM behind the port: `OpenAICompatLLM` (LM Studio/llama.cpp via urllib) with JSON-extract → 1 strict repair → safe `solo_fallback`; `RecordedLLM` replays through the same parse path. |
| `adapters/tools_fs.py` | 112 | `FsSandbox` (root-confined, `..` → `SandboxError`) + read/write/list/run_command tools + `default_tool_catalog`. |
| `eval/` | ~320 | Separate scoring harness (consumes core; core never imports it). `Scenario`=task+roles+scorers; `runner` runs trials → aggregate (pass-rate/mean/variance) → report. |

## Control + data flow (the spine)

```
start(desc) ─► ROOT_TASK_CREATED ─► _route ─► _ready queue
run_until_idle() drains FIFO ─► _process_one(task):
  no agent ............................► TASK_FAILED
  budget.charge() fails ...............► BUDGET_EXCEEDED (halt, clear queues)
  ► TASK_STARTED
  hooks.check("pre_plan") blocks ......► HOOK_BLOCKED + TASK_FAILED
  ReAct loop: agent.step():
    kind=tool ► TOOL_CALLED ► _run_tool ► TOOL_RESULT ► observe ► charge ► loop
                (guard: max_tool_steps)
    kind=terminal ► PLAN_PRODUCED ► DELEGATION_DECIDED:
       delegate ► hooks.check("pre_delegate"):
                    block ► solo-fallback _complete
                    pass  ► _spawn(child)
       solo     ► _complete
_spawn: route(child, prefer=target) ► SUBTASK_SPAWNED
        target None ► park in _waiting + TASK_WAITING
        else ........► enqueue child
_complete ► TASK_COMPLETED ► _settle (walk parents, remaining--; 0 ► parent done)
```

**Mid-run injection (the headline requirement):** `join_agent(agent, resume)` → `roster.add` + `AGENT_JOINED` → `_wake_waiting()` re-routes parked `_waiting` tasks back to `_ready` → resume drains them. A delegation to an unfilled role *parks* (waiting) instead of mis-routing; injecting the agent wakes it. This is real pause→inject→resume, not a between-runs hack.

**Projection chain:** `EventLog` ──`reduce`──► `TaskNode` tree ──► {`live_view.render` (CLI) | `server.build_graph`+`translate_event` (UI) | `eval` scorers}. Same events, four consumers, zero parallel state.

## External boundaries (ports & adapters)

- **LLM port** `llm.LLM.complete(ctx)->dict`. Adapters: `FakeLLM`, `OpenAICompatLLM` (HTTP→OpenAI-compat endpoint, `OPENAI_BASE_URL`/`MODEL`), `RecordedLLM`. Core never knows which.
- **Tool port** `tools.Tool.run(args, sandbox)->ToolResult`. Adapter: `adapters/tools_fs` (real FS + `subprocess` for `run_command`).
- **HTTP/WS** `server.py` — stdlib `http.server` + hand-rolled WebSocket frame codec; serves `ui/Agent IDE.dc.html`.
- **Everything empty by default** — no tool/hook/rule/budget fires until registered (gates, not rules).

## Task entry points

| Want to… | Start here |
|---|---|
| Understand the model | `README.md` then `events.py` → `orchestrator.py` → `read_model.py` |
| Run the demo | `demo.py` / `python -m pytest -q` |
| Run on real weights | `run_local.py --task ... [--sandbox ./work]` (LM Studio up) |
| Score a model | `run_eval.py [--real --trials N]` |
| Serve the UI | `run_server.py [--real]` → http://127.0.0.1:8000 |
| Add a capability | `builtins.py` (catalog) + `examples/topology.json` (wire it) |
| See invariants | `tests/test_invariants.py` (the contract the harness must hold) |

## Slice history (what each added, all backward-compatible)

1. Closed loop on FakeLLM (events + tree + projection). 2. Real LLM behind the port (parse/repair/fallback). 3a. Pausable work-queue + true mid-run injection. 3b. Eval harness (scored, not pass/fail). 4. Tool execution + FS sandbox (ReAct). 5. Topology loader (Đồ thị 1 as JSON) + wiring. 6a. HTTP/WS server for the Agent-IDE UI.

## Open unknowns / deferred (verify before building on)

- **Slice 6b verifier is the big gap** — `mu`-driven *decompose-until-trivial*, `done_when` acceptance gates, real pass/fail `verdict`s with evidence. Today `server.build_graph` stubs `mu` (= subtree size) and `done_when` (= files written). This is exactly the [[decompose-until-trivial-principle]] memory; a separate plan exists (`plans/260626-1528-decompose-agent-recursion-slice/`).
- **No enforcement of edges** — topology validates wiring structurally but per-agent tool/delegation *permissions* aren't enforced at runtime.
- **`memory` node type** is a round-trip placeholder, not wired (`wiring.py:70`).
- **Execution is synchronous** FIFO depth-first — async/parallel deferred by design.
- **`ui/` not deeply read** — `Agent IDE.dc.html` + `project-data.js` + `support.js`; server contract inferred from `build_graph`/`translate_event`, not the JS.
- **No path-traversal review done** on `server._static` (it does prefix-check `full.startswith(static_dir)`); out of scope for this map.
