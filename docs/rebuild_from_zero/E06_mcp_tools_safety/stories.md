# E06 — Stories (draft)

- **S06.1** — As the runtime, I call a tool by alias or `server.tool` and get a normalized envelope.
- **S06.2** — As a safety layer, I reject any filesystem path outside the workspace.
- **S06.3** — As a safety layer, I hard-block git-mutating tools unless an explicit env opt-in is set for the run.
- **S06.4** — As a safety layer, the terminal tool accepts only `argv` (no shell string) and tags each result with a security risk.
- **S06.5** — As the runtime, validation and policy run BEFORE the server is invoked (fail cheap).
- **S06.6** — As the runtime, tool sessions are reused across calls instead of spawning a new process each time.
