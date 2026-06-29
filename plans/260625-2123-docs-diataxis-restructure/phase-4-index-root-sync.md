---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — docs/README.md index + sync root snapshot

**Goal**: viết điểm vào duy nhất cho docs/; đồng bộ README/CHANGELOG/project_context về sự thật hiện tại (user chốt "gom đồng bộ").

## Step 1 — NEW `docs/README.md` (index / bản đồ của bản đồ)
Cấu trúc: bảng 4 trục Diátaxis + spec + roadmap, mỗi mục 1 dòng + link:
- **Bắt đầu**: getting-started.md
- **How-to**: guides/
- **Tra cứu**: reference/ (+ system-architecture.md, code-standards.md ở root docs/)
- **Vì sao**: explanation/ (+ decisions.md)
- **Hợp đồng epic**: spec/done, spec/active
- **Roadmap**: roadmap/project-roadmap.md, roadmap/dependency-map.md, roadmap/future/
- **Lịch sử**: archive/
Thêm "thứ tự đọc cho người mới" (lấy từ codebase-summary §"Thứ tự đọc").

## Step 2 — NEW guides stub (ngắn, rút từ doc đã có)
- `guides/add-a-feature.md`: convention plugin loader — `config/features.yaml` (feature flag) → `features/loader.py` `install(kernel)`. Nguồn: explainer config/features cũ + loader (trước khi xoá ở phase 3, trích ý chính vào đây).
- `guides/run-console-ui.md`: `python -m ui.server` → http://127.0.0.1:8765; endpoints `/api/{bootstrap,runs,snapshot,tree,file,stream}`. Nguồn: codebase-summary.

> Lưu ý thứ tự: trích nội dung 2 stub này TRƯỚC khi phase 3 xoá config/features.md + features/loader.md (hoặc đọc từ source .py). An toàn nhất: viết stub ở phase 4 đọc thẳng từ `config/features.yaml` + `features/loader.py`.

## Step 3 — SYNC `README.md` (root) — rewrite tới hiện tại
Hiện tại: "Sprint 0 / E01–E04" + trỏ `docs/rebuild_from_zero/NEW_REPO_BUILD_GUIDE.md` (KHÔNG tồn tại — link gãy sẵn).
Sửa:
- Trạng thái: E01–E10 done + E19 test harness + E21 active (Phase A+B1). Lấy từ roadmap/project-roadmap.md §"Tóm tắt tình hình".
- Link spec: `docs/rebuild_from_zero/` → `docs/spec/` + `docs/roadmap/`. Bỏ link NEW_REPO_BUILD_GUIDE gãy.
- Trỏ điểm vào: `docs/README.md`, `docs/getting-started.md`.

## Step 4 — SYNC `CHANGELOG.md` — thêm mục thiếu
Entry mới nhất = E08. Thêm 2 mục (lấy từ git log + roadmap):
- **E10 — Multi-agent + Delegation** (commit 4377daa): TaskLoop, DelegationManager chokepoint riêng, session scope inherit.
- **E21 — Realtime Control Plane Phase A + B1** (commits 7998c27, f73d377): contracts + registries; EventEmitter canonical publish path. Ghi rõ transport/UI/reliability pending.

## Step 5 — `project_context.txt` — DELETE (superseded)
Dump cũ 2026-06-16, path Windows `D:\my_agents_v0.3`, đã lỗi thời. `reference/codebase-summary.md` thay thế.
```bash
git rm project_context.txt
```
> Nếu user muốn giữ "context dump" tự sinh: thay bằng note 1 dòng trỏ `docs/reference/codebase-summary.md`. Mặc định: xoá.

## Acceptance
- `docs/README.md` tồn tại, link tới mọi vùng, 0 link gãy.
- `README.md` không còn "Sprint 0 only" + không còn link NEW_REPO_BUILD_GUIDE.
- `CHANGELOG.md` có mục E10 + E21.
- `project_context.txt` đã xoá (hoặc thay note 1 dòng nếu user veto).

## Files touched
NEW: 3 (README + 2 guide) · SYNC: README.md, CHANGELOG.md · DELETE: project_context.txt.
