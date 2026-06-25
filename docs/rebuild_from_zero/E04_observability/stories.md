# E04 — Stories (draft)

- **S04.1** — As a debugger, every run writes `events.jsonl` with ordered Message/Action/Observation/State events.
- **S04.2** — As a debugger, each run writes a `summary.json` with metric counters and final status.
- **S04.3** — As an operator, I list past runs and inspect the latest run's summary from a CLI.
- **S04.4** — As a debugger, I filter events of a run by kind / tool / text substring, with JSON output.
- **S04.5** — As an operator, I can disable event logging via env without breaking the run.
