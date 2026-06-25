# E05 — Stories (draft)

- **S05.1** — As a user, I run `run_single("<task>")` and the agent loops tool→observe until it returns a final answer.
- **S05.2** — As the runtime, the agent node produces an action via the LLM adapter and the discipline gate.
- **S05.3** — As the runtime, `route_next` sends to the tool node on `action=tool` and ends on `action=final`.
- **S05.4** — As the runtime, tool observations are condensed and appended before the next agent step.
- **S05.5** — As a developer, the same node/loop code is reused by the multi-agent graph (E10) without a second implementation.
