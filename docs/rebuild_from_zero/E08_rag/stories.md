# E08 — Stories (draft)

- **S08.1** — As the runtime, I check `rag_health` before any ingest/search and stop with a dependency error if it fails.
- **S08.2** — As a user, I ingest workspace docs (`.md/.txt/.py`) into the vector store.
- **S08.3** — As the runtime, re-ingesting the same source replaces its old chunks (no duplicates).
- **S08.4** — As a user, I search and get hits above a score threshold, each with source + chunk index.
- **S08.5** — As a safety layer, ingest/search only touch paths inside the workspace.
