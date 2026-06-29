---
phase: 3
title: "Fake Control Server — replay + SSE + commands + authz + reality"
status: pending
plan: 260626-0212-e21-control-plane-ui-fake-backend
created: 2026-06-26
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — Fake Control Server

## Overview

Tim của kế hoạch: một **fake server Python** nói **đúng hợp đồng E21 thật** bằng cách
**reuse `control/`** (Hướng B, DEC-6). Đây là nơi "drop-in = đổi URL" thành sự thật:
fake chạy cùng `Redactor`/`SessionSeq`/contract như backend thật. Phụ thuộc **Phase 1**
(snapshot + ack). Stdlib-only (D5), giống [ui/server.py:16](../../../ui/server.py).

3 endpoint (khớp AC S21.15/16/17):
- `GET /api/snapshot` → `TaskLoopSnapshot` (no raw secret) — S21.17.
- `GET /api/stream` (SSE) → **chỉ `ui_payload`** + `seq`, hỗ trợ `Last-Event-ID` catch-up — S21.16.
- `POST /api/commands` → static-token authz (L2), `parse_command`, `CommandAck`, idempotency — S21.15.

Và **inject reality** (L3): latency, ép drop→reconnect, trùng `event_id`, trùng `idempotency_key`.

## Files

**Create:**
- `control/replay.py` — `EventReplayBuffer`: load `events.jsonl`, ring-buffer (2048, D4), `events_after(last_event_id)` catch-up + dedup theo `event_id`, hook reality-injection. (Tách khỏi HTTP → test thuần.)
- `tools/gen_t1_fixture.py` — sinh kịch bản T1 **bằng dataclass thật** → `RuntimeEvent(...)` → `Redactor().apply()` → ghi jsonl.
- `fixtures/control_plane/t1_scenario.events.jsonl` — output (committed).
- `tools/fake_control_server.py` — `ThreadingHTTPServer` + handler 3 endpoint; wiring replay+snapshot+authz+reality. CLI `--port`/`--token`/`--no-reality`.
- `tests/test_fake_control_server.py` — test 3 endpoint + reality.

**Reuse (không sửa):** `control/redaction.py` (`Redactor`), `control/events.py` (`SessionSeq`,`RuntimeEvent`), `control/commands.py` (`parse_command`,`CommandAck`), `control/command_registry.py` (`load_command_registry`), `control/snapshot.py` (`build_snapshot`).

### Kịch bản T1 fixture (phủ S21.9/18/21) — dùng `loop.*` event THẬT (F1)
`loop.team_composed`[A,B,C] → `loop.turn`[A] → `loop.decision`[next=B] → `loop.tool`
[risk=high] → `checkpoint.reached` waiting → (chờ `ApproveCheckpoint`) → `approval.approved`
→ `loop.turn`[B] → `loop.finished`. Cộng 1 event `permission.changed`[B] (để Inspector có
permission — F6). Mỗi dòng = `RuntimeEvent(...)` → **stamp `seq` qua `SessionSeq.next()`**
([events.py:204](../../../control/events.py)) → `Redactor().apply()` → `as_dict()`.
> **F3:** KHÔNG ghi `RuntimeEvent(...).as_dict()` trực tiếp — `seq` mặc định 0
> ([events.py:126](../../../control/events.py)), chỉ stamp ở [emitter.py:57](../../../control/emitter.py).
> seq=0 khắp nơi ⇒ `id:0` ⇒ Last-Event-ID vô nghĩa. Phải stamp monotonic.
> Một event mang `payload.api_key` (chứng minh redaction reachable — F2).

### Endpoint contract
- **POST /api/commands:** header token != `--token` → **401**; `command_type` không có
  trong registry (`CommandTypeRegistry.assert_known()` [command_registry.py:43](../../../control/command_registry.py),
  **F4**) **hoặc** body sai schema (`parse_command` raise [commands.py:100-110](../../../control/commands.py))
  → **400** + phát `command.rejected`; hợp lệ → ghi `command.received`, trả
  `CommandAck(status=received, command_id, seq)` **<300ms**; dedup keyed **`(session_id,
  idempotency_key)`**, bounded (**F9**) → đã thấy → trả **cùng** ack (áp 1 lần, S21.10).
- **GET /api/stream:** authz qua **`?token=`** (EventSource no-header — **F8/D7**), token sai → 401;
  `Content-Type: text/event-stream`; mỗi event `id: <seq>\nevent: <event_type>\ndata:
  <ui_payload JSON>\n\n`; client gửi `Last-Event-ID` → resume từ seq+1.
  - **Visibility gate (F2/D6):** event registry `visibility=='secret'` → **drop, không gửi**
    (logic thật dù hôm nay chưa type secret — test dựng 1 event secret-type để chứng minh).
  - **Vượt ring (F7/S21.16):** `Last-Event-ID` < seq cũ nhất còn trong ring (2048) → trả
    `event: resync` → client re-fetch `GET /api/snapshot` + replay JSONL; **không** im lặng mất.
- **GET /api/snapshot:** `build_snapshot(buffer.events, session_id)` → JSON (chỉ `ui_payload`);
  session lạ → **404**.

## TDD

### Tests Before (RED)
- [ ] `test_sse_redacts_reachable_event` (S21.16/**F2**): event `ui_safe` có `payload.api_key`; SSE frame `data` chỉ `[REDACTED]`, raw `payload` KHÔNG xuất hiện. **Khoá:** redaction reachable (không phải đường chết).
- [ ] `test_sse_drops_secret_visibility` (S21.16/**F2**): dựng 1 event registry `visibility=secret` → SSE **không** gửi nó. **Khoá:** visibility-gate thật.
- [ ] `test_last_event_id_catchup_no_dup` (S21.16): `Last-Event-ID: 5` → chỉ nhận seq>5, không trùng. **Khoá:** reconnect đúng.
- [ ] `test_out_of_ring_resync` (S21.16/**F7**): `Last-Event-ID` < seq cũ nhất → nhận `event: resync` (không im lặng mất event). **Khoá:** fallback đúng AC.
- [ ] `test_stream_token_query` (**F8**): `?token=` sai → 401; đúng → stream. **Khoá:** read-path authn nhất quán.
- [ ] `test_post_command_authz` (S21.15): thiếu/sai token header → 401. **Khoá:** L2 honest.
- [ ] `test_post_command_unknown_type` (S21.4/**F4**): `command_type` lạ → 400 + `command.rejected`. **Khoá:** registry gate.
- [ ] `test_post_command_bad_schema` (S21.15): thiếu `idempotency_key` → 400 + `command.rejected`. **Khoá:** gateway từ chối trước queue.
- [ ] `test_post_command_ack_and_idempotency` (S21.10/15/**F9**): hợp lệ → `CommandAck.status=="received"`+`command_id`; gửi lại cùng `(session_id,idempotency_key)` → cùng ack, áp 1 lần. **Khoá:** double-click an toàn.
- [ ] `test_snapshot_no_raw_secret` (S21.17): `GET /api/snapshot` không secret; session lạ → 404.
- [ ] `test_replay_ring_and_reality_dedup` (D4/L3/**F15**): buffer ≤2048; **reality-ON** → dup `event_id` (kể cả seq khác) → `events_after` dedup + order theo seq; `--no-reality` → deterministic. **Khoá:** dedup chịu được inject.
- [ ] Run → FAIL (chưa có `control.replay` / `tools/fake_control_server.py`).

### Implement
1. `control/replay.py`: `EventReplayBuffer(maxlen=2048)`; `append`/`events_after(last_id)` (dedup `event_id`, order seq) / `oldest_seq` (cho resync) / `load_jsonl`; reality hooks gated `inject: bool` (default True; off cho test).
2. `tools/gen_t1_fixture.py`: dựng `loop.*` event qua dataclass + stamp `seq` (`SessionSeq`) + `Redactor().apply()` → ghi jsonl (commit).
3. `tools/fake_control_server.py`: handler `do_GET`/`do_POST` theo contract; reuse `Redactor`/`SessionSeq`/`parse_command`/`build_snapshot`/`load_command_registry`/`load_event_registry`; dedup dict keyed `(session_id, idempotency_key)`; visibility-gate đọc `event_registry`; resync khi vượt ring; cap số SSE connection đồng thời (**F12**, demo single-client).
4. Min code để test xanh; reality off-able qua `--no-reality` + env.

### Tests After (xanh)
- [ ] 8 test trên xanh (reality-off cho assert deterministic; 1 test riêng bật reality kiểm dup+dedup).

### Regression Gate
`python -m pytest tests/ tests_audit/ -q && python run_smoke.py` → PASS + `CORE_AGENT_SMOKE_OK`.
Smoke thủ công: `python tools/fake_control_server.py --port 8800 --no-reality` rồi `curl -s localhost:8800/api/snapshot | python -m json.tool` cho snapshot hợp lệ.

## Success
- [ ] 3 endpoint hành xử đúng contract (8 test xanh).
- [ ] SSE **không bao giờ** lộ raw `payload`/secret (grep frame = `[REDACTED]`).
- [ ] `idempotency_key` trùng → áp 1 lần; ACK <300ms (đo trong test).
- [ ] Fixture jsonl sinh qua dataclass thật (không JSON viết tay) — by-construction.

## Risks
- **R2 (fake quá sạch)** đã trị bằng L3 inject; nhưng test phải off reality để deterministic — Mitigation: cờ `--no-reality`/env, 1 test riêng cho reality.
- **R6 import path** (thấp): `tools/` import `control.*` cần chạy từ repo root; test import như module (`from control.replay import ...`) → CI bắt sớm.
- **SSE blocking trong ThreadingHTTPServer** (tb): mỗi stream giữ 1 thread; `daemon_threads=True` ([ui/server.py:555](../../../ui/server.py)) để không treo shutdown. Test dùng client timeout.
