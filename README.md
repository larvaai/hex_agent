# core_agent

Clean rebuild of the agent system. **Sprint 0** implements the foundation (P0):

- **E01 Kernel** — `core/`: hexagonal kernel, capability registry (+ null fallback), `CapabilityResult` envelope, feature plugins from `config/features.yaml`.
- **E02 Output Discipline** — `discipline/`: JSON parse + repair, condense, finish-gate, budgets (shared module).
- **E03 LLM Adapter** — `llm/`: OpenAI-compatible, JSON-mode, **lazy-init**, injectable client.
- **E04 Observability** — `observability/`: event log (JSONL) + summary + inspect CLI.

Spec: see `../rebuild_spec/` (E01–E04 PRD/stories/acceptance) and `../NEW_REPO_BUILD_GUIDE.md`.

## Requirements
Python 3.11+.

```bash
python -m pip install -e ".[dev]"   # or: pip install openai PyYAML pytest
```

## Run
```bash
# deterministic smoke (no LLM/network):
python run_smoke.py

# tests (offline):
python -m pytest

# inspect a run's events:
python -m observability.inspect list
python -m observability.inspect summary latest
```

## Layout
```
core/          kernel, registry, schemas (envelope), events, state, bootstrap
discipline/    json_gate, condense, finish_gate, budget   (shared)
llm/           adapter (lazy, JSON-mode)
observability/ event_log + inspect CLI
features/      loader + example_echo (plugin pattern)
config/        features.yaml
tests/         offline tests for E01–E04
var/           (gitignored) agent_runs/<run_id>/{events.jsonl,summary.json}
```

## Principles (baked in)
One graph substrate later (single = 1 node); discipline shared (no duplication); JSON-mode at the LLM layer; safety = one chokepoint; observability from commit 1; lazy LLM client; UTF-8 no BOM; `var/` gitignored.
