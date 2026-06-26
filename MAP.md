# MAP — chỉ mục module (TỰ SINH bởi `tools/gen_map.py`)

Mỗi module + một dòng mục đích + epic. **Chạy lại `python tools/gen_map.py`** sau khi thêm/đổi file.

## adapters/

| module | mục đích |
|---|---|

## control/

| module | mục đích |
|---|---|
| `control/checkpoint.py` | RuntimeCheckpoint — the approval-gate contract for risky actions. Epic E21 (S21.5). |
| `control/command_registry.py` | Command-type registry — declares when each command applies and what it needs. Epic E21 (S21.4). |
| `control/commands.py` | RuntimeCommand — the one structured shape for every UI/human intervention. Epic E21 (S21.3). |
| `control/emitter.py` | EventEmitter — the one validated, redacted, sequenced publish path. Epic E21 (B1). |
| `control/errors.py` | Shared error for E21 Realtime Control Plane contracts. |
| `control/event_registry.py` | Event-type registry — the central catalog so modules can't invent event names. Epic E21 (S21.2). |
| `control/events.py` | RuntimeEvent envelope — the single shape every control-plane event uses. Epic E21 (S21.1/S21.7-info). |
| `control/permission.py` | Permission — the human-editable, per-agent capability profile. Epic E21 (S21.6). |
| `control/ports.py` | Ports for the Realtime Control Plane — the seams transport/storage sit behind. Epic E21. |
| `control/redaction.py` | Redactor — the secret-safety boundary before any payload reaches UI/SSE. Epic E21 (S21.7). |
| `control/replay.py` | EventReplayBuffer — the bounded event store the fake SSE layer streams + resyncs from. Epic E21 (S21.16). |
| `control/snapshot.py` | TaskLoopSnapshot read-model — the shape the UI Graph/Inspector render. Epic E21 (S21.9). |

## core/

| module | mục đích |
|---|---|
| `core/bootstrap.py` | Build a kernel and install features + middleware from config. Epic E01/E06. |
| `core/events.py` | Thread-safe subscriber registry with detached event delivery. |
| `core/kernel.py` | Shared, frozen capability runtime; per-run state and lifecycle live in KernelSession. |
| `core/middleware.py` | ToolMiddleware protocol — pre/post hook around execute_tool. Epic E01/E06. |
| `core/ports.py` | ToolPort protocol — the seam every concrete tool implements. Epic E01. |
| `core/registry.py` | CapabilityRegistry + NullToolPort — resolve a tool name to an executor, with graceful fallback. Epic E01. |
| `core/schemas.py` | Core data contracts: TaskEnvelope, ToolRequest, CapabilityResult envelope, FeatureDescriptor. Epic E01. |
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
| `discipline/budget.py` | Loop budgets — steps, parse-errors, same-tool repeats (parse errors do not consume steps). Epic E02. |
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
| `middleware/retry.py` | Retry — re-invoke the inner handler on a non-ok result. Epic E06 / E10 S10.13. |
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

## rag/

| module | mục đích |
|---|---|
| `rag/chunking.py` | Document collection + chunking. Epic E08. |
| `rag/embedders.py` | Embedder adapters. Epic E08. |
| `rag/feature.py` | RAG feature — register rag_health/rag_ingest/rag_search behind the chokepoint. Epic E08. |
| `rag/ports.py` | RAG ports + value types — the seam between logic and infra. Epic E08. |
| `rag/service.py` | RagService — health-gated ingest/search logic over the ports. Epic E08. |
| `rag/stores.py` | Vector store adapters. Epic E08. |
| `rag/stores_qdrant.py` | Qdrant vector store adapter (production). Epic E08, Slice S2. |

## roles/

| module | mục đích |
|---|---|
| `roles/agent.py` | Agent — a role bound to its skills/lenses, enforcing its allowlist. Epic E09. |
| `roles/lenses.py` | Lenses — review viewpoints rendered into an agent's prompt. Epic E09. |
| `roles/registry.py` | AgentRegistry — one role store shared by single- and multi-agent paths. Epic E09. |
| `roles/spec.py` | RoleSpec (canonical) + RoleView (E10 projection) + role loader. Epic E09. |

## safety/

| module | mục đích |
|---|---|
| `safety/policy.py` | Safety chokepoint — policy check + SafeToolPort wrapper applied to every toolbox tool. Epic E06. |
| `safety/sandbox.py` | Workspace path-jail — resolve a path and ensure it stays inside the workspace. Epic E06. |

## skills/

| module | mục đích |
|---|---|
| `skills/registry.py` | SkillRegistry — load skills and render them with progressive disclosure. Epic E07. |
| `skills/spec.py` | SkillSpec + SKILL.md parser. Epic E07. |

## supervisor/

| module | mục đích |
|---|---|
| `supervisor/broker.py` | Context Broker — writes a just-enough briefing per worker turn. Epic E10. |
| `supervisor/checkpoint.py` | SQLite checkpoint for the TaskLoop Blackboard — the truth for resume. Epic E10 S10.10. |
| `supervisor/contracts.py` | Supervisor data contracts — Agent O decisions + Context Broker packet. Epic E10. |
| `supervisor/evidence.py` | Evidence classification for the acceptance gate. Epic E10/E21 (S21.33). |
| `supervisor/graph.py` | Supervisor nodes — compose_team / o_decide / run_round / judge / tool. Epic E10. |
| `supervisor/llm.py` | LLM-backed Agent O + Context Broker (E10 Slice S2). |
| `supervisor/loop.py` | run_task_loop — the public Agent-O TaskLoop facade. Epic E10. |
| `supervisor/orchestrator.py` | Agent O — the orchestrator/judge. Epic E10. |
| `supervisor/state.py` | TaskLoopState — the serializable Blackboard for one multi-agent run. Epic E10. |

## tests_audit/

| module | mục đích |
|---|---|
| `tests_audit/conftest.py` | Shared deterministic fixtures for the strict audit suite. |
| `tests_audit/test_acceptance_evidence_adversarial.py` | Adversarial matrix for evidence-typed acceptance + AC report. Epic E10/E21 (S21.33). |
| `tests_audit/test_cli_and_tooling_entrypoints.py` | Executable entrypoints and repository-tooling tests. |
| `tests_audit/test_contract_roundtrips.py` | Property tests for every persisted/public data contract. |
| `tests_audit/test_core_edges_rigor.py` | Edge/boundary rigor for the core runtime: middleware protocol, session lifecycle |
| `tests_audit/test_delegation_bootstrap_rigor.py` | Adversarial rigor for delegation bootstrap/manager/policy/registry/store seams. |
| `tests_audit/test_discipline_and_rag_properties.py` | Property/fuzz tests for parsers, budgets, condensation, chunking and vector math. |
| `tests_audit/test_graph_resume_matrix.py` | Graph transition, failure and crash/resume matrix. |
| `tests_audit/test_json_repair_properties.py` | Property tests for the JSON repair pipeline: superset-of-valid + mangle round-trips. Epic E02. |
| `tests_audit/test_kernel_registry_adversarial.py` | Adversarial kernel, registry, feature-loader and event-bus contract tests. |
| `tests_audit/test_llm_features_rigor.py` | Strict audit of the LLM adapter + feature plugins: lazy client, JSON-mode request shape, retry/backoff classification, and the loader/echo/llm_chat plugin contracts. |
| `tests_audit/test_middleware_exact_semantics.py` | Exact callback, ordering and retry semantics for every middleware. |
| `tests_audit/test_middleware_safety_graph_rigor.py` | Rigor for middleware/safety/graph/gen_map: pin pass-through branches, jail escapes, node fail-routes, and the MAP generator. |
| `tests_audit/test_observability_durability.py` | Durability, concurrency, metric mapping and inspection CLI tests. |
| `tests_audit/test_observability_inspect_rigor.py` | Adversarial rigor for the inspect CLI + EventLogger durability — empty/missing/malformed run dirs, arg-parsing errors, and the run_id path-traversal guard. |
| `tests_audit/test_orchestrator_loop_rigor.py` | Rigor for orchestrator.loop + orchestrator.checkpoint: run/resume facade, projection, error branches. |
| `tests_audit/test_rag_edges_rigor.py` | Rigorous edge/error coverage for the rag package — the lines the focused suite leaves cold. |
| `tests_audit/test_rag_qdrant_adapter_contract.py` | Offline, exhaustive contract tests for the production Qdrant adapter. |
| `tests_audit/test_roles_rigor.py` | Rigorous audit of roles/ — lens/spec parsing, allowlist enforcement, registry as the single store, round-trip invariants. |
| `tests_audit/test_roles_skills_config_integrity.py` | Strict parser, registry and bundled-config integrity checks for roles/skills. |
| `tests_audit/test_security_boundaries.py` | Adversarial checks for every local I/O and process-execution boundary. |
| `tests_audit/test_session_delegation_state_machine.py` | Lifecycle, scope, ordering and idempotency checks for sessions/delegation. |
| `tests_audit/test_supervisor_adversarial_matrix.py` | Adversarial schema and authority checks for the multi-agent supervisor. |
| `tests_audit/test_toolbox_sandbox_rigor.py` | Rigor for the sandboxed toolbox: fs jail escapes, no-shell argv exec, timeout kill, policy gate. |
| `tests_audit/test_ui_http_and_frontend_contract.py` | Black-box HTTP API and static frontend contract tests. |
| `tests_audit/test_ui_server_http_rigor.py` | Adversarial/rigor coverage for the OLD observability HTTP server (ui/server.py, ui/__main__.py). |

## toolbox/

| module | mục đích |
|---|---|
| `toolbox/code_index.py` | Read-only code index — symbols, references, imports, dependency graph. Epic E06. |
| `toolbox/feature.py` | Tool feature — register sandboxed fs + terminal + code-intelligence tools, each behind the safety chokepoint. Epic E06. |
| `toolbox/filesystem.py` | Workspace-sandboxed filesystem tools: fs_read, fs_write, fs_list + surgical editors. Epic E06. |
| `toolbox/lint_test.py` | Structured validation tools — compile / ruff / pytest, no arbitrary shell. Epic E06. |
| `toolbox/terminal.py` | Terminal tool — run an argv (no shell) inside the workspace with a timeout. Policy gates danger. Epic E06. |

## ui/

| module | mục đích |
|---|---|
| `ui/__main__.py` | (thiếu module docstring — thêm 1 dòng + epic) |
| `ui/server.py` | Local HTTP/SSE server for the core_agent observability console. |

## (root)

| file | mục đích |
|---|---|
| `read_file_and_list.py` | (thiếu module docstring — thêm 1 dòng + epic) |
| `run_smoke.py` | Deterministic Sprint 0 smoke — no LLM, no network. Prints CORE_AGENT_SMOKE_OK on success. |

