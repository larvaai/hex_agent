# E12 — Stories (draft)

- **S12.1** — As a user, I send any task and the supervisor routes it to the right graph/department.
- **S12.2** — As the router, I return a structured `RouteDecision` with intent, needs-flags, and steps.
- **S12.3** — As the router, when my confidence is low, I fall back to an LLM classifier instead of guessing.
- **S12.4** — As the supervisor, I run the safety gate before dispatching, and stop if blocked.
- **S12.5** — As the supervisor, for a mixed task I produce and execute a multi-step plan across departments.
- **S12.6** — As the supervisor, I synthesize a final answer merging department outputs, citations, and validation evidence.
