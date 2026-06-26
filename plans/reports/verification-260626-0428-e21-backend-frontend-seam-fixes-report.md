---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# E21 backend↔frontend seam — AFK verification + fixes

**Date:** 2026-06-26 04:28 (+07) · **Plan:** 260626-0212-e21-control-plane-ui-fake-backend · **Mode:** AFK autonomous, no-approval
**Verdict:** ✅ seam wired + hard-verified; **5 HIGH + 2 MEDIUM + 1 LOW bugs found & fixed (TDD)**; work UNCOMMITTED (shared-tree contention — see Git).

---

## 1. What was asked vs what was found

User: "nối backend↔frontend để hoàn thành E21, test cực gắt, mọi thứ đã sẵn sàng."

Ground truth (re-derived, did not trust the stale `verification.json`):
- E21 code already committed on `feat/o-delegation-flexibility` (tip `8cc54d2`); **43/44 working-tree files byte-identical** to it. The working tree on `feat/docs-diataxis-restructure` carries untracked copies (branch-switch leftover — known shared-tree pattern).
- "nối backend↔frontend" in E21's design = React adapter ↔ fake control server. Already wired; the job was to **prove it live + harden it**.

## 2. Verification matrix (combined state, after all fixes)

| Check | Result |
|---|---|
| Full Python suite `pytest tests/ tests_audit/` | **1054 passed**, 1 skipped, 9 xfailed |
| E21 subset (snapshot/replay/fake-server/contracts/gen-ts) | all green (+8 new TDD tests) |
| Frontend vitest | **22/22** (+2 adapter tests; contract-seam drives a real child server) |
| Frontend build (tsc --noEmit + vite) | clean, 529 modules |
| TS drift-guard `gen_ts_contracts.py --check` | exit 0 |
| Core smoke `run_smoke.py` | `CORE_AGENT_SMOKE_OK` |
| **Live HTTP seam drive** (independent of test runner) | **12/12 AC** |
| Live browser E2E (read + write round-trip) | OK, 0 console errors |
| HIGH#2 fix on real fixture (modal gone) | confirmed: cp_demo_1 `approved`, 0 waiting on finished session |

Live drive (`/tmp/e21_live_drive.py`) asserts over real HTTP: snapshot no-raw-secret · SSE redacted (raw `sk-DEMO-LEAK` never on wire) · 401 no-token (read+write) · bad-schema/unknown-cmd → 400 reject · ACK 0.4ms · idempotency once · Last-Event-ID catch-up no-dup · visibility-secret drop · reality drop→reconnect · CORS preflight 204.

## 3. Bug found during live browser test (then a deep audit found more)

**CORS preflight missing (HIGH).** Browser POST of a command carries `X-Auth-Token` → browser sends a preflight `OPTIONS` → fake server returned **501** (no `do_OPTIONS`) → the entire write path (Approve/Reject/Send) silently died cross-origin. **vitest passed anyway** (jsdom doesn't enforce CORS preflight) and the prior `verification.json` claimed "demo verified in-browser" — rendering worked, but clicking Approve against a real cross-origin browser did not. This is the "passes the runner, breaks under real conditions" class.

A 6-lens adversarial audit (24 agents, each booting a real server to reproduce) then found **14 confirmed bugs** (4 refuted). All HIGH reproduced end-to-end.

## 4. Fixes applied (TDD red→green)

| # | Sev | Bug | Fix (file) |
|---|---|---|---|
| CORS | HIGH | preflight 501 → write path dead in browser | `do_OPTIONS` 204 + ACA-Methods/Headers — `tools/fake_control_server.py` |
| F-snap | HIGH | `build_snapshot` ignores `approval.*` → finished session ships `waiting` checkpoint → **phantom ApprovalModal** contradicting the stream | fold `approval.approved/rejected` resolves checkpoint by id, drops agent from `waiting` — `control/snapshot.py` |
| F-body | HIGH | POST non-object JSON (`[]`/`"x"`) → uncaught `AttributeError` crashes request thread, empty wire response | `isinstance(body, dict)` guard in reject path — `fake_control_server.py` |
| F-backoff | HIGH | server 200-then-close + adapter `onopen` resets `attempt=0` every cycle → backoff pinned at 250ms (~4 reconnects/s storm; the flapping "RECONNECTING" badge) | reset backoff only after a connection stays open `stableMs` (2s) — `ui/control-plane/src/adapter/controlPlane.ts` |
| F-resync | HIGH | out-of-ring resync never recovers — adapter keeps stale `lastEventId` → infinite resync + snapshot-refetch loop | drop `lastEventId` on resync (store dedups by seq → no dup) — `adapter/controlPlane.ts` |
| F-issuer | MED | `command.received` hardcodes actor `{human,ui}` → audit trail loses the real issuer | carry `issued_by` into envelope actor + payload — `fake_control_server.py` |
| F-session | MED | write path skips `session_id` validation (read 404s, write 200s); dedup keyed on unvalidated session | reject when `cmd.session_id != self.session_id` — `fake_control_server.py` |
| F-clen | LOW | malformed/negative `Content-Length` → uncaught `ValueError` crashes thread | guarded `int()` mirroring `_stream` — `fake_control_server.py` |

New tests: `test_control_snapshot.py` (+2 approval fold), `test_fake_control_server.py` (+3 hardening +1 CORS = +4), `controlPlane.test.ts` (+2 backoff/resync).

## 5. Not fixed — documented (advisory)

- **MED — visibility gate fails OPEN on unknown event_type.** `_visibility` falls back to `ui_safe` on an unregistered type → it streams. A concurrent session changed the gate to an allowlist (`public`/`ui_safe` only), but the fallback is still permissive. Real fix = fail-closed default (`internal`). NOT applied: genuine posture tradeoff (fail-closed hides new dev events) + that exact code is being actively edited by another session. **Team decision needed.**
- **6× LOW** (all confirmed but accepted/deferred): Redactor is key-name-only — secrets in free-form string *values* pass (plan-accepted design); `?token=` leaks to access logs (F8 accepted tradeoff); no wire-boundary re-redaction backstop (defense-in-depth); `command.rejected` reflects attacker `command_type` verbatim (log-injection, not XSS in current UI); `needs_resync` uses `min(seq)` (out-of-order eviction edge). Out of T1 scope / low blast radius.
- **Reconnect storm — server side** is by-design demo behavior ("a live backend would hold the socket"); only the client backoff was fixed (the defensible half).

## 6. Git state — UNCOMMITTED, deliberately

**A concurrent session is live in the same E21 files** (added `threading.Lock` + visibility allowlist + connection-cap to `fake_control_server.py` ~04:22; a new `ui.ide` module + `agent-ide` launch config on :8800; plan `control-plane-ide`). `fake_control_server.py` + `test_fake_control_server.py` now hold **both sessions' changes interleaved at file level**.

→ **Did not commit.** Committing these pathspecs would entangle the other session's in-flight work (which they likely intend to commit with `ui.ide`). This respects the shared-tree rule ("commit theo pathspec, push by ref"). Nothing is lost — all changes are in the working tree.

My contribution pathspec (commit when the tree settles / by whichever session owns it):
```
control/snapshot.py tools/fake_control_server.py
tests/test_control_snapshot.py tests/test_fake_control_server.py
ui/control-plane/src/adapter/controlPlane.ts ui/control-plane/src/test/controlPlane.test.ts
```
Did NOT touch `CHANGELOG.md` (shared/contested). Proposed entry to add on commit:
> **E21 — seam hardening (AFK):** CORS preflight (browser write path), snapshot folds `approval.*` (no phantom modal), adapter backoff-stability + resync cursor-reset, command issuer attribution + session validation, hostile-body/Content-Length guards. +8 TDD tests. 5 HIGH + 2 MED + 1 LOW from a 6-lens adversarial audit.

## 7. Unresolved questions

1. **Visibility fail-open posture** (§5) — fail-closed default or keep permissive? Team call.
2. **Port :8800 collision** — both `fake_control_server.py` and the new `ui.ide` claim it. Which is canonical for the demo?
3. **Demo fixture** — it's a *completed* session, so the (now-correct) snapshot shows no pending gate. To demo the live Approve interaction visually, a `--paused` fixture variant (truncated at `checkpoint.reached`) would help.
4. **Commit ownership** — confirm whether this session or the `ui.ide` session lands `fake_control_server.py`.
