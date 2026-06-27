---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — L1 backend real-integration (no model)

**Goal:** deterministic pytest against the REAL `IdeControlServer` / `IdeSession` / `AgentRunner`
in-process (no model, no browser). Closes the CRITICAL/HIGH backend gaps. This is the real-only backbone.

**Pattern:** boot `IdeControlServer((host,0), token=…, session_id=…)` on an ephemeral port in a thread
(mirror `test_ide_backend.py:122` setup) or call the app objects directly. Drive real HTTP / call
`session.emit` directly for stream-seed. NO `orchestrator.run` (that needs the model) — for run-lifecycle
use the existing `_finish_*` + cancel-boundary seam (`test_ide_backend.py:158,183`).

## Files
`tests/test_ide_stream.py` · `tests/test_ide_files_edges.py` · `tests/test_ide_http_cors_auth.py` · `tests/test_ide_run_lifecycle.py`

## Tests Before (red) → Implement (test code) → assertions

### test_ide_stream.py — SSE lifecycle (server.py:387-436) — zero coverage today
- `test_stream_emits_ui_payload_only_never_raw` — seed `session.emit` with a secret-keyed payload (session.py:87 redacts); GET `/api/stream`; assert frame `data:` carries `ui_payload` with `[REDACTED]`, raw secret string absent from the whole byte stream. **Security backbone.**
- `test_stream_visibility_filter_drops_internal` — emit an `internal`/`secret`-visibility event; assert it is NOT framed but `last_seq` still advances (server.py:419).
- `test_stream_last_event_id_resumes` — connect with `lastEventId=k`; assert only seq>k delivered, in order.
- `test_stream_resync_frame_when_out_of_ring` — force last_seq below ring floor; assert a `event: resync` frame (controlPlane.ts:124 contract), not a silent gap.

### test_ide_files_edges.py — files.py edges — mostly untested
- `test_write_binary_rejected` — write content with `\x00` → FileOpError "binary…" (files.py:180-181).
- `test_write_oversized_rejected` — content > `MAX_FILE_BYTES` (files.py:60) → reject (files.py:216).
- `test_tree_hides_ignored_dirs` — create `.git/config`, `node_modules/x` under workspace; `/api/files/tree` excludes them (files.py:33-43,89-91).
- `test_sensitive_crud_blocked` — create/rename/delete on `.env`,`id_rsa`,`*.pem` all blocked (files.py:225-267) — extends read/write-only coverage.
- `test_symlink_not_followed` — symlink workspace→/etc; tree marks `type:symlink`, read through it rejected (files.py:145-147).
- `test_project_scope_hides_agent_runs` — `scope=project` tree excludes `var/agent_runs/*` (files.py:112-113).

### test_ide_http_cors_auth.py — server.py auth + CORS — untested
- `test_cors_reflects_localhost_only` — `Origin: http://127.0.0.1:3000` → reflected; `Origin: http://evil.com` → NOT reflected (server.py:55-56,188-193). **No `*`.**
- `test_options_preflight_headers` — OPTIONS → 204 + Allow-Methods/Headers/Max-Age (server.py:377-384).
- `test_snapshot_is_public_but_writes_gated` — GET `/api/snapshot` 200 without token (server.py:242-248); POST/PUT/DELETE without token → 401 (server.py:195-205). Documents the asymmetry deliberately.
- `test_idempotency_dedup_same_ack` — POST SubmitPrompt twice, same `(session,idempotency_key)` → identical ack, run dispatched once (server.py:111-155). **Monkeypatch `runner.start` to a no-op counter** to avoid the model.

### test_ide_run_lifecycle.py — runner.py without model
- `test_cancel_sets_status_cancelled_not_finished` — start (stubbed `_run`), cancel → `_finish_cancelled`, status `cancelled` (runner.py:159,196).
- `test_baseline_captured_before_run` — assert `try_begin_run` snapshots baseline at start (runner.py:99-101); a post-start write shows in diff.
- `test_diff_baseline_atomic_under_concurrent_diff` — two concurrent `/api/files/diff` don't race baseline (session.py:135-137).

## "Is the test real?" gate (anti-vacuous)
Each security/filter test must be shown to FAIL if the guard is removed: temporarily invert one assertion
(or feed the known-bad input expecting pass) and confirm red, then restore. Note the demonstration in the
test docstring. No assertion weaker than the invariant it guards (code-standards §4.5).

## Regression Gate
`python -m pytest tests/ tests_audit/ -q` stays green (was 1072 passed). New files add only; touch no
existing test. `tests_audit/ -q --tb=no` (no-xfail) clean.
