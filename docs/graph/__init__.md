# `graph` package

Public exports:

- `build_agent_graph`: compile the runtime around an `AgentKernel` and optional checkpointer.
- `run_agent`: compatibility facade built on that compiled graph.
- `AgentState`: serializable graph-state contract.

Normal application callers should continue using `orchestrator.run` and `orchestrator.resume`, which provide durable SQLite persistence and stable lifecycle outcomes.
