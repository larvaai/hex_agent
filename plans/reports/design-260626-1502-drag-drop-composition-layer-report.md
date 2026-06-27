---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Design — drag-and-drop composition layer

> Goal: add **nodes, states, agents, departments** as pluggable puzzle pieces declared in **config files** — timeout/gate/hook set externally. Core stays a thin substrate; "generating a department" needs no Python.
>
> Method: 3 independent designs → adversarial critique each → synthesis (workflow `drag-drop-composition-design`, 7 agents). This report = the synthesized recommendation.

## Thesis

You already do config-driven composition **5 times**, all the same shape:

> **typed Spec (dataclass) + `parse_*(data, source)` gateway raising file+field errors + Registry with `assert_known` (reject-unknown) + load-from-YAML.**

| instance | spec | registry | file |
|---|---|---|---|
| features | `FeatureDescriptor` | `features/loader.py` | `config/features.yaml` |
| middleware | (inline) | `core/bootstrap._install_middleware` | `config/features.yaml` |
| roles/lenses | `RoleSpec` | `roles/registry.py` | `roles/library/*.yaml` |
| command-types | `CommandTypeSpec` | `control/command_registry.py` | `config/runtime_command_types.yaml` |
| event-types | — | `control/event_registry.py` | `config/runtime_event_types.yaml` |
| (decompose check-vocab) | `{check,params}` | `CHECK_VOCAB` (spec-only) | `tree.yaml` |

"Drag-and-drop" is **not a new system** — it's this one pattern extended to the three things still hardcoded, plus a **compiler** that lowers validated specs into the *existing* runtime. The kernel never learns the word "department".

## The gap (what's hardcoded today)

1. **The graph.** `graph/runtime.py:build_agent_graph()` bakes 6 nodes `{guard,agent,tool,delegate,finish,fail}` + every edge in Python. Add a node/state = edit Python.
2. **Departments.** Emergent from an LLM `supervisor/graph.py:compose_team` at runtime — never *declared* — even though `department:` is already a field on every `RoleSpec`. No `DepartmentSpec`.
3. **Per-piece gate/hook/timeout.** Wired in code (`_install_middleware` fixed set; `control/checkpoint` used ad hoc).

## Design — one idiom, two compile targets (deliberately NOT unified)

Shared library: **`graph/kinds.py:NodeKindRegistry`** — mirrors `CapabilityRegistry` exactly: `name -> factory(params, *, session, deps) -> callable(state)->patch`. Seeded with 6 builtin factories that just `partial()` today's `graph/nodes.py` fns; extended via the **`features.loader` `module:install`** pattern under a `config['graph_kinds']` block. A new node behavior = a new registered kind (a few lines of Python), exactly like a new tool executor.

- **(A) `GraphCompiler.compile(GraphSpec) -> langgraph.StateGraph`** — replaces the *body* of `build_agent_graph` (signature unchanged). The center of gravity; solves "add nodes/states tuỳ ý".
- **(B) `DepartmentCompiler.compile(DepartmentSpec) -> DepartmentPlan`** — a **frozen seed** for `supervisor/loop.py:_drive`, **NOT a graph**. Solves "sinh department". The supervisor stays a plain `while`-loop with zero department awareness; a department lowers to a pre-seeded `TaskLoopState` + a scope-narrowing delegation wrapper.

Why two targets: the supervisor is a Python loop, not a langgraph graph, and the decompose Navigator is a single-cursor DFS tree-walker — three different execution models. Forcing them through one `compile()` verb is unsound. They share only the **spec/registry idiom**, not an executor.

## Puzzle-piece catalog

| piece | spec shape | registry / mechanism | validated by (gateway) |
|---|---|---|---|
| **node (kind)** | `{id, kind, params?, hooks?}` | `NodeKindRegistry`; 6 builtins + `config['graph_kinds']` `module:install` | `kind in registry` else `ValueError "graph <file>: node <id>: unknown kind"` |
| **edge / router** | `node.edges: {route_value: target\|__end__}` | single `_route` fn (reads `state['route']`); route values are **code-derived patches, never LLM content** | every target is a declared node or `__end__`; route keys non-empty; entry exists |
| **state channel** | `{name, type, default}` | `graph/state.make_state_type` over closed vocab `{str,int,float,bool,list,dict}`; **LastValue reducer only** | type in vocab; name ∉ floor keys (`messages`/`budget`); no dup |
| **department** | `{name, department, members, scope, budget, acceptance, events}` | `departments/registry.py:DepartmentRegistry` (groups `RoleSpec` by `department:`) | each member exists ∧ `member.department==spec.department`; `scope ⊆ ∪ member.allowed_tools`; events in `EventTypeRegistry` |
| **hook** | `node.hooks: {before:[topic], after:[topic]}` | existing `EventTypeRegistry` + `EventEmitter` | every topic in `EventTypeRegistry` (add `graph.*` rows first) |
| **gate** *(P7, deferred)* | `node.gate: {risk_level, checkpoint_type, on_reject_route}` | **NEW** `config/runtime_checkpoint_types.yaml` + `CheckpointTypeRegistry` | `risk_level ∈ RISK_LEVELS`; type in registry; **async-resumable only, no blocking gate** |
| **timeout** *(P7, deferred)* | `node.timeout: {max_steps_sub_budget, on_timeout_route}` | reuses `discipline/Budget`; **no wall-clock** | route declared; sub-budget `min()`-clamped vs run Budget |

## Config layout (what a human edits)

```yaml
# config/graphs/default.graph.yaml — today's 6-node graph AS DATA (backward-compat baseline)
name: core-agent
entry: guard
channels: []
nodes:
  guard:    { kind: guard,    edges: { agent: agent, fail: fail } }
  agent:    { kind: agent,    edges: { tool: tool, delegate: delegate, finish: finish, guard: guard, fail: fail } }
  tool:     { kind: tool,     edges: { guard: guard, fail: fail } }
  delegate: { kind: delegate, edges: { guard: guard, fail: fail } }
  finish:   { kind: finish,   edges: { guard: guard, end: __end__ } }
  fail:     { kind: fail,     edges: { end: __end__ } }
```

```yaml
# config/graphs/review_with_hook.graph.yaml — drag-and-drop proof: custom kind + new channel + hook, ZERO compiler edits
name: code-with-review
entry: guard
channels:
  - { name: review_verdict, type: str, default: null }
nodes:
  guard:  { kind: guard,  edges: { agent: agent, fail: fail } }
  agent:  { kind: agent,  edges: { tool: tool, finish: finish, guard: guard, fail: fail } }
  tool:
    kind: tool
    hooks: { before: [graph.step], after: [graph.tool_done] }   # both MUST be registered
    edges: { guard: guard, fail: fail }
  finish: { kind: finish, edges: { guard: guard, end: __end__ } }
  fail:   { kind: fail,   edges: { end: __end__ } }
```

```yaml
# departments/library/engineering.yaml — declared team; lowers to a TaskLoopState SEED, not a graph
name: engineering
department: engineering
members: "*"                              # or [code, test, reviewer] (all already department: engineering)
scope: [fs_read, fs_write, fs_list]       # subset of union(member.allowed_tools)
budget: { max_rounds: 6, max_decision_repeats: 3 }   # min()-clamped vs run_task_loop defaults
acceptance:
  - { id: ac_tests_green, text: "owned tests pass; evidence = a test_result artifact" }
  - { id: ac_reviewed,    text: "a reviewer turn approved; evidence = a review_decision artifact" }
events: [loop.team_composed]
```

```yaml
# config/runtime_event_types.yaml — additive rows so node hooks emit through the validated EventEmitter
graph_topics:
  graph.step:           { visibility: ui_safe, durable: true }
  graph.tool_done:      { visibility: ui_safe, durable: true }
  graph.budget_blocked: { visibility: ui_safe, durable: true }
  graph.completed:      { visibility: ui_safe, durable: true }
```

```yaml
# config/features.yaml — additive: register custom node kinds via the existing plugin pattern
graph_kinds:
  review: { enabled: true, module: graph_kinds.review }   # exposes install(node_kind_registry)
```

## Core changes

| file | LOC | change |
|---|---|---|
| `graph/kinds.py` *(new)* | ~70 | `NodeKindRegistry` (register/resolve/assert_known); 6 builtin factories `partial()` `graph/nodes.py`; `config['graph_kinds']` via `importlib` `module:install` |
| `graph/spec.py` *(new)* | ~180 | `GraphSpec/NodeSpec/ChannelSpec` + `parse_graph_spec` (full gateway validation incl. convergence cycle check) + `DEFAULT_GRAPH_SPEC` literal |
| `graph/compiler.py` *(new)* | ~120 | `compile_graph(spec,*,session,deps,checkpointer)`; resolve kinds, wrap (hooks only in v1), `add_conditional_edges` from edge maps, derive `recursion_limit` from compiled topology |
| `graph/decorators.py` *(new)* | ~40 | `hook_decorator` (v1); `gate_decorator`/`timeout_decorator` land later, separately justified |
| `graph/state.py` | ~35 | `make_state_type(channels)` → `AgentState` when empty, else TypedDict subclass; reject floor-key collision/dup |
| `graph/runtime.py` | ~15 | `build_agent_graph` body → `compile_graph(load_graph_spec('default'), ...)`; signature unchanged; add optional `graph_name='default'` |
| `orchestrator/loop.py` | ~10 | move `recursion_limit` formula into `compile_graph` (from compiled topology) |
| `config/runtime_event_types.yaml` | ~6 | add `graph.*` topic rows |
| `departments/{spec,registry,instantiate}.py` *(new)* | ~220 | `DepartmentSpec` + `parse_department` (copy `parse_role`) + `DepartmentRegistry` + `instantiate_department` (seed `TaskLoopState` + scope-narrowing delegation wrapper); +1 additive kwarg `department_plan=None` on `run_task_loop` |

## Convergence & authority (the load-bearing invariants)

- **Termination is proven at COMPILE time.** `parse_graph_spec` DFS's the route-map graph and rejects any cycle/back-edge that does **not** traverse a budget-charging kind (one that calls `Budget.record_step`, i.e. `agent`). An unbounded config-declared loop never reaches runtime. This is the config-graph analogue of the decompose spec's well-founded-measure law.
- **The LLM gets no control-flow authority.** Route values fed to langgraph conditional edges are **always** code-derived node-return patches, never LLM content. `params` are plain data to a Python factory — there is **no params mini-language**.
- **Config may only TIGHTEN bounds** via `min()`, never raise or disable a guard. Department scope intersects with `DelegationPolicyEngine.validate` (`delegation/policy.py`), which stays the sole authority on `scope ⊆ parent`.
- **Kernel stays thin.** Hooks are compiler-applied node-wrapper *decorators* (per-compile, per-session), **never `kernel.use()`** — `kernel.use` is kernel-lifetime/shared and raises after `freeze()`, so routing per-graph hooks through it would break the freeze model or leak across runs.

## Backward-compat

Absent/empty config ⇒ **byte-identical** behavior. (a) No `config/graphs` dir → `DEFAULT_GRAPH_SPEC` literal (mirrors `load_config` → `{features:{}}`). (b) `build_agent_graph` keeps its signature; `run_agent`, run/resume, checkpointers, `adapters/agents/langgraph_agent.py` untouched; same `StateGraph(AgentState)` + same node names ⇒ existing SQLite checkpoints resume. (c) Empty channels ⇒ `AgentState` unchanged; no hooks ⇒ identity decorator ⇒ zero overhead; **v1 ships no gate/timeout** ⇒ no new pause path. (d) Departments additive: `run_task_loop(department_plan=None)` runs today's emergent `compose_team` path exactly. **Canary:** full `tests/` + `tests_audit/` + a NEW golden topology test asserting the compiled default == the hand-written graph.

## Phased build order (vertical-slice-first)

| phase | deliverable | proves |
|---|---|---|
| **P0** | golden test snapshotting today's `build_agent_graph` node-set + edge maps | objective "topologically identical" oracle — land it **before** touching `runtime.py` |
| **P1** | `graph/spec.py` + `graph/kinds.py` (+ convergence cycle check) | validated-spec + reject-unknown half, with termination proof at compile time |
| **P2** | `graph/compiler.py` (no-decorator path) + rewrite `build_agent_graph`; run full suite + P0 | **load-bearing slice** — real run drives a compiled graph identical to today. STOP, confirm green, before any new piece |
| **P3** | `config/graphs/default.graph.yaml` + file-first/literal-fallback load | adding/rewiring nodes is now a YAML edit |
| **P4** | `make_state_type` + channel test through checkpoint round-trip | "add a state" is a YAML line; reducer footgun closed by LastValue-only + collision rejection |
| **P5** | `hook_decorator` + `graph.*` rows + 1 e2e | per-node hook attaches declaratively through the validated emitter |
| **P6** | `departments/{spec,registry,instantiate}.py` + `engineering.yaml` + `run_task_loop(department_plan=)` | "add a department" is one YAML file; scope composes safely with unchanged `DelegationPolicyEngine` |
| **P7** *(optional, separately justified)* | async-resumable `gate_decorator` + `CheckpointTypeRegistry` + step-sub-budget timeout + 1 custom kind | full drag-and-drop incl. human gate — only after the resumable pause/re-entry seam is designed |

## Deliberately rejected (YAGNI fence)

- **Synchronous in-process approval gate** (all 3 designs assumed one) — contradicts the event-sourced control plane (`control/ports.py` exposes only `EventSinkPort`; no blocking `approve()`). Gates are async-resumable only, deferred to P7.
- **A `Department.graph` driving a team** — the supervisor is a `while`-loop, not a graph; `langgraph_agent.py:45` hardcodes `build_agent_graph` with no graph param. Department lowers to a **seed**, not a graph.
- **department == decompose-subtree unification** — different executors; share only the idiom.
- **Reusing decompose `CHECK_VOCAB`/`accept_decomposition`/`mu` verbatim** — none of it exists in code (spec-only); building a convergence engine is net-new safety-critical work, out of scope. v1's proof = `Budget` step count + the compile-time cycle check.
- **Non-LastValue channel reducers / `CHANNEL_VOCAB`** — `AgentState` uses zero reducers; an `append_list` on `messages` double-appends. LastValue-only.
- **Wall-clock per-node timeout** — non-serializable across the checkpoint boundary, indistinguishable from a clean fail on resume. Step-sub-budget only.
- **`DepartmentSpec.defaults` cascade, topology enum, `department_types.yaml`, `OrchestratorPort.compose_department` (LLM emits a whole spec)** — no consumer; path-b widens LLM authority over the safety envelope.
- **Per-node decorator-order knob** — fix one canonical order (hook innermost in v1; timeout outermost when it lands), assert in a test.

## Open questions

- **Resumable-gate re-entry (P7):** `orchestrator/loop.resume()` only continues `running` checkpoints with `snapshot.next`; a node parked on a `waiting` `RuntimeCheckpoint` isn't modeled. Where is the pending checkpoint id persisted (`AgentState` channel? `TaskLoopState` field?) so it survives the SQLite round-trip, and what's the `expired` path so a parked gate can't wait forever?
- **`recursion_limit` derivation:** confirm "longest acyclic path between budget-charging nodes" matches langgraph superstep accounting once hook/gate wrappers exist (do wrapped handlers count as extra supersteps?).
- **Builtin `graph.*` emissions** are raw `kernel.events.publish` (registry-bypassing) today. Migrate onto the validated `EventEmitter` for consistency, or keep raw to guarantee zero drift? v1 keeps raw — confirm observability projections don't assume otherwise.
- **Delegated-worker graph selection:** if a department wants workers on a non-default graph, `langgraph_agent.py` must thread `graph_name` through `DelegationRequest`. Out of scope for v1 (workers run default) — confirm no department needs it first.
- **`DepartmentRegistry` must receive the SAME `agent_registry` that validated the spec** at instantiate time (`run_task_loop`'s is currently `Optional/None`). Make it required on the department path to close the `compose_team` catalog-validation bypass?
