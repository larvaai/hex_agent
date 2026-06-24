# E10 — Stories (v2)

- **S10.1 Team composition** — As Agent O, I select the *minimum* set of agents from the
  department registry for a task and record why, so a task uses no more agents than needed.
- **S10.2 Bounded dialogue loop** — As the supervisor, I run rounds where each round delegates
  to the selected agents and merges their output into the Blackboard, until a terminal decision.
- **S10.3 Scoped context packet** — As a worker agent, I receive only a curated Context Packet
  (objective + relevant context + narrowed capability scope + expected output schema), never the
  full transcript.
- **S10.4 Context Broker agent** — As the Context Broker agent, I read the next agent's objective +
  scope of work, then write a just-enough briefing **from the store slice I am given** (not from
  memory), attaching the `source_ids` I used; the packet is logged as an artifact.
- **S10.5 Worker turn = delegation** — As the supervisor, I run each agent turn as an isolated
  child session via `DelegationManager` (scope ⊆ parent, depth-guarded), capturing the result as
  an `ArtifactEnvelope`.
- **S10.6 Acceptance gate** — As Agent O, I reach `finished` only when every acceptance criterion
  is `passed` and has evidence; otherwise I continue, request a tool, block, or fail.
- **S10.7 Loop guard** — As the supervisor, I stop a run as `blocked/failed` when `max_rounds` is
  hit, when a round makes no progress, or when O repeats the same decision too many times.
- **S10.8 Structured O decision** — As the runtime, I require O to output one JSON decision; an
  invalid decision is repaired via the json-gate (E02), and persistent failure ends the loop.
- **S10.9 Tools via the kernel chokepoint** — As the runtime, O never calls a tool directly; a
  `need_tool` decision runs through `execute_tool` (policy + scope), and the result returns to the
  Blackboard as an artifact.
- **S10.10 Checkpoint / resume** — As the runtime, the Blackboard is serializable; a run can
  resume mid-loop from the SQLite checkpoint (the truth), not from the UI projection.
- **S10.11 Reuse the single-agent substrate** — As the runtime, a worker agent itself runs on the
  E05 single-agent graph (via the LangGraph delegation adapter); no second agent loop is written.
- **S10.12 Carried-over discipline** — As the runtime, within worker turns the existing
  separation-of-duties, repair-mode (patch-only after a failed test), and finish-gate still apply.
- **S10.13 Capability kind** — As the runtime, capabilities carry a `kind` (`model|read|effect`)
  and `idempotent` flag so retry/policy treat a side-effecting tool differently from a read/model.
- **S10.14 Broker cannot grant scope** — As the runtime, the Broker shapes only informational
  context; a worker's `allowed_capabilities` is set by O/policy, and nothing the Broker writes can
  widen it.
