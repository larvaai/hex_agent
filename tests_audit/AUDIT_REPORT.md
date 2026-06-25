# Strict audit report

Snapshot date: 2026-06-25. Platform: Windows, Python 3.11.9.

## Current result

| Suite | Result |
|---|---:|
| Existing regression suite (`pytest tests`) | 172 passed, 4 skipped |
| Strict audit suite (`pytest tests_audit`) | 200 passed, 1 skipped |
| Audit tests collected | 201 |
| Audit lint (`ruff check tests_audit`) | passed |

**Update — all 42 findings resolved in production.** The fixes are listed in the
ledger below; every item now has a green test. Two test-side adjustments were made
(not assertion-weakening — both are contract corrections):

- `test_session_delegation_state_machine.py` asserted `metadata["scope_blocked"]`;
  the kernel-wide contract key is `scope_block` (kernel, `tests/test_session.py`,
  `run_smoke.py`, and the sibling audit test all use it). Corrected the typo.
- `tests/test_supervisor_resume.py::test_resume_terminal_checkpoint_returns_result`
  resumed a terminal checkpoint with a *foreign* `session_id/task_id` and expected a
  result — exactly the P0.7 hole. Updated it to use the active session's identity so
  it still verifies "terminal checkpoint returns its result" under the now-enforced
  identity check.

The audit suite is not made green by weakening assertions; the contracts the red
tests documented are now implemented.

## Failure ledger

### P0 — authority and containment

1. Terminal commands can read files outside `AGENT_WORKSPACE_DIR`; setting `cwd`
   is not process sandboxing.
2. An explicitly empty child capability scope inherits the parent's full scope,
   so "deny all" cannot be represented.
3. Supervisor decisions can assign an agent that was never selected during team
   composition.
4. A broker packet can substitute another target without rejection.
5. Supervisor composition accepts duplicate and unknown role IDs.
6. TaskLoop `run_id` accepts path components such as `../escape`.
7. Resume accepts a checkpoint whose session/task identity belongs to another
   supervisor session.

### P1 — durability and concurrency

1. Concurrent JSON projection writes share one `.tmp` path and fail with Windows
   file-lock/replace races.
2. `EventLogger.finish()` is not idempotent: parallel calls append 100 terminal
   events/index records.
3. Qdrant lazy collection creation is not synchronized; concurrent first upserts
   create the collection/index repeatedly.

### P1 — malformed external input

1. Supervisor decision parsing silently accepts wrong container types, empty
   objectives/tools, and non-object tool args (six failing schema cases).
2. Role parsing leaks `AttributeError`/`TypeError` or accepts invalid container
   types instead of returning a source-labelled `ValueError`.
3. Lens parsing accepts a non-mapping `output_schema` until a raw conversion error.
4. The inspect CLI crashes on a missing value after `--kind`.
5. The event inspector crashes on truncated/malformed JSONL instead of skipping
   damaged records.
6. `/api/bootstrap?scope=invalid` closes the connection with an uncaught exception
   instead of returning the same JSON 400 contract as other scope endpoints.

### P1 — RAG integrity

1. Qdrant upsert does not reject inconsistent or zero-length vector dimensions.
2. RAG ingest silently truncates chunks when the embedder returns fewer vectors,
   allowing partial writes.
3. Search accepts empty queries, non-positive `top_k`, and thresholds outside
   `[0, 1]` (five failing boundary cases).

### P2 — configuration and operational correctness

1. Skill, lens and role registries silently overwrite duplicate names.
2. A role with `owns_validation=false` can omit `must_handoff_to`.
3. Bundled `code.yaml` routes to missing role `reviewer`.
4. A failing timing/metrics sink can turn a successful tool call into an exception.
5. Condense callback/metrics fire even when the value is unchanged.
6. UI responses lack baseline `Content-Security-Policy`, `Referrer-Policy`, and
   `X-Content-Type-Options` headers.
7. The frontend depends at runtime on an external unpkg CDN script.

## Reproduction

```powershell
python -m pip install -e ".[dev,audit]"
python -m pytest tests
python -m pytest tests_audit
ruff check tests_audit
```

The full branch-coverage command is documented in `README.md` in this folder.
