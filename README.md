# core_agent

Clean rebuild of a hexagonal (microkernel) multi-agent system, một epic mỗi đợt. Trạng thái hiện tại:

- **Nền tảng (P0) — done**: E01 Kernel (`core/`), E02 Output Discipline (`discipline/`), E03 LLM Adapter (`llm/`), E04 Observability (`observability/`).
- **Single-agent + tools (P1–P2) — done**: E05 Graph (`graph/`), E06 Safety/Toolbox (`safety/`, `toolbox/`, `middleware/`), E07 Skills (`skills/`), E08 RAG (`rag/`, Qdrant + memory offline).
- **Multi-agent (P3) — done**: E09 Roles (`roles/`), E10 Delegation + TaskLoop (`supervisor/`, `delegation/`, `adapters/`).
- **Realtime control (P4, cross) — active**: E21 Realtime Control Plane (`control/`) — Phase A (contracts) + Phase B B1 (EventEmitter) shipped; transport / Control-Tower UI / reliability pending.
- **Cross**: E19 Test Harness (`tests/`, `tests_audit/`).

Tài liệu: bắt đầu ở **[docs/README.md](docs/README.md)** (bản đồ) + [docs/getting-started.md](docs/getting-started.md). Spec epic ở [docs/spec/](docs/spec/); roadmap tương lai ở [docs/roadmap/](docs/roadmap/).

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

# local real-time UI (then open http://127.0.0.1:8765):
python -m ui.server
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

## Design docs

- [docs/README.md](docs/README.md) — bản đồ toàn bộ tài liệu (4 trục Diátaxis + spec + roadmap).
- [Runtime flow — how a task runs input → output (current reality)](docs/reference/runtime-flow.md)
- [Known risks — dangerous files & behavioral footguns (read before editing)](docs/reference/known-risks.md)
- [MCP tool architecture, scaling and safety](docs/reference/mcp-tools.md) — *proposal, not yet implemented*
- [System architecture](docs/system-architecture.md) · [Code standards](docs/code-standards.md) · [Decision register](docs/decisions.md)
