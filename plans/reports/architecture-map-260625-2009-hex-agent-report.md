---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Codebase Map — hex_agent (pkg `core_agent`) · Architecture

Generated: 2026-06-25
Scope: whole-repo architecture (layers, ports/adapters seams, control+data flow, boundaries, entry points)
Map path: /Users/uspro/Desktop/Namson/hex_agent/plans/reports/architecture-map-260625-2009-hex-agent-report.md

> Hexagonal / microkernel multi-agent system, rebuilt epic-by-epic E01..E21.
> **One load-bearing invariant:** every LLM and tool call crosses the single chokepoint
> `AgentKernel.execute_tool` (`core/kernel.py:63`). LLM is just a capability `llm.chat`.
> Delegation is a *deliberately separate* chokepoint. SQLite is the only resume truth.

## Module / layer overview

| Layer | Directory / Module | Primary responsibility |
|---|---|---|
| Microkernel core (E01) | `core/` | Frozen capability runtime: chokepoint `execute_tool`, registry, envelope, EventBus, per-run `KernelSession` + scope |
| Discipline (E02) | `discipline/` | Pure functions: json parse+repair, finish-gate, budgets, condense — reused everywhere |
| LLM adapter (E03) | `llm/`, `features/llm_chat.py` | OpenAI-compatible lazy client (JSON-mode, retry); exposed as capability `llm.chat` |
| Observability (E04) | `observability/` | EventBus subscriber → `events.jsonl` + `summary.json` + inspect CLI |
| Single-agent runtime (E05) | `graph/`, `orchestrator/` | One compiled LangGraph per run; public `run()/resume()` facade over SQLite checkpoint |
| Tools & Safety (E06) | `toolbox/`, `safety/`, `middleware/` | Sandboxed fs/terminal tools; 2 parallel safety layers; middleware onion |
| Skills / Roles (E07/E09) | `skills/`, `roles/` | Role-agnostic SKILL contracts → role allowlist derivation (cycle-break) |
| RAG (E08) | `rag/` | Health-gated ingest/search behind `VectorStorePort`/`EmbedderPort` (memory default, Qdrant optional) |
| Multi-agent + delegation (E10) | `supervisor/`, `delegation/`, `adapters/` | Agent-O round-based TaskLoop above frozen kernel; delegation = separate seam |
| Control plane + UI (E21/E18) | `control/`, `ui/`, `config/` | Event/command contracts + EventEmitter (partial); legacy HTTP/SSE console |

## File-key + responsibility

**Core chokepoint (E01)**
- `core/kernel.py` — **THE entrypoint.** `AgentKernel.execute_tool` (`:63`) the single chokepoint; `freeze()` (`:48`) deep-freezes registry+config+middleware; `use()` registers middleware outer→inner; `_wrap` (`:24`) avoids late-binding closure bug.
- `core/ports.py` — seams: `ToolPort` (`:20`), `DelegationPort`/`DelegationStorePort`/`DelegationServicePort` (`:32/:48/:65`).
- `core/registry.py` — `CapabilityRegistry.resolve_tool` (`:103`, exact→fallback→`NullToolPort`); `ToolDescriptor(kind/idempotent/risk)` (`:10`); `NullToolPort` (`:29`) keeps kernel alive on missing capability.
- `core/schemas.py` — frozen contracts: `TaskEnvelope`, `ToolRequest`, `ToolCallContext` (carries `allowed_capabilities`), `CapabilityResult.from_raw` (`:74`, normalizes any raw dict → envelope), `DelegationSpec` (`:132`).
- `core/session.py` — `KernelSession` (per-run state+scope); `SessionFactory` (`:104`) sole constructor; `create_child` enforces scope ⊆ parent (`:163`, `PermissionError`).
- `core/events.py` — `EventBus.publish` (`:22`) deep-copies payload per subscriber, swallows subscriber exceptions (observer can't break runtime).
- `core/middleware.py` — `ToolMiddleware` Protocol (`:11`) pre/post around chokepoint.
- `core/bootstrap.py` — `build_kernel` (`:56`): install features → middleware; `_install_middleware` fixed order timing→policy→retry→condense; **BudgetGuard deliberately excluded** (per-run state).
- `features/loader.py` — `install_configured_features` (`:10`) importlib + `module.install(kernel)` plugin contract, driven by config.

**Single-agent runtime (E05)**
- `graph/state.py` — `AgentState` TypedDict (`:12`), `schema_version=2`, `encode/decode_session_state` + v1 `kernel_state` migration.
- `graph/nodes.py` — nodes: `guard` (`:40`), `agent` (`:51`, `llm.chat` + `parse_action`), `tool` (`:106`, inline same-tool guard), `delegate` (`:141`), `finish` (`:202`, `check_finish` gate), `fail` (`:243`).
- `graph/runtime.py` — `build_agent_graph` (`:31`) binds one session; topology `START→guard→agent→{tool|delegate|finish|guard|fail}…END` (`:49-65`); `run_agent` (`:85`).
- `orchestrator/loop.py` — `run()` (`:89`, `run_id==thread_id`, `checkpoint=True`), `resume()` (`:213`, SQLite restore + legacy json migration `:146`).
- `orchestrator/checkpoint.py` — `open_checkpointer` (`:35`) `SqliteSaver` over `langgraph.sqlite`; `checkpoint.json` is UI projection only.

**Tools & safety (E06)**
- `safety/sandbox.py` — `resolve_in_workspace` (`:18`) path-jail; `SandboxError` on escape; workspace from `AGENT_WORKSPACE_DIR`.
- `safety/policy.py` — **Layer B**: `classify_terminal` (`:53`, blocks shell/destructive/git-mutation/abs-path escape), `ToolPolicy.check` (`:88`), `SafeToolPort` (`:105`) per-tool wrap.
- `toolbox/feature.py` — registers `fs_read/fs_write/fs_list/terminal_run`, each wrapped in `SafeToolPort` with kind/idempotent/risk descriptors (`:19-36`).
- `toolbox/terminal.py` — `Terminal.execute` re-runs `classify_terminal` in-tool (defense-in-depth `:21`); argv-only `subprocess.run`, no shell, 1–30s timeout.
- `middleware/policy.py` — **Layer A**: `PolicyGate` name-deny short-circuit (`:15`); inert by default (no `middleware` key in default config).
- `middleware/retry.py` — `_retryable` (`:14`) refuses `policy_block` and `effect`+non-idempotent (S10.13 guard).
- `middleware/{condense,timing,budget}.py` — condense skips `llm.*`; timing outermost; BudgetGuard tests-only.

**Discipline (E02) + LLM (E03)**
- `discipline/json_gate.py` — `parse_json_object` (`:64`, strip fences→repair→brace-scan), `parse_action` (`:91`), `build_retry_message`.
- `discipline/finish_gate.py` — `check_finish` (`:15`) blocks final when code_changed & !validation_passed.
- `discipline/budget.py` — `Budget` (max_steps 30 / parse 3 / same-tool 3); `tool_key` for dedup.
- `llm/adapter.py` — `call_llm` (`:53`) lazy openai client, JSON-mode, `_is_transient` (`:40`) exp-backoff retry vs permanent, **never raises** (returns error-final).

**Vertical slices (E07/E08/E09)**
- `rag/ports.py` — `EmbedderPort`/`VectorStorePort` (`:25/:32`); `RagConfig`.
- `rag/service.py` — `_require_healthy` (`:30`, `dependency_unavailable` gate) atop ingest/search; sandbox jail; delete-then-upsert replace.
- `rag/stores_qdrant.py` — `QdrantVectorStore` lazy client, double-checked-lock create + keyword index, `uuid5` deterministic ids, `health()` never raises.
- `rag/feature.py` — backend select memory|qdrant (`:27`); emits `rag.health/ingest/search` via injected publish.
- `roles/spec.py` — **`allowed_tools` (`:53`) = union(explicit|core|skill.allowed) − skill.forbidden** (the single home of the E07→E09 cycle-break); `RoleView` projection.
- `roles/agent.py` — `guard_tool_call`/`guard_finish`; `build_prompt` (system+lenses+tools+contracts).
- `skills/registry.py` — `render(contract|full)` progressive disclosure (`:57`); `union_tools` (`:79`) feeds E09.
- `observability/event_log.py` — `events.jsonl` (`:60`) + `summary.json`/`index.jsonl`; `attach_to_bus` (`:102`) maps topics→kinds+counters.

**Multi-agent (E10) + delegation**
- `supervisor/loop.py` — `run_task_loop` (`:70`), `resume_task_loop` (`:107`, ownership guard `:126`), `_drive` (`:147`).
- `supervisor/graph.py` — `run_round` (builds `DelegationPolicy` from O assignment → delegate `:173`), `run_tool` (`:213` via `execute_tool`), `judge_acceptance` (`:229`); only consumer of `control/` emitter (opt-in, default None `:47`).
- `supervisor/llm.py` — `KernelChatLLM` reaches model via `execute_tool('llm.chat')` (`:64`) — O/Broker disciplined like any capability.
- `delegation/manager.py` — `DelegationManager.delegate` (`:63`): `policy.validate` → `create_child(scope=allowed_capabilities)` → `handler.run`. **Separate chokepoint from the kernel.**
- `adapters/agents/{scripted,langgraph}.py` — `DelegationPort` adapters.

**Control plane (E21) + UI**
- `control/events.py` — `RuntimeEvent` envelope (`:113`); `ui_payload` None-until-Redactor; `TraceContext`/`SessionSeq`.
- `control/commands.py` / `control/checkpoint.py` / `control/permission.py` — frozen `RuntimeCommand`/`RuntimeCheckpoint`/`Permission` contracts with validation.
- `control/redaction.py` — `Redactor` (`:37`) recursive secret-key mask (14 keys), records paths, never mutates original.
- `control/emitter.py` — `EventEmitter.emit_event` (`:53`): gate→seq→redact→fan-out; `BusEventSink` bridges to EventBus/EventLogger.
- `control/ports.py` — `EventSinkPort` (`:14`) — the swap seam (v1 BusEventSink; Kafka/Redis = T2 future).
- `config/runtime_event_types.yaml` / `runtime_command_types.yaml` — allowlist registries (visibility/durable/redact + apply_at/requires_permission).
- `ui/server.py` — legacy HTTP/SSE console (`/api/{bootstrap,runs,snapshot,tree,file,stream}`); **does NOT import `control/`**.
- `run_smoke.py` — deterministic no-LLM smoke → `CORE_AGENT_SMOKE_OK`.

## Data / control flow

**Boot:** `create_kernel` → `load_config` (`config/features.yaml`) → `install_configured_features` (each `module.install(kernel)` registers tools/features) → `_install_middleware` (no-op under default config) → kernel frozen at first `create_root`.

**Single-agent task (the chokepoint loop):**
1. `orchestrator.run()` builds a LangGraph bound to one `KernelSession` (root scope).
2. `guard` checks step budget → `agent` calls `session.execute_tool('llm.chat')` → `parse_action`.
3. Every call enters `AgentKernel.execute_tool`: deep-copy args → publish `tool.requested` → **scope check** (not-in-`allowed_capabilities` → `scope_block`, return) → build middleware onion (`reversed(_middlewares)`, first-registered = outermost) → `core` closure resolves tool + executes + `CapabilityResult.from_raw` stamps kind/idempotent/risk → publish `tool.completed|failed`.
4. Routed verb → `tool` (SafeToolPort.check → terminal re-classify → execute) | `delegate` | `finish`.
5. `finish` applies `check_finish` (code_changed needs validation) → `complete_task` or route to `fail`.
6. After each step the loop checkpoints to **`langgraph.sqlite`** (truth) + writes `checkpoint.json` (UI projection).

**Multi-agent (E10):** `run_task_loop` drives a round-based Blackboard (`TaskLoopState`). Agent-O emits structured JSON decisions (json-gate parsed); O never calls tools directly — `need_tool` crosses `execute_tool`; `run_round` builds a `DelegationPolicy` then calls the **delegation** seam; `judge_acceptance` gates acceptance criteria. State persists to `taskloop.sqlite`; resume refuses foreign session/task identity.

**Delegation (separate seam):** `DelegationManager.delegate` → `policy.validate` → `SessionFactory.create_child` (scope ⊆ parent) → `handler.run` (scripted | langgraph adapter). Progress persisted before publish. Never a kernel method.

**Resume:** `orchestrator.resume(run_id)` reads SQLite via `get_state` and continues (`stream(None)`); one-time legacy `checkpoint.json` migration path exists. `resume` never trusts the JSON projection.

**Observability:** kernel only publishes; `EventLogger.attach_to_bus` subscribes and writes `events.jsonl` + counters → `summary.json`/`index.jsonl` under `var/agent_runs/<run_id>/`.

**Control plane (E21, partial):** when an `EventEmitter` is injected into `SupervisorContext`, `loop.*` events flow through the canonical `RuntimeEvent` envelope (gate→seq→redact→fan-out to `EventSinkPort`→`BusEventSink`→existing EventLogger). Default is None → legacy raw `bus.publish`.

## External boundaries

- **LLM API** — OpenAI-compatible chat endpoint, default `localhost:1234/v1` (`llm/adapter.py:15,31,67`).
- **Qdrant** — HTTP vector store, optional (`backend: qdrant`), `rag/stores_qdrant.py:43`; `fastembed` model `BAAI/bge-small-en-v1.5`.
- **SQLite** — `langgraph.sqlite` (single-agent, `orchestrator/checkpoint.py:30`) and `taskloop.sqlite` (supervisor, `supervisor/checkpoint.py:34`) — resume truth.
- **Filesystem** — workspace path-jail for all fs tools + terminal cwd (`safety/sandbox.py`); JSONL run logs under `var/agent_runs/` (gitignored).
- **Terminal subprocess** — argv-only, no shell, 1–30s timeout (`toolbox/terminal.py:33`).
- **HTTP/SSE** — local observability console (`ui/server.py:517-551`).
- **Config YAML (user-edited)** — `config/features.yaml` (features + optional middleware), `config/runtime_{event,command}_types.yaml` (E21 registries).
- **Env vars** — `AGENT_WORKSPACE_DIR`, `AGENT_ALLOW_GIT_MUTATIONS`, `AGENT_RUNS_DIR`/`AGENT_EVENT_LOG`, `LLM_{BASE_URL,API_KEY,MODEL,MAX_TOKENS,TIMEOUT=120,MAX_RETRIES=2,RETRY_BASE=0.5}`.

## Task entry points

| Task | Start at |
|---|---|
| Run a single-agent task | `orchestrator/loop.py` `run()` (`:89`) |
| Resume an interrupted run | `orchestrator/loop.py` `resume()` (`:213`) |
| Run a multi-agent task | `supervisor/loop.py` `run_task_loop()` (`:70`) |
| Add a tool / capability | new `features/<x>.py` (`FEATURE` + `install()`) + enable in `config/features.yaml` |
| Add a sandboxed fs/terminal tool | `toolbox/` + register via `SafeToolPort` in `toolbox/feature.py` |
| Change a safety rule | `safety/policy.py` `classify_terminal`/`ToolPolicy.check` |
| Add cross-cutting middleware | `middleware/` + `config['middleware']` + `core/bootstrap.py:_install_middleware` |
| Add a role / skill | `roles/library/*.yaml`, `skills/library/*.md` (allowlist derives in `roles/spec.py`) |
| Add a RAG backend | implement `rag/ports.py` ports; select in `rag/feature.py` |
| Inspect a run's events | `observability/inspect.py` (`list`/`summary`/`events`) |
| Add a control-plane event/command | declare in `config/runtime_*_types.yaml` + `control/` contracts |
| Touch the UI | `ui/server.py` + `ui/static/` |

## Open unknowns

- [ ] **Default config has no `middleware` section** → `timing/policy/retry/condense` are inert by default; only the per-tool `SafeToolPort` layer is active. Whether any shipped config enables the middleware chain is not visible. (`core/bootstrap.py:28`, `config/features.yaml`)
- [ ] **Where `EventLogger.attach_to_bus` is invoked per run** — bootstrap builds the kernel but the obs-wiring call site (and `finish`/summary trigger) is outside `core/bootstrap.py`. (`observability/event_log.py:102`)
- [ ] **`repair_mode=True` entry point (S10.12)** — `ToolPolicy` is built with `repair_mode=False` at toolbox install; who flips it (patch-only writes) is unresolved. (`safety/policy.py:95`)
- [ ] **`run_id`/`thread_id` collision handling** — uniqueness guarantee not traced. (`orchestrator/checkpoint.py:22`)
- [ ] **E21 control plane is not wired into the live runtime/UI**: no production `bus_emitter` caller, no `CommandGateway` (Phase C), no checkpoint/permission persistence (B4/B5), `ui/server.py` SSE is poll-diff not an `EventEmitter` subscription. Frontier work, not a defect. (`control/emitter.py`, `supervisor/graph.py:47`)
- [ ] Minor: `Redactor` masks **14** secret keys (doc/spec said 15). (`control/redaction.py:16`)

---
*Map is comprehension input for `hs:plan` — not a plan, no code changed. Companion progress/status report is in the prior session turn. Docs hygiene note: `MAP.md`, `README.md`, `project_context.txt`, `CLASS_ENCYCLOPEDIA.md` are stale vs current code; trust `CHANGELOG.md` + `docs/rebuild_from_zero/` + `KNOWN_RISKS.md` + `RUNTIME_FLOW.md`.*
