# E07 — Stories (draft)

- **S07.1** — As an author, I write a skill with `Allowed (tools)` and `Forbidden (tools)` naming canonical MCP tools.
- **S07.2** — As the runtime, by default I inject only the skill contract (description + Allowed + Forbidden), not the full body.
- **S07.3** — As the runtime, when a skill is selected for the current step, I load its full Steps/Report.
- **S07.4** — As an operator, a role's tool allowlist can be derived from the union of its skills' declared tools.
- **S07.5** — As the loader, I reject a skill missing `name`/`description` frontmatter.
