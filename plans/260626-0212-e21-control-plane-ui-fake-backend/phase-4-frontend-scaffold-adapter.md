---
phase: 4
title: "Frontend scaffold + thin transport adapter"
status: pending
plan: 260626-0212-e21-control-plane-ui-fake-backend
created: 2026-06-26
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — Frontend scaffold + thin adapter

## Overview

Dựng project **React + Vite + TS** mới song song (DEC-6 #6 — không đụng
[ui/server.py](../../../ui/server.py)) + một **adapter mỏng (~30 dòng)** gom mọi
`fetch`/`EventSource` vào một chỗ. Phụ thuộc **Phase 2** (import `generated.d.ts`).

Vì sao adapter mỏng (không phải lớp swap transport): server lo việc swap (đổi URL);
adapter chỉ là **điểm bám test** + một cửa duy nhất cho transport (giống nguyên lý
chokepoint của repo). Đây là chỗ contract-seam test (Phase 7) bám vào. Không phình
thành "adapter + server đều swap" (Hướng C — trả 2 lần effort, YAGNI).

## Files

**Create (tất cả dưới `ui/control-plane/`):**
- `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `.gitignore` (node_modules/, dist/).
- `src/main.tsx`, `src/App.tsx` (shell rỗng + connection-status badge).
- `src/adapter/controlPlane.ts` — adapter: `getSnapshot()`, `postCommand(cmd)`, `openStream(onEvent, {lastEventId})` với reconnect/backoff.
- `src/config.ts` — `BASE_URL` (env `VITE_CP_BASE_URL`, default fake), `CP_TOKEN`.
- `src/test/controlPlane.test.ts` — vitest cho adapter.
- (đã có từ Phase 2: `src/contracts/generated.d.ts`)

**Dev-deps:** `react`,`react-dom`,`@xyflow/react`,`dagre`,`@tanstack/react-virtual`
(dùng Phase 5/6); `vite`,`typescript`,`vitest`,`@testing-library/react`,`jsdom`,`msw`
(msw **chỉ** cho component test lẻ — KHÔNG làm transport fake; fake chính là server Python, §3 brainstorm).

### Adapter contract (điểm bám seam-test)
- `getSnapshot(): Promise<TaskLoopSnapshot>` — `fetch(BASE_URL+'/api/snapshot')`.
- `postCommand(cmd: RuntimeCommand): Promise<CommandAck>` — POST + header token; **không** mutate state UI-side.
- `openStream(onEvent, {lastEventId?})` — `new EventSource(BASE_URL+'/api/stream?token='+CP_TOKEN)` (token qua **query** vì EventSource không set header được — **F8/D7**); browser tự gửi `Last-Event-ID`; xử lý `event: resync` → gọi `getSnapshot()` rồi reopen (F7); `onEvent` nhận **đã-parse `ui_payload`** (adapter không bao giờ đọc `payload`); reconnect có backoff + báo trạng thái (S21.25).
- Tất cả type từ `generated.d.ts` (không hand-write).

## TDD

### Tests Before (RED — vitest, dùng mock fetch/EventSource hoặc msw)
- [ ] `adapter_reads_ui_payload_only`: cho frame có cả `payload` (secret) lẫn `ui_payload`; `onEvent` nhận object **không** chứa key `payload`/secret. **Khoá:** seam — UI mù với raw.
- [ ] `adapter_post_sends_runtime_command`: `postCommand` gửi đúng JSON shape `RuntimeCommand` + token header; trả `CommandAck`; **không** đổi state nội bộ. **Khoá:** write path = phát command.
- [ ] `adapter_reconnect_uses_last_event_id`: ngắt stream → adapter reconnect, truyền `lastEventId` đã thấy; có backoff (không storm). **Khoá:** S21.25.
- [ ] Run → FAIL (chưa có `src/adapter/controlPlane.ts`).

### Implement
1. Scaffold Vite React-TS (`npm create vite` tương đương, commit lockfile).
2. `src/adapter/controlPlane.ts` theo contract; import types từ `generated.d.ts`.
3. `App.tsx` shell + badge; chưa có screen (Phase 5/6).
4. Min code 3 test xanh.

### Tests After (xanh)
- [ ] 3 test adapter xanh.
- [ ] `npm run build` (tsc) không lỗi type (generated types compile được).

### Regression Gate
`npm --prefix ui/control-plane ci && npm --prefix ui/control-plane run test && npm --prefix ui/control-plane run build`
→ tất cả PASS. (Python suite không đổi ở phase này — chạy `python -m pytest -q` sanity, vẫn xanh.)

## Success
- [ ] `npm run dev` lên được shell + badge; `npm run build` sạch.
- [ ] Adapter là **một** cửa transport; 3 test seam-foundation xanh.
- [ ] `generated.d.ts` import & compile (TS↔Python fidelity hoạt động end-to-end).

## Risks
- **MSW bị kéo thành transport fake** (tb): cấm — fake chính là server Python (R2). MSW chỉ mock cho component test lẻ. Mitigation: code-review + adapter test chạy được với cả mock thuần.
- **Node/Vite version drift** (thấp): node v26 + npm 11 sẵn (đã verify); commit lockfile để reproducible.
- **EventSource không gửi token header** (đã giải — F8/D7): token qua `?token=`; cả fake lẫn real honor cùng cách → read-path authn nhất quán, drop-in giữ contract. Test `adapter_stream_sends_token` (query có token). Lưu ý prod: query token vào log → real backend nên rotate/short-lived (BACKLOG, ngoài fake v1).
- **resync khi vượt ring** (tb, F7): adapter phải bắt `event: resync` → re-fetch snapshot, không coi là lỗi. Test trong Phase 7 (reality-on).
