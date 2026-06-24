# `graph/nodes.py`

The compiled graph has five nodes:

- `guard`: blocks before an LLM call when the step budget is exhausted.
- `agent`: calls `llm.chat` through `AgentKernel.execute_tool`, parses the JSON action, and records parse/step counters.
- `tool`: enforces the same-tool budget, executes through the kernel, and appends the capability envelope to messages.
- `finish`: applies the shared finish gate and calls `kernel.complete_task` once allowed.
- `fail`: closes the lifecycle through `kernel.fail_task`.

Every node restores the checkpointed kernel snapshot before work and returns the updated snapshot afterward. This makes a newly constructed kernel safe to use during `resume()` without putting the kernel object into graph state.
