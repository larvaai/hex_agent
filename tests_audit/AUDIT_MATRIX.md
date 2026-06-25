# Audit coverage matrix

This matrix maps production risk surfaces to strict tests. The normal regression
suite remains in `tests/`; this folder is the independent adversarial suite.

| Surface | Production modules | Audit file | Techniques |
|---|---|---|---|
| Contracts and codecs | `core.schemas`, `core.state`, `graph.state`, `supervisor.state` | `test_contract_roundtrips.py` | round-trip, alias isolation, schema invariants |
| Kernel chokepoint | `core.kernel`, `core.registry`, `core.events`, `features.loader` | `test_kernel_registry_adversarial.py` | exception normalization, mutation attack, freeze, fallback, 1,000-call concurrency |
| Middleware | `middleware.*`, `core.bootstrap` | `test_middleware_exact_semantics.py` | exact ordering, callback isolation, retry matrix, boundary counts |
| Discipline and parsers | `discipline.*` | `test_discipline_and_rag_properties.py` | Hypothesis properties, arbitrary-byte fuzzing, off-by-one budgets |
| Sessions and delegation | `core.session`, `delegation.*` | `test_session_delegation_state_machine.py` | lifecycle transitions, scope monotonicity, idempotency, corrupt handler protocol |
| Agent graph and resume | `graph.*`, `orchestrator.*` | `test_graph_resume_matrix.py` | transition matrix, transport failure, effect replay, checkpoint races |
| Filesystem/process safety | `safety.*`, `toolbox.*` | `test_security_boundaries.py` | traversal, symlink escape, binary/UTF-8, command policy, process confinement |
| RAG logic/math | `rag.chunking`, `rag.embedders`, `rag.stores`, `rag.service` | `test_discipline_and_rag_properties.py`, `test_rag_qdrant_adapter_contract.py` | reference implementation, vector properties, validation, cardinality |
| Qdrant adapter | `rag.stores_qdrant` | `test_rag_qdrant_adapter_contract.py` | strict fake client, exact payload/filter forwarding, deterministic IDs, first-write race |
| Roles, skills, lenses | `roles.*`, `skills.*`, bundled YAML/Markdown | `test_roles_skills_config_integrity.py` | property parsing, duplicate rejection, closed-world references, prompt disclosure |
| Supervisor authority | `supervisor.*` | `test_supervisor_adversarial_matrix.py` | hostile model JSON, selected-agent authority, broker substitution, evidence gate, SQLite concurrency |
| Observability | `observability.*`, `core.events` | `test_observability_durability.py` | metric truth table, 2,000-event load, finish race, corrupt log recovery, CLI matrix |
| UI backend/API | `ui.server` | `test_ui_http_and_frontend_contract.py` | real threaded HTTP server, status/type matrix, input limits, sensitive-file boundary |
| Frontend static contract | `ui/static/*` | `test_ui_http_and_frontend_contract.py` | DOM selector closure, unsafe sink scan, external dependency and mojibake checks |
| Executable entrypoints | `run_smoke.py`, `ui.server:main`, `observability.inspect`, `tools/gen_map.py`, `read_file_and_list.py` | `test_cli_and_tooling_entrypoints.py`, `test_observability_durability.py` | CLI argument matrix, resource cleanup, generated-output verification |

## Test types present

- deterministic unit and contract tests;
- state-machine and lifecycle tests;
- Hypothesis property-based tests;
- arbitrary-byte parser fuzz tests;
- adversarial security tests;
- concurrency, race and load tests;
- crash/resume and idempotency tests;
- in-process integration tests;
- black-box HTTP tests;
- configuration/library integrity tests;
- static frontend security/DOM contract tests.

No audit test uses `xfail`. The only conditional skip is the symlink-escape test
when the host OS refuses symlink creation.
