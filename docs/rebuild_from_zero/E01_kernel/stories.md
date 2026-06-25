# E01 — Stories (draft)

- **S01.1** — As the runtime, I execute a registered tool through the kernel and get a `CapabilityResult` envelope.
- **S01.2** — As the runtime, when I request an unregistered tool, I get a structured `ok=false / missing_capability` result instead of a crash.
- **S01.3** — As an operator, I disable a feature in `features.yaml` and its tools become unavailable while the kernel still boots.
- **S01.4** — As an operator, an enabled feature is auto-installed at bootstrap and registers its capabilities.
- **S01.5** — As a debugger, the kernel emits events (`task.accepted`, `tool.requested`, `tool.completed|failed`) for every action.
- **S01.6** — As a developer, every tool result is normalized to the same envelope shape regardless of the raw tool output.
