# E02 — Stories (draft)

- **S02.1** — As the runtime, I parse the model's action JSON and, if malformed, attempt deterministic repair before failing.
- **S02.2** — As the runtime, after N parse errors I stop the run with a clear classified error (without consuming the step budget per retry).
- **S02.3** — As the runtime, I condense large tool observations before re-feeding them to the model.
- **S02.4** — As the runtime, I block a `final` action when code changed but no validation passed, unless the model reports a blocker.
- **S02.5** — As the runtime, I stop when the same tool call repeats beyond `max_same_tool_calls`.
- **S02.6** — As a developer, the discipline module is imported by every orchestration path (no duplication).
