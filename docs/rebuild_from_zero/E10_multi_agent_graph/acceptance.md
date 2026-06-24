# E10 — Acceptance Criteria (v2)

> Given/When/Then, map 1–1 với stories S10.x để chuyển thẳng sang test (E19).

## S10.1 team composition
- Given a task and an agent registry of N agents, When Agent O composes the team, Then it emits a
  `SessionPlan` artifact listing the selected agents **with a reason each**, and selects fewer than
  N when the task does not need all of them.

## S10.2 bounded dialogue loop
- Given a composed team, When the supervisor runs a round, Then each selected agent is delegated
  exactly once that round and its output is appended to the Blackboard before the next `o_decide`.

## S10.3 scoped context packet
- Given a worker agent turn, When the agent runs, Then its child session contains only the Context
  Packet (objective + curated context + scoped capabilities), And the parent's full message
  transcript is **not** present in the child session state.

## S10.4 context broker agent
- Given a worker assignment (objective + scope of work) and a store slice supplied as input, When
  the Broker agent writes the Context Packet, Then the packet carries `source_ids` pointing to real
  artifact/turn ids in that input, And the packet is recorded as an artifact on the Blackboard, And
  it stays within the configured token budget.

## S10.5 worker turn = delegation
- Given a worker turn, When it executes, Then it runs through `DelegationManager.delegate` with a
  child scope that is a subset of the parent scope, And the result is returned as a
  `DelegationResult` carrying `ArtifactEnvelope`(s).

## S10.6 acceptance gate
- Given at least one acceptance criterion without evidence, When O evaluates the round, Then the
  decision is **not** `finished`; And `finished` is only reachable when every criterion has status
  `passed` with a non-empty `evidence` list.

## S10.7 loop guard
- Given a round that produces no new artifact and no change in any acceptance status, When the next
  `o_decide` runs, Then the run is routed to `blocked` or `failed` (not `continue`); And reaching
  `max_rounds` always terminates the loop.

## S10.8 structured O decision
- Given Agent O returns malformed JSON, When the supervisor parses it, Then the json-gate repairs
  or re-prompts (E02); And exceeding the parse-error budget ends the loop as `failed`.

## S10.9 tools via the kernel chokepoint
- Given a `need_tool` decision, When the tool runs, Then it crosses `AgentKernel.execute_tool`
  (emitting `tool.requested`/`tool.completed` with lineage) and its envelope is stored on the
  Blackboard as an artifact — O never invokes an executor directly.

## S10.10 checkpoint / resume
- Given a loop interrupted mid-round, When `resume(run_id)` is called, Then it restores the
  Blackboard from the SQLite checkpoint and continues from the next pending node, without
  re-running a completed worker turn.

## S10.11 reuse the single-agent substrate
- Given a worker agent, When it executes a turn, Then it runs on the E05 single-agent graph via the
  LangGraph delegation adapter (verified structurally), not a bespoke loop.

## S10.12 carried-over discipline
- Given a worker turn that changed code without passing validation, When that turn tries to finish,
  Then the finish-gate blocks it; And a whole-file rewrite attempt in repair-mode is blocked with
  `policy_code=repair_requires_patch_tool`.

## S10.13 capability kind
- Given a capability registered with `kind="effect"` and `idempotent=False`, When it returns a
  non-ok result under the retry middleware, Then it is **not** retried; And a `kind="read"`/
  `idempotent=True` capability may be retried within its attempt budget.

## S10.14 broker cannot grant scope
- Given an O assignment that sets a worker's `allowed_capabilities` to `{fs_read}`, When the Broker
  produces a packet that mentions or requests other capabilities, Then the worker's child session
  scope is still exactly `{fs_read}` — the Broker's output cannot widen it.
