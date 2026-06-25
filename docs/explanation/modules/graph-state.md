# `graph/state.py`

> Code thật: `graph/state.py` · tóm tắt 1 dòng ở `../../../MAP.md`. Tài liệu này giải thích vai trò/invariant, KHÔNG nhúng full source (tránh rot — source là sự thật).

`AgentState` is the serializable `TypedDict` checkpointed by LangGraph. It owns task/run identity, messages, the complete `Budget` snapshot, last action, routing status, final outcome, and an encoded snapshot of `kernel.state`.

The module deliberately excludes runtime objects such as `AgentKernel`, LLM clients, loggers, and database connections. `encode_kernel_state`/`decode_kernel_state` preserve `TaskEnvelope` while keeping graph checkpoints portable.

`new_agent_state(...)` is the only initializer used by both the public orchestrator and the backward-compatible `graph.run_agent` facade.
