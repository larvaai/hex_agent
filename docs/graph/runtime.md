# `graph/runtime.py`

`build_agent_graph(kernel, checkpointer)` constructs the sole agent runtime with LangGraph `StateGraph`:

```text
START -> guard -> agent
                  | tool -> tool -> guard
                  | final -> finish -> END / guard
                  | parse retry -> guard
                  | failure -> fail -> END
```

The compiled graph captures the runtime kernel in node callables while all persisted data remains in `AgentState`.

`run_agent(...)` remains as a compatibility facade for callers that inject a plain `llm_call`. It adapts that callable into the `llm.chat` capability and invokes the same compiled graph with an in-memory checkpointer; it is not a second loop.
