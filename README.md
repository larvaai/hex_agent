# core_agent

Clean rebuild of the agent system. **Sprint 0** implements the foundation (P0):

- **E01 Kernel** — `core/`: hexagonal kernel, capability registry (+ null fallback), `CapabilityResult` envelope, feature plugins from `config/features.yaml`.
- **E02 Output Discipline** — `discipline/`: JSON parse + repair, condense, finish-gate, budgets (shared module).
- **E03 LLM Adapter** — `llm/`: OpenAI-compatible, JSON-mode, **lazy-init**, injectable client.
- **E04 Observability** — `observability/`: event log (JSONL) + summary + inspect CLI.

Spec: see `docs/rebuild_from_zero/` (E01–E04 PRD/stories/acceptance) and `docs/rebuild_from_zero/NEW_REPO_BUILD_GUIDE.md`.

## Requirements
Python 3.11+.

```bash
python -m pip install -e ".[dev]"   # or: pip install openai PyYAML pytest

# optional production RAG/Qdrant backend + integration tests:
python -m pip install -e ".[dev,rag]"
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

# local real-time UI (equivalent entrypoints; open http://127.0.0.1:8765):
python -m ui
# python -m ui.server
# core-agent-ui              # after editable install
```

## Layout
```
core/          kernel, registry, schemas (envelope), events, state, bootstrap
adapters/      concrete implementations of core ports
delegation/    framework-neutral manager, registry, policy, progress store
discipline/    json_gate, condense, finish_gate, budget   (shared)
graph/         serializable state, nodes, compiled LangGraph runtime
orchestrator/  stable run/resume facade + SQLite checkpointer
llm/           adapter (lazy, JSON-mode)
observability/ event_log + inspect CLI
ui/            Dracula console: runs, prompts, state, logs, file explorer
features/      loader + example_echo (plugin pattern)
config/        features.yaml
tests/         offline unit, concurrency, resume, and delegation tests
var/           (gitignored) agent_runs/<run_id>/{events.jsonl,summary.json,langgraph.sqlite,checkpoint.json}
```

## Principles (baked in)
One compiled LangGraph substrate; `AgentKernel` is shared/frozen while `KernelSession` owns run state; every LLM/tool call crosses `execute_tool`; delegation uses a separate framework-neutral chokepoint; discipline shared (no duplication); SQLite is parent-graph checkpoint truth; JSON-mode at the LLM layer; thread-safe observability; lazy LLM client; UTF-8 no BOM; `var/` gitignored.

## Documentation

- [Contributing — quick contributor checklist](CONTRIBUTING.md)
- [Onboarding & contributing — newcomer path, architecture and change playbooks](docs/ONBOARDING_AND_CONTRIBUTING.md)
- [Run & configure — CLI, UI, API, system prompts, skills, roles and features](docs/RUN_AND_CONFIGURE.md)
- [Runtime flow — how a task runs input → output (current reality)](docs/RUNTIME_FLOW.md)
- [Class encyclopedia — all production classes and ownership](docs/CLASS_ENCYCLOPEDIA.md)
- [Code review — verified findings and test gaps](docs/CODE_REVIEW.md)
- [Known risks — dangerous files & behavioral footguns (read before editing)](docs/KNOWN_RISKS.md)
- [MCP tool architecture, scaling and safety](docs/MCP_TOOLS.md) — *proposal, not yet implemented*
