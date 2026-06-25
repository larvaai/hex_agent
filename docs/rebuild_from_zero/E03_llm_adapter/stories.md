# E03 — Stories (draft)

- **S03.1** — As the runtime, I call the LLM with `response_format=json_object` so the model cannot return non-JSON for action steps.
- **S03.2** — As a developer, importing the adapter module does not open any network client (lazy init).
- **S03.3** — As the runtime, an LLM timeout/error is returned as a structured message, not an unhandled exception.
- **S03.4** — As an operator, I override base URL / model / key via env or call args.
- **S03.5** — As the runtime, I can request a grammar-constrained output when the backend supports it.
