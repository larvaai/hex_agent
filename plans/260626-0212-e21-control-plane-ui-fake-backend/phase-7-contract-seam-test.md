---
phase: 7
title: "Contract-seam test + demo (định nghĩa Done)"
status: pending
plan: 260626-0212-e21-control-plane-ui-fake-backend
created: 2026-06-26
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 7 — Contract-seam test + demo

## Overview

**Định nghĩa Done** của cả plan: một test cross-cutting chứng minh seam **đúng thật**,
không phải lời hứa. Đây là lý do dùng `--tdd` (contract-seam là load-bearing).
Phụ thuộc **Phase 3** (fake), **5+6** (UI). Chạy UI thật đối thoại với fake server thật.

4 assertion (brainstorm §7):
1. UI **chỉ** đọc `ui_payload`, **không bao giờ** đọc `payload` raw.
2. Render `[REDACTED]` đúng [redaction.py:34](../../../control/redaction.py).
3. Approve gửi `RuntimeCommand` thật qua POST, **không** mutate state UI-side.
4. Reconnect dùng `Last-Event-ID` catch-up.

## Files

**Create:**
- `ui/control-plane/src/test/contract-seam.test.ts` — integration: boot fake server (child process `tools/fake_control_server.py`) → drive adapter/UI → assert 4 điều.
- `ui/control-plane/README.md` — cách chạy demo (fake + dev) + định nghĩa Done.
- `docs/GLOSSARY.md` — thêm thuật ngữ mới (Modify).
- `CHANGELOG.md` — 1 dòng E21 (Modify, code-standards §5).

**Modify:** `plans/260626-0212-.../plan.md` status → (cook cập nhật khi xong).

### Demo (Done = tương tác trên fixtures)
`python tools/fake_control_server.py --port 8800` + `VITE_CP_BASE_URL=http://localhost:8800
npm --prefix ui/control-plane run dev` → kịch bản T1 (O chọn A,B,C → tool high-risk →
checkpoint waiting → Approve → B finished) hiển thị đúng trên Graph/Timeline/Inspector/Modal.

## TDD

### Tests Before (RED — đây LÀ test, viết trước khi "demo xanh")
- [ ] `seam_ui_never_reads_raw_payload` (**F13**): bơm event có cả `payload.api_key` + `ui_payload`; assert **qua API surface của adapter** — object `onEvent` nhận **không có key `payload`** và không chứa giá trị secret (adapter strip raw trước khi expose). KHÔNG dựa grep `.payload` (substring tồn tại trong path `ui_payload`, mong manh). **Khoá:** assertion 1.
- [ ] `seam_renders_redacted`: secret → UI hiển thị `[REDACTED]` literal. **Khoá:** assertion 2.
- [ ] `seam_approve_posts_real_command`: Approve → fake nhận `POST /api/commands` với `RuntimeCommand` hợp lệ (`parse_command` không raise); state UI không đổi trước `approval.approved`. **Khoá:** assertion 3.
- [ ] `seam_reconnect_last_event_id`: ép fake drop SSE (reality on) → adapter reconnect với `Last-Event-ID` → không trùng/không sót event. **Khoá:** assertion 4.
- [ ] Run → FAIL (UI/seam chưa hoàn chỉnh / chưa wire).

### Implement
1. `contract-seam.test.ts`: helper boot/teardown fake server (child_process), `--port` ngẫu nhiên, reality togglable per assertion.
2. Hoàn thiện wiring App nếu test lộ lỗ (vd adapter rò `payload`).
3. `README.md` + `CHANGELOG.md` + `GLOSSARY.md`.

### Tests After (xanh)
- [ ] 4 seam assertion xanh đối thoại với fake server thật.
- [ ] Demo thủ công chạy được (ghi lại lệnh trong README).

### Regression Gate
`python -m pytest tests/ tests_audit/ -q && python run_smoke.py && npm --prefix
ui/control-plane run test && npm --prefix ui/control-plane run build`
→ TẤT CẢ PASS. Đây là gate cuối toàn plan.

## Success
- [ ] 4 contract-seam assertion xanh (đối thoại fake server thật, không mock).
- [ ] Demo T1 tương tác chạy đúng kịch bản.
- [ ] `docs/GLOSSARY.md` có thuật ngữ mới; `CHANGELOG.md` +1 dòng E21.
- [ ] Drop-in chứng minh: đổi `VITE_CP_BASE_URL` sang backend thật (khi có) = 0 dòng UI đổi (ghi là tiêu chí kiểm chứng tương lai trong README).

## Risks
- **Integration test flaky (child process + port)** (tb): dùng port ngẫu nhiên + chờ health trước khi assert; reality off cho assert deterministic, 1 assert riêng bật reconnect. Mitigation: timeout + retry-on-connect.
- **Component bypass adapter đọc raw** (tb, F13): assertion 1 chỉ chứng minh adapter strip; nếu component tự `fetch` raw (bỏ adapter), seam-test không bắt. Mitigation: adapter là cửa transport duy nhất (Phase 4); code-review + lint cấm `fetch`/`EventSource` ngoài `src/adapter/`.
- **Demo cần cả 2 runtime** (thấp): README ghi rõ 2 lệnh; CI chỉ chạy seam-test (headless), demo là thủ công.
