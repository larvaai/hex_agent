---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — Spec (done/active) + Roadmap (future) + sửa docstring cross-ref

**Goal**: tách epic spec theo trạng thái; gom forward-looking vào roadmap/; sửa 5 docstring source trỏ path mới.

## Step 1 — MOVE spec đã-done
```
git mv docs/rebuild_from_zero/E08_rag                docs/spec/done/E08-rag
git mv docs/rebuild_from_zero/E10_multi_agent_graph  docs/spec/done/E10-multi-agent-graph
```
(flow_taskloop.mermaid đi theo trong E10 folder — giữ nguyên trong.)

## Step 2 — MOVE spec active
```
git mv docs/rebuild_from_zero/E21_realtime_control_plane docs/spec/active/E21-realtime-control-plane
```

## Step 3 — MOVE roadmap + sửa map drift
```
git mv docs/project-roadmap.md                                   docs/roadmap/project-roadmap.md
git mv docs/rebuild_from_zero/01_BUILD_ORDER_AND_DEPENDENCIES.md  docs/roadmap/dependency-map.md
```
- `roadmap/dependency-map.md` — **SỬA MAP DRIFT (DEC-4)**: dòng `E15 Self-eval & Governance | P4 | E04, E10, E16` → `E04, E10, E21` (E16 đã gộp E21); thêm dòng ghi rõ "E15 self-eval đã gộp vào E21 (verdict merge-into-other) — không còn epic future độc lập". Thêm chú thích đầu "E16+E17+E18 đã gộp → E21" + bảng cổng phụ thuộc future (🟢 E11/E13/E14 gate-in / 🔴 gate-out chờ E12 · 🔴 E12 chờ E11+E13 · ⚪ E20 cổng-thời-điểm) lấy từ report §TL;DR.
- `roadmap/project-roadmap.md`: đánh dấu E15 "đã gộp vào E21".
- `rebuild_from_zero/` còn rỗng sau khi rút PRD (Step 4a) → xoá ở phase 3.

## Step 4 — roadmap/future = LIVING NOTE + index + sổ ngưỡng (KHÔNG phải stub)
> Nguồn nội dung: `plans/reports/roadmap-living-notes-260625-2308-future-epics-critique-report.md` (đã critique, bám file:line). E15 KHÔNG có note — đã gộp E21.

**4a. 5 living note** `roadmap/future/{E11-departments, E12-router-supervisor, E13-software-factory, E14-ledger-memory, E20-labs}.md`.
Mỗi note có ĐỦ 8 trường: `problem_solved` · `why_not_now` · `current_anchors` (file:line verbatim) · `wiring_threshold` (đo được, không mơ hồ) · `wiring_sketch` (seam file:line) · `dependencies` (gate) · `critique` (YAGNI / risks-built / risks-skipped) · `verdict`.
- **E12**: `git mv` PRD cũ vào vị trí TRƯỚC, rồi PREPEND living note lên đầu, giữ PRD gốc bên dưới mục `## Spec gốc (PRD draft)` để không mất chi tiết:
  ```
  git mv docs/rebuild_from_zero/E12_intent_router_supervisor/PRD.md docs/roadmap/future/E12-router-supervisor.md
  ```
- **E11/E13/E14/E20**: viết mới từ report (không có PRD trước).

**4b. `roadmap/README.md` (NEW)** — living index: roadmap là gì (kho lạnh có nhãn-ngưỡng; "deps 🟢 = *được phép* ≠ *nên*") · cách đọc 1 note (verdict→threshold→deps→sketch) · **VÒNG ĐỜI** `future→triggered→planned→active→done` + nhánh `merge-into-other` / `block-on:<epic>` · **THAW PROTOCOL** (giao thức rã đông 6 bước) · bảng trạng thái (cả 5 ở `future`). Nguồn: report §"Thaw Protocol" + §"Dàn ý README".

**4c. `roadmap/THRESHOLDS.md` (NEW)** — sổ ngưỡng thủ công: các lệnh đếm + bảng `{ngày đo | metric | giá trị | ngưỡng | đã chạm?}`. Điền hàng hôm nay: 2 dept · 4 role · 1 owns_validation:false · 0 run · 0 resume-call-site (đều CHƯA chạm). Nguồn: report §"Thaw Protocol Bước 0".

## Step 5 — sửa 5 docstring/comment cross-ref (comment-only, KHÔNG đổi logic)
```
rag/__init__.py:6        docs/rebuild_from_zero/E08_rag/BUILD_PLAN.md         → docs/spec/done/E08-rag/BUILD_PLAN.md
tests/test_rag.py:3      docs/rebuild_from_zero/E08_rag/acceptance.md         → docs/spec/done/E08-rag/acceptance.md
skills/__init__.py:8     docs/rebuild_from_zero/CYCLE_E07_E09_skill_role.md   → docs/explanation/design-decisions.md
control/__init__.py:7    docs/rebuild_from_zero/E21_realtime_control_plane/   → docs/spec/active/E21-realtime-control-plane/
supervisor/__init__.py:6 docs/rebuild_from_zero/E10_multi_agent_graph/        → docs/spec/done/E10-multi-agent-graph/
```
> Chỉ sửa chuỗi path trong docstring/comment. Không chạm dòng đầu docstring (gen_map đọc dòng đầu — các ref này ở dòng 6–8, an toàn).

## Step 6 — fix link nội bộ trỏ rebuild_from_zero
```bash
grep -rnE "rebuild_from_zero" docs/ README.md
```
Sửa mọi `rebuild_from_zero/Exx` → `spec/{done|active}/...` hoặc `roadmap/...` tương ứng (đặc biệt `roadmap/project-roadmap.md`, `reference/codebase-summary.md`, `getting-started.md`).

## Acceptance
- `spec/done/{E08-rag,E10-multi-agent-graph}` + `spec/active/E21-realtime-control-plane` đầy đủ file.
- `roadmap/` có project-roadmap, dependency-map, README.md, THRESHOLDS.md, future/ với **5 living note** (E11,E12,E13,E14,E20 — KHÔNG E15).
- Mỗi living note có đủ **8 trường** + ≥1 `file:line` anchor thật; `wiring_threshold` đo được (có số/lệnh đếm).
- `roadmap/dependency-map.md`: dòng E15 = `E04, E10, E21` (không còn E16); có ghi chú E15 gộp E21.
- `roadmap/THRESHOLDS.md` có lệnh đếm + ≥1 hàng đo ngày hôm nay.
- `grep -rn rebuild_from_zero .` → 0 (trừ lịch sử git).
- 5 docstring trỏ path mới; `python -m pytest tests/test_rag.py` xanh.

## Files touched
MOVE: 6 (E08, E10, E21, project-roadmap, dependency-map, E12-PRD) · NEW: 6 (4 living note E11/E13/E14/E20 + README + THRESHOLDS) · EDIT: dependency-map map-drift + project-roadmap E15-fold · CODE comment: 5 file · link-fix: roadmap + cross.
