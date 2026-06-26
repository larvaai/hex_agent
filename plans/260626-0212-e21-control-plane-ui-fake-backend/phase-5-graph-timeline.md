---
phase: 5
title: "Agent Graph + Event Timeline (read path)"
status: pending
plan: 260626-0212-e21-control-plane-ui-fake-backend
created: 2026-06-26
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 5 — Agent Graph + Event Timeline

## Overview

2 màn **đọc** (read path) — hàm thuần của snapshot/event-stream. Phụ thuộc **Phase 3**
(fake cấp data) + **Phase 4** (adapter). Không phụ thuộc Phase 6 (file riêng).

- **Agent Graph** (S21.18): node status realtime, click→inspector. React Flow
  `@xyflow/react` + `dagre` auto-layout (React Flow không tự layout DAG).
- **Event Timeline** (S21.19): virtualized (hàng nghìn event), filter type/agent/tool,
  render `[REDACTED]`. `@tanstack/react-virtual`.

Vì sao React Flow (junior reader): ecosystem chín, nhiều ví dụ agent-graph copy được
(brainstorm §5). Graph là hàm thuần `snapshot.agents[]` → node; **không optimistic
mutate** — chỉ cập nhật sau khi nhận event (S21.18/S21.50).

## Files

**Create (dưới `ui/control-plane/src/`):**
- `components/AgentGraph.tsx` — đọc `TaskLoopSnapshot.agents`, map status→màu node, `onNodeClick`→chọn agent; dedup theo `event_id` (idempotent).
- `components/EventTimeline.tsx` — virtualized list từ stream theo `seq`; filter bar (type/agent/tool); render `ui_payload` với `[REDACTED]` hiển thị literal.
- `state/store.ts` — store nhỏ (useReducer/zustand-lite) gom snapshot + event-log; **chỉ** ghi từ adapter `onEvent`, không từ component.
- `components/__tests__/AgentGraph.test.tsx`, `components/__tests__/EventTimeline.test.tsx`.

**Modify:** `src/App.tsx` (gắn 2 màn + nối adapter stream vào store).

## TDD

### Tests Before (RED — vitest + @testing-library/react)
- [ ] `graph_renders_agent_status` (S21.18): snapshot A=done/B=running/C=pending → 3 node đúng trạng thái/màu. **Khoá:** Graph = hàm thuần snapshot.
- [ ] `graph_idempotent_on_duplicate_event` (S21.18): cùng `event_id` đến 2 lần → graph **không** vỡ/nhân đôi node. **Khoá:** dedup `event_id`.
- [ ] `timeline_virtualized_and_filter` (S21.19): 2000 event → DOM node render << 2000 (virtualized); filter `type=tool.*` lọc đúng. **Khoá:** không dựng toàn bộ DOM.
- [ ] `timeline_shows_redacted` (S21.19): event với field secret đã `[REDACTED]` → hiển thị literal `[REDACTED]`, không giá trị thật. **Khoá:** R3.
- [ ] Run → FAIL (chưa có component).

### Implement
1. `state/store.ts`: reducer `applyEvent`/`setSnapshot`; dedup set `event_id`.
2. `AgentGraph.tsx`: React Flow nodes từ `agents[]`; dagre layout; click→`selectAgent`.
3. `EventTimeline.tsx`: `@tanstack/react-virtual` + filter; render redacted payload.
4. `App.tsx`: `openStream(onEvent=store.applyEvent)`; poll/initial `getSnapshot`.
5. Min code 4 test xanh.

### Tests After (xanh)
- [ ] 4 test trên xanh. `npm run build` (tsc) sạch.

### Regression Gate
`npm --prefix ui/control-plane run test && npm --prefix ui/control-plane run build` → PASS.

## Success
- [ ] Graph hiển thị đúng status mỗi node; duplicate `event_id` không vỡ.
- [ ] Timeline virtualized (DOM << event count) + filter hoạt động + `[REDACTED]` hiện literal.
- [ ] Store chỉ ghi từ adapter (không component mutate trực tiếp — bất biến "UI không sửa state").

## Risks
- **dagre layout với graph lớn chậm** (thấp, T1 ít node): chỉ T1 surface (≤ ~10 agent). Mitigation: layout memoized theo snapshot hash.
- **Virtualization + filter sai count** (tb): test `timeline_virtualized_and_filter` assert số DOM node thực render. Mitigation: dùng API đo của react-virtual.
