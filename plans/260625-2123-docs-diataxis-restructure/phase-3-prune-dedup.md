---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — Strip core explainer + delete mirror + dedup + archive

**Goal**: giữ 4 explainer module lõi (cắt code-block), xoá ~30 mirror-source docs, khử trùng lặp, archive snapshot lịch sử, dọn dir rỗng.

## Step 1 — STRIP + MOVE 4 explainer lõi (module trong KNOWN_RISKS)
Với mỗi file: xoá block `## Toàn bộ nội dung file` + toàn bộ code ```python ... ``` bên dưới (giữ phần văn xuôi giải thích vai trò/invariant), rồi move:
```
core/kernel.md   → explanation/modules/kernel.md
graph/state.md   → explanation/modules/graph-state.md
graph/runtime.md → explanation/modules/graph-runtime.md
safety/sandbox.md→ explanation/modules/safety-sandbox.md
```
> Thêm mỗi file 1 dòng đầu: "Code thật: `<path>.py` · 1-dòng tóm tắt ở `MAP.md`".

## Step 2 — DEDUP
```
git rm docs/architecture/MCP_TOOLS.md                 # byte-identical dup (đã giữ reference/mcp-tools.md)
git mv docs/architecture/LANGGRAPH.md docs/reference/langgraph.md
git rm -r docs/ChatGPTCodex                            # dup encyclopedia
git mv docs/CLASS_ENCYCLOPEDIA.md docs/archive/class-encyclopedia.md
```
> `archive/class-encyclopedia.md`: thêm banner đầu "⚠ SNAPSHOT LỊCH SỬ — trước KernelSession/delegation/control. Không phải sự thật hiện tại."

## Step 3 — DELETE lớp mirror-source (nhúng full code, tái sinh từ MAP)
```bash
git rm docs/core/__init__.md docs/core/bootstrap.md docs/core/events.md docs/core/ports.md \
       docs/core/registry.md docs/core/schemas.md docs/core/state.md
git rm -r docs/discipline docs/features docs/llm docs/observability docs/toolbox docs/tests
git rm docs/graph/__init__.md docs/graph/nodes.md
git rm docs/safety/__init__.md docs/safety/policy.md
git rm docs/config/features.md
```
> core/kernel.md, graph/{state,runtime}.md, safety/sandbox.md đã move ở step 1 → core/, graph/, safety/ còn lại rỗng.

## Step 4 — dọn dir rỗng
```bash
find docs -type d -empty -delete   # core, graph, safety, config, architecture, tools, rebuild_from_zero...
```

## Acceptance
- `explanation/modules/` có 4 file, KHÔNG còn block code đầy đủ (`grep -c "Toàn bộ nội dung file" docs/explanation/modules/*` = 0).
- `docs/architecture/`, `docs/ChatGPTCodex/`, `docs/core/`, `docs/discipline/`, `docs/llm/`, `docs/observability/`, `docs/toolbox/`, `docs/tests/`, `docs/config/`, `docs/tools/`, `docs/rebuild_from_zero/`, `docs/features/`, `docs/graph/`, `docs/safety/` không còn tồn tại.
- `archive/class-encyclopedia.md` có banner historical.
- `find docs -type d -empty` → rỗng.

## Files touched
STRIP+MOVE: 4 · DEDUP: 2 rm + 1 mv + 1 mv · DELETE mirror: ~30 · rmdir rỗng.
