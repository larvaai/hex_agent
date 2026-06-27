---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — scaffold + strategy + re-home (no behaviour change)

**Goal:** layered `tests/` tree, marker policy, shared fixtures, and the existing 51 tests
moved into the pyramid **with assertions unchanged**. Nothing about `dragzero/` changes.

## Files

- `drag_from_zero/pyproject.toml` — extend `[tool.pytest.ini_options]`:
  ```toml
  testpaths = ["tests"]
  addopts = "-m 'not browser and not real_llm'"
  markers = [
    "browser: drives the real ui/ in a headless browser (opt-in; needs playwright + chromium)",
    "real_llm: hits a real local model (opt-in; skips unless OPENAI_BASE_URL is set)",
  ]
  # same test basenames live across unit/ integration/ e2e/ — avoid import collisions
  # (conftest stays at tests/ root; no __init__.py)
  ```
  Add `import-mode=importlib` via `addopts` or the `[tool.pytest.ini_options] consider_namespace_packages`/`pythonpath`; concretely append ` --import-mode=importlib` to `addopts`.
  Add optional dev deps (documented, not installed by default):
  ```toml
  [project.optional-dependencies]
  test-browser = ["playwright>=1.40", "pytest-playwright>=0.4"]
  ```
- `drag_from_zero/tests/conftest.py` — keep the existing `sys.path` insert; ADD:
  - `pytest_collection_modifyitems`: auto-skip `real_llm` items when `OPENAI_BASE_URL`
    unset; auto-skip `browser` items when `playwright` not importable.
  - shared fixtures (lifted from `test_slice6a_server`): `server_factory(builder, static_dir)`
    → `(port, httpd)` on ephemeral port; `ws_client` (the hand-rolled stdlib WS reader);
    `fake_llm_planner_coder` responder; `tmp_sandbox`.
- New dirs: `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/e2e_browser/`,
  `tests/real_llm/`.

## Re-home map (move, then verify identical)

| from | to |
|---|---|
| `test_invariants.py` | split: pure folds → `unit/test_read_model.py` seed; loop/budget/hook/inject → `integration/test_orchestrator_loop.py` seed |
| `test_slice2_adapter.py` | pure parse → `unit/test_llm_local_parse.py`; full-loop replay → `integration/test_adapter_substitution.py` |
| `test_slice3_workqueue.py` | `integration/test_workqueue_inject.py` |
| `test_slice3b_eval.py` | scorer good≠bad → `unit/test_scorers.py`; run_scenario/aggregate → `integration/test_eval_runner.py` |
| `test_slice4_tools.py` | sandbox/jail pure → `unit/test_tools_fs.py`; tool loop → `integration/test_orchestrator_loop.py` |
| `test_slice5_topology.py` | validate/round-trip → `unit/test_topology.py`; build_runtime → `integration/test_wiring.py` |
| `test_slice6a_server.py` | stays as `e2e/test_topology_to_server.py` seed (already over-wire) |

Re-home = `git mv` then split by copy; **do not edit assertion bodies**. If a test mixes
layers, copy the relevant asserts into each destination unchanged.

## TDD framing

- **Red proof:** after the move, run `pytest -q` — must still be **≥51 passed**. Then delete
  one re-homed assertion locally, confirm the count drops (proves the move kept teeth),
  restore it.
- **Green gate:** `python -m pytest -q` → ≥51 passed, 0 failed, default selection silently
  excludes `browser`+`real_llm` (collect-only shows them deselected, not errored).

## Acceptance

- [ ] `pytest -q` ≥ 51 passed; `pytest --co -q -m browser` and `-m real_llm` collect (0 run by default).
- [ ] markers registered (no `PytestUnknownMarkWarning`).
- [ ] same-basename files across dirs collect without import error (`--import-mode=importlib`).
- [ ] zero `dragzero/` source diff.
