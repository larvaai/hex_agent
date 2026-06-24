# LangGraph runtime architecture

## Boundary

LangGraph owns orchestration only. `core/` has no LangGraph imports and remains the framework-agnostic microkernel. Every LLM and tool action crosses `AgentKernel.execute_tool`, preserving middleware, safety, capability envelopes, events, and trace IDs.

```mermaid
flowchart LR
    caller["UI / caller"] --> facade["orchestrator.run / resume"]
    facade --> graph["compiled StateGraph"]
    graph --> agent["agent node"]
    graph --> tool["tool node"]
    graph --> finish["finish / fail nodes"]
    agent --> kernel["AgentKernel.execute_tool"]
    tool --> kernel
    finish --> lifecycle["complete_task / fail_task"]
    graph --> sqlite[("langgraph.sqlite")]
```

## Topology

```text
START -> guard -> agent
                  | parse/unknown -> guard
                  | tool -> tool -> guard
                  | final -> finish -> END or guard
                  | failure -> fail -> END
```

`guard` enforces the step budget before an LLM call. `agent` records valid actions and parse retries. `tool` enforces the same-tool budget before executing through the kernel. `finish` applies the shared finish gate; only then does it close the kernel task lifecycle.

## State and persistence

`AgentState` is the authoritative orchestration state. It contains only serializable values: task/run identity, messages, discipline counters, last action, outcome, and an encoded snapshot of `kernel.state`. Runtime services are captured when compiling nodes and never enter a checkpoint.

Each run stores its durable LangGraph checkpoint at:

```text
var/agent_runs/<run_id>/langgraph.sqlite
```

The adjacent `checkpoint.json` is a UI projection updated after every graph state transition. Resume never reads that projection, except for a one-time migration of checkpoints created before LangGraph.

`run_id` maps to LangGraph `thread_id`; the kernel's `task_id` remains the correlation ID for lifecycle and tool events.
