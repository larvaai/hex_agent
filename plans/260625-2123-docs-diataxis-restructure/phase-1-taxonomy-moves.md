---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Skeleton + taxonomy moves (Diátaxis 4 trục)

**Goal**: dựng cây thư mục đích + move lớp navigation/reference/explanation/guides/tutorial; fix link nội bộ giữa các file đã move.

## Step 0 — skeleton (mkdir trước để git mv không lỗi)
```bash
cd docs
mkdir -p guides reference/assets explanation/modules spec/done spec/active roadmap/future archive
```

## Step 1 — MERGE tutorial
- Gộp `HOW_TO_FOLLOW.md` + `run_smoke.md` → `getting-started.md` (giữ phần "5 lớp dẫn đường" + "thứ tự đọc" của HOW_TO_FOLLOW, nối "Kiểm tra nhanh" của run_smoke). Xoá 2 file gốc sau khi gộp.

## Step 2 — MOVE reference (git mv)
```
git mv docs/RUNTIME_FLOW.md       docs/reference/runtime-flow.md
git mv docs/KNOWN_RISKS.md        docs/reference/known-risks.md
git mv docs/codebase-summary.md   docs/reference/codebase-summary.md
git mv docs/MCP_TOOLS.md          docs/reference/mcp-tools.md
git mv docs/class_dependency.mermaid docs/reference/assets/class_dependency.mermaid
```
> `architecture/LANGGRAPH.md` → reference/langgraph.md xử lý ở phase 3 (cùng cụm dedup `architecture/`).

## Step 3 — MOVE explanation + guides
```
git mv docs/project-overview-pdr.md            docs/explanation/overview-pdr.md
git mv docs/rebuild_from_zero/CYCLE_E07_E09_skill_role.md docs/explanation/design-decisions.md
git mv docs/tools/gen_map.md                    docs/guides/regenerate-map.md
```
> `explanation/design-decisions.md`: thêm 1 dòng đầu trỏ `../decisions.md` (DEC register) để gom "vì-sao quyết định" về một chỗ.

## Step 4 — GIỮ nguyên (KHÔNG move)
`docs/system-architecture.md`, `docs/code-standards.md` (standards contract), `docs/decisions.md`, `docs/project-roadmap.md` (move ở phase 2).

## Step 5 — fix link nội bộ giữa file vừa move
Grep + sửa đường dẫn tương đối đã đổi tầng:
```bash
grep -rnE "\]\(\.?\.?/?(HOW_TO_FOLLOW|RUNTIME_FLOW|KNOWN_RISKS|codebase-summary|MCP_TOOLS|project-overview-pdr|run_smoke|tools/gen_map)" docs/
```
- `reference/codebase-summary.md` trỏ `./HOW_TO_FOLLOW.md` → `../getting-started.md`; `./RUNTIME_FLOW.md` → `./runtime-flow.md`; `./KNOWN_RISKS.md` → `./known-risks.md`; `./rebuild_from_zero/` → `../spec/` (path phase-2); `../plans/reports/architecture-map…` giữ nguyên (đúng).
- `getting-started.md` trỏ `MAP.md`/`RUNTIME_FLOW.md`/`CHANGELOG.md` → `../MAP.md`, `reference/runtime-flow.md`, `../CHANGELOG.md`.

## Acceptance
- `docs/getting-started.md` tồn tại, 2 file gốc biến mất.
- `reference/`, `explanation/`, `guides/` chứa đúng file theo trên.
- Grep step 5 trả 0 link trỏ path cũ trong các file đã move.

## Files touched
MOVE: 8 · MERGE: 2→1 · link-fix: reference/codebase-summary.md, getting-started.md.
