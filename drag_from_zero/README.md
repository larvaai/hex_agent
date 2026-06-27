# drag_from_zero

A dynamically composable multi-agent runtime. Drag-drop produces the initial
*roster*; the real topology changes while it runs. This repo is **Slice 1**: the
smallest real closed loop that touches the whole architecture, running on a
deterministic `FakeLLM` so the harness is testable.

## The one idea: two graphs, never merged

| | Đồ thị 1 — Topology | Đồ thị 2 — Execution tree |
|---|---|---|
| when | design-time | run-time |
| nature | static, authored (drag-drop) | emergent, orchestrator-grown |
| node | Agent / Tool / Router / Memory / Hook | a task instance + live state |
| edge | routing / subscription rules | delegation / parent-child |
| is | **config** | **a projection of the event log** |

The **orchestrator** is the bridge. The **event log is the single source of
truth**; the execution tree (and any UI) is a pure projection of it
(`read_model.reduce`). The eventual React Flow UI is just another consumer of
the same event stream — the API boundary is fixed now, the UI is deferred.

## How the six requirements map

- **drag-drop** → author the topology (roster + routing). *(UI deferred; roster is JSON/code in Slice 1.)*
- **add an agent mid-session** → `orchestrator.join_agent()` → `agent_joined` event → it becomes routable.
- **observe everything** → the live view is `reduce(events)`, not a second state.
- **no hard-coded policy** → `HookRegistry` / `RuleRegistry` / `ToolRegistry` / `Budget` are empty/disabled by default (gates, not rules).
- **rules / tools / hooks / budget added by hand** → register them at runtime.
- **delegate or solo** → every plan step emits a first-class `DelegationDecision`; delegating grows a child node in the tree.

## Run it

```bash
python demo.py        # one scenario: event log + rendered execution tree
python -m pytest -q   # harness invariants on FakeLLM
```

## What the tests pin (and what they don't)

`tests/test_invariants.py` covers **harness invariants** on a deterministic
FakeLLM — delegation emits events and grows the tree, the view is a pure
projection, budget halts when registered, hooks can block, empty registries pass
through, mid-session injection works. They deliberately do **not** judge answer
quality — that is semantic **eval** (non-deterministic, scored), a separate later
slice and where real token burn lives.

## Deferred on purpose

Async work-queue execution (Slice 1 is synchronous + depth-first for
determinism), the real local LLM behind `LLM.complete()` (llama.cpp / LM Studio,
Slice 2), tool sandboxing, the eval harness, and the React Flow drag-drop UI.
Build the truth (runtime + event model) first; the view is a consumer.

## Slice 2 — real local LLM behind the port

`dragzero.llm.LLM` is the port; `FakeLLM` was one adapter. Slice 2 adds a second,
`dragzero/adapters/llm_local.py`, with **zero changes to the core or the Slice 1
tests** — proof that the seam is real (run `python -m pytest tests/test_invariants.py`,
still 8/8).

- `OpenAICompatLLM` — hits any OpenAI-compatible endpoint (LM Studio / llama.cpp),
  stdlib `urllib`, no deps. Extracts JSON from fenced/prose replies, makes one
  stricter **repair** call on bad output, and falls back to a safe `solo`
  decision (observable via `_meta`) instead of crashing.
- `RecordedLLM` — replays canned replies through the *same* parse/repair path, so
  the full orchestration loop is tested deterministically without weights.

```bash
python -m pytest tests/test_slice2_adapter.py -q   # adapter: parse, repair, substitutability
python run_local.py --task "Fix parse_config and add a test"   # real weights (LM Studio running)
```

`run_local.py` is the token-burn entrypoint: same harness, real model, swap the
adapter and nothing else. Point it at your server with `OPENAI_BASE_URL` / `MODEL`.

## Slice 3a — pausable work-queue + true mid-run injection

Slice 1 ran the tree by synchronous recursion, so an agent could only join
*between* runs. The orchestrator is now a deterministic FIFO **work queue**:

- `start()` enqueues the root; `run_until_idle()` drains the queue and **pauses**
  when a delegation targets a role nobody fills (the subtask parks in `waiting`,
  emitting `task_waiting` instead of mis-routing).
- `join_agent()` mid-pause wakes the parked task and `run_until_idle()` resumes —
  the injected agent answers the work. This is the real "add an agent mid-session
  to answer" requirement, not a between-runs approximation.

`run()` is still `start()` + `run_until_idle()`, so all 16 earlier invariants are
unchanged (run `python -m pytest tests/test_invariants.py tests/test_slice2_adapter.py`).

```bash
python -m pytest tests/test_slice3_workqueue.py -q   # pause -> inject -> resume
```

The event trace tells the whole story — `task_waiting`, then `agent_joined`
between the pause and the resume, then the child runs under the new agent.

## Slice 3b — eval harness (scored, not pass/fail)

Invariant tests pin the *harness*; eval scores *semantic behaviour* — "did the
planner delegate to the right role?" — over many trials and aggregates into a
report (pass-rate, mean, variance). It lives in `dragzero/eval/` and consumes the
core; the core never imports it.

- A `Scenario` = task + available roles + a rubric of **scorers**
  (`expects_delegation_to`, `expects_solo`, `reached_role`, `completed`,
  `max_plan_calls`, `no_fallback`, and an optional `llm_judge`). The harness ships
  the gauges; you compose the rubric — same empty-by-default philosophy.
- Scorers read the **event log + tree** only, so the same projection the live view
  shows is what gets graded.
- The eval machinery itself is tested deterministically (score known FakeLLM
  behaviours; assert good ≠ bad), so non-determinism is quarantined to real runs.

```bash
python run_eval.py                    # deterministic demo report
python run_eval.py --real --trials 5  # score your local model (token burn)
python -m pytest tests/test_slice3b_eval.py -q
```

A model that over-delegates a trivial question fails `solves_solo`; one that never
delegates a coding task fails `delegates_to:coder`. That is the signal you read
instead of traces.

## Slice 4 — tool execution + sandbox

Agents now *do* work, not just route it. Each task runs a bounded **ReAct loop**:
the agent may emit a tool action — `{"action": {"type": "tool", "tool": ...,
"args": ...}}` — which the orchestrator runs and feeds back as an observation,
until the agent returns a terminal decision. **Tool calls are first-class
events** (`tool_called` / `tool_result`), so the projection and eval see them.

- `dragzero/tools.py` is the port (`ToolResult`, `Tool`); `dragzero/adapters/tools_fs.py`
  is the side-effecting adapter: `FsSandbox` confines every path to a root (`..`
  escapes raise `SandboxError`), with `read_file` / `write_file` / `list_dir` and
  an opt-in `run_command`.
- Tools are **empty by default** — register them and pass a `sandbox` to enable.
  Unknown tool, missing sandbox, or path escape become observable failed
  `tool_result`s, never crashes. A `max_tool_steps` guard stops runaway loops.
- With no tools the loop runs once and the event stream is byte-identical to
  Slice 1 — every earlier invariant still holds (38 tests total).

```bash
python -m pytest tests/test_slice4_tools.py -q
python run_local.py --sandbox ./work --task "Add a test for parse_config"   # real model does real edits
```

Eval gained `used_tool` / `tool_succeeded`, so you can score whether the agent
actually read the file or ran the tests — not just whether it claimed to.

## Slice 5 — topology loader (Đồ thị 1 as JSON)

The design-time graph is now declarative, serialisable config — the API boundary
the React Flow UI will read and write. `dragzero/topology.py` is pure data
(node palette `agent`/`tool`/`router`/`memory`/`hook` + edges + budget); it
round-trips to/from JSON and validates structure. `dragzero/wiring.build_runtime`
turns it into a runnable `Orchestrator`:

- agent nodes → the roster; tool/hook/router nodes wire the registries from named
  **catalogs** (`default_tool_catalog`, `BUILTIN_HOOKS`, `BUILTIN_RULES`); the
  budget node sets the gate. Unknown capability names raise `TopologyError`.
- the LLM is *not* in the topology — `build_runtime(topology, llm)` injects it, so
  the same JSON runs on FakeLLM or a local model.
- router rules have teeth: a `by_keyword` router sends matching tasks to a role
  (a `deploy` task → `devops`), else routing falls back to the entry agent.

```bash
python -m pytest tests/test_slice5_topology.py -q
```

See `examples/topology.json` for a full graph. Edges are validated wiring the UI
draws; per-agent *enforcement* of tool/delegation permissions is a later slice.
Build the truth first — the drag-drop UI is now just a producer/consumer of this
JSON plus the event stream.

## Slice 6a — HTTP/WS server for the Agent-IDE UI

`dragzero/server.py` serves the `ui/` Agent-IDE against the real runtime — pure
stdlib (`http.server` + a hand-rolled WebSocket), no FastAPI, and it only *reads*
the orchestrator's event log (core untouched). Two translation layers bridge our
model to what the UI expects:

- `build_graph` reshapes the execution tree (read-model) into the UI's
  `{root, nodes, edges}` (filling `goal, mu, done_when, depends_on, children,
  runtime`). `mu`/`done_when` are best-effort here — the verifier that fills them
  properly is Slice 6b.
- `translate_event` maps our events onto the UI's vocabulary
  (`activate / propose / decompose / verdict / block / run_end`).

A run executes on a background thread; frames are buffered and broadcast to WS
clients (replay on connect, then live), paced for visible animation.

```bash
python run_server.py            # FakeLLM demo, open http://127.0.0.1:8000
python run_server.py --real     # drive a local model (LM Studio / llama.cpp)
python -m pytest tests/test_slice6a_server.py -q
```

Verified end-to-end in a real browser: the UI boots from `/api/session`, **Run**
decomposes the tree live (`t1 → t2 → t3`), file chips open artifacts the agents
actually wrote into the sandbox, and the chat narrates translated verdicts —
"reduced — children done", "run finished · done · 21 steps". No console errors.

## Slice 6b — the code-owned verifier (no more stub)

`build_graph` used to fake the two fields the UI's whole thesis rests on: `mu` was
subtree size, `done_when` was "files the agent wrote", and `translate_event` reported
`passed: true` for *every* completed task. The verdict was the model's claim. That is
gone.

`dragzero/verifier.py` is now the **sole verdict authority** — vendored, stdlib-only:

- a `done_when` criterion is the typed triple `{check, params, artifact}` — a *question*
  the gate answers, never an answer. Any verdict-shaped key (`passed`/`status`/`score`/…)
  is rejected at construction. The worker can never write a verdict.
- a **closed** `CHECK_VOCAB` (unknown check → FAIL) and an **artifact assertion** that runs
  before every predicate: the file must exist, be non-empty, sit in the sandbox, and be
  **fresh** (mtime ≥ the run's activated_at). No-artifact = FAIL; a stale leftover can't
  pre-satisfy a gate.
- `mu` = `done_when_count`, summed over the subtree — a real well-ordered measure.

The verdict is re-derived **at the projection boundary**: when the model *claims* a node
complete, `build_graph` runs the gate over the sandbox and reports the code's PASS/FAIL —
which **overrides** the claim. Mark a task "done" without writing its artifact and the UI
reads `FAIL` / blocked. A node with no authored criteria is `unverified`, never a faked
pass. The orchestrator is untouched: this is all in `server.py` + `verifier.py`.

The run spec authors `done_when` keyed by node id, `"__root__"`, or agent role (see
`run_server.DONE_WHEN`). Change a check and the UI's verdict changes with it.

```bash
python -m pytest tests/test_slice6b_verifier.py -q   # gate walls + anti-cheat through build_graph
python run_server.py                                 # the UI now shows code verdicts: μ 6→4→2, verdict pass
```

Verified end-to-end in a browser: the tree decomposes live, each node closes with a
code-derived `verdict pass`, and feeding the tester a report with no coverage line flips
the tester **and** the root to FAIL while the model still reports every task complete.

## Gaps 1–3 — disk truth, worker-proposed decompose, capability

Three subsystems closing the design doc's open laws. Each is additive: a run that uses none of
them is byte-identical to Slice 6a. Designed by a parallel agent fan-out grounded in the proven
`decompose_agent/` engine, then adversarially attacked (invariants 1–5 probed; three holes found
and fixed with regression tests).

**Gap 1 — disk is the only truth.** `dragzero/ledger.py` is an append-only JSONL ledger:
`EventLog(ledger=…)` flushes every event durably (the write happens *before* memory is mutated,
so disk never falls behind RAM), and `EventLog.replay(ledger)` rebuilds — resume is
`reduce(replay(ledger).events())`, byte-identical to the live tree. The reader is
corruption-tolerant: a torn tail line (a crash half-write) is dropped, not fatal.

**Gap 2 — the worker PROPOSES, code ACCEPTS (decompose-until-trivial).** A task with authored
`done_when` runs the code-owned loop in the orchestrator: K leaf attempts (each a ReAct pass +
`run_checks` over the sandbox), and on persistent failure the worker is asked to propose children
— each a `{goal, done_when}` node. `dragzero/accept.py` (Gate-2, pure, pre-mutation) accepts only
a split where every child is **strictly smaller** (μ = `done_when_count`), the parent's criteria
are all **covered by implication**, and no child forges a verdict key. Children verify by code;
the parent closes by **compose** — and a failed child or a failing own-gate is `COMPOSE_FAIL`
(surfaced in the orchestrator *and* the ledger, not just the projection), never a silent DONE.
Termination is a theorem: μ-descent + a per-root step budget + `MAX_DEPTH` + identical-re-proposal
STUCK. Leaf-ness is discovered by exhausting K — never asked of the model.

**Gap 3 — capability token (ADR-1..4).** `dragzero/capability.py` is a frozen token threaded down
the spawn tree; `attenuate()` only narrows (a widen raises), `depth` decrements one per level. The
Gate reads the token, never the agent's words: a tool outside `capability.tools` is denied at the
single dispatch site; `depth`/`spawn_quota`/`can_delegate` are hard stops on both the delegate and
the decompose spawn paths, surfaced as `capability_exhausted`. Default `capability=None` is
permissive passthrough.

```bash
python -m pytest tests/test_disk_truth.py tests/test_decompose.py tests/test_capability.py -q
```

Live: `decompose_server.py` (a `--scenario`-style demo) drives a root whose 3-criterion gate the
worker can't satisfy alone — it decomposes into `impl-login · impl-session · write-tests`, μ
shrinks 6→1, every leaf closes on a code verdict, and the parent composes to PASS.
