# E09 — Stories (draft)

- **S09.1** — As an operator, I define a role in YAML (tools, routing, test-ownership, lenses) and the agent is built from it.
- **S09.2** — As a safety layer, an agent calling a tool outside its allowlist returns a blocker/handoff instead of executing.
- **S09.3** — As an operator, an invalid role config fails fast with a clear error.
- **S09.4** — As the runtime, a role with `owns_validation=false` must hand off to the test role; it cannot mark its own work validated.
- **S09.5** — As an agent, my prompt includes only my lens group, my allowed tools, and my allowed skills (contract mode).
- **S09.6** — As a developer, single-agent and multi-agent build agents from the same role definitions.
