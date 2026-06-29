---
plan: docs-diataxis-restructure
slug: docs-diataxis-restructure
created: 2026-06-25 21:23
mode: hard
status: in_progress
owner: namson.nguyen102@gmail.com
source_report: plans/reports/docs-structure-260625-2123-diataxis-restructure-report.md
roadmap_report: plans/reports/roadmap-living-notes-260625-2308-future-epics-critique-report.md
decision: DEC-1, DEC-3, DEC-4, DEC-5
phases: 5
risk: low-logic / high-file-count
standards: docs/system-architecture.md, docs/code-standards.md, harness/rules/documentation-management.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Cấu trúc lại `docs/` theo Diátaxis-hybrid

Thực thi DEC-1 (xem report nguồn). Reorg tài liệu thuần: move / merge / delete / strip + sync root snapshot.
Không đổi logic code; chỉ sửa **docstring/comment trỏ đường dẫn doc** + viết tài liệu.

## Expected output (artifact người dùng thấy)

Cây `docs/` sau reorg:

```
docs/
  README.md                 # NEW index
  getting-started.md        # MERGE HOW_TO_FOLLOW + run_smoke
  system-architecture.md    # GIỮ root (standards contract)
  code-standards.md         # GIỮ root (standards contract)
  decisions.md              # GIỮ (DEC register, đã có)
  guides/                   # regenerate-map, add-a-feature, run-console-ui
  reference/                # runtime-flow, known-risks, codebase-summary, mcp-tools, langgraph, assets/ (MAP giữ root; docs/README.md trỏ tới)
  explanation/              # overview-pdr, design-decisions, modules/{kernel,graph-state,graph-runtime,safety-sandbox}
  spec/                     # done/{E08-rag,E10-multi-agent-graph}  active/{E21-realtime-control-plane}
  roadmap/                  # README(living index+Thaw Protocol), project-roadmap, dependency-map, THRESHOLDS, future/{E11,E12,E13,E14,E20} = LIVING NOTE (E15 gộp E21)
  archive/                  # class-encyclopedia (historical)
```
Root: `README.md` + `CHANGELOG.md` synced về sự thật hiện tại (E01–E10 done, E21 active). `MAP.md` ở root (auto-gen).

## Acceptance criteria (đầu vào → đầu ra nghĩa là "done")

1. `python tools/gen_map.py` chạy sạch, `MAP.md` regenerate ở root.
2. `python run_smoke.py` in `CORE_AGENT_SMOKE_OK`.
3. `python -m pytest` + `python -m pytest tests_audit` xanh hết (chứng minh sửa docstring không phá gì).
4. Audit link nội bộ: 0 link `.md` gãy trong `docs/` + `README.md` + `CHANGELOG.md` (grep `](` + path refs).
5. Mọi `.md` nằm trong `docs/` (trừ root `README.md`, `CHANGELOG.md`) — giữ md-location invariant.
6. Cây `docs/` khớp Expected output; `git status` cho thấy rename (history preserved qua `git mv`).
7. 5 docstring cross-ref (rag/skills/control/supervisor `__init__.py`, tests/test_rag.py) trỏ path mới, đúng.
8. `roadmap/future/` có **5 living note** (E11,E12,E13,E14,E20 — KHÔNG E15), mỗi note đủ 8 trường + `wiring_threshold` đo được; `roadmap/README.md` (Thaw Protocol + vòng đời) + `roadmap/THRESHOLDS.md` (lệnh đếm + hàng đo hôm nay) tồn tại; `dependency-map.md` đã sửa map-drift E15 (E16→E21).

## Scope boundary — OUT vòng này

- KHÔNG đổi logic/hành vi code (chỉ comment/docstring path).
- KHÔNG sửa `harness/` (trừ xác nhận standards contract — read-only).
- KHÔNG viết lại nội dung doc CŨ (chỉ move + sync snapshot + strip code-block). NGOẠI LỆ: `roadmap/future/` living note + `roadmap/{README,THRESHOLDS}.md` là nội dung MỚI, nguồn = report roadmap-living-notes (đã critique sẵn, không sáng tác thêm).
- E15 KHÔNG có living note (verdict merge-into-other → gộp E21); chỉ ghi nhận trong dependency-map + project-roadmap.
- KHÔNG tạo `docs/GLOSSARY.md` (không coin term mới; "Diátaxis" là term ngành).
- KHÔNG move `system-architecture.md` / `code-standards.md` (standards contract — giữ root).
- E07/E09 acceptance refs trong `tests/test_roles.py`, `tests/test_skills.py` đã stale sẵn (folder không tồn tại) — KHÔNG fix vòng này.

## Non-negotiable constraints

- Stack: Python repo, doc tiếng Việt (output.yaml `language: vi`).
- `MAP.md` giữ root (user chốt) → `tools/gen_map.py` không sửa.
- `docs/system-architecture.md` + `docs/code-standards.md` giữ path cũ (`harness/standards/README.md` self-hosting contract).
- Dùng `git mv` (preserve history) cho mọi MOVE.
- md chỉ trong `docs/`/`plans/` (+ root README/CHANGELOG) — CLAUDE.md rule.

## Touchpoints (file/contract bị sửa)

| Loại | File |
|---|---|
| MOVE (git mv) | ~12 doc → reference/explanation/guides/roadmap/archive (xem phase 1–2) |
| MERGE | HOW_TO_FOLLOW.md + run_smoke.md → getting-started.md |
| STRIP+MOVE | core/kernel.md, graph/state.md, graph/runtime.md, safety/sandbox.md → explanation/modules/ |
| DELETE | ~30 per-module mirror docs + architecture/MCP_TOOLS.md (dup) + ChatGPTCodex/ (dup) |
| NEW | docs/README.md, guides/{add-a-feature,run-console-ui}.md, roadmap/{README,THRESHOLDS}.md, roadmap/future/{E11,E13,E14,E20}.md (living note); roadmap/future/E12 = move PRD + prepend living note |
| EDIT (doc) | roadmap/dependency-map.md (map-drift E15: E16→E21), roadmap/project-roadmap.md (E15 gộp E21) |
| CODE (comment-only) | rag/__init__.py:6, tests/test_rag.py:3, skills/__init__.py:8, control/__init__.py:7, supervisor/__init__.py:6 |
| ROOT sync | README.md (rewrite tới E10+E21), CHANGELOG.md (+E10,+E21), project_context.txt (delete — superseded) |

## Phase index

1. [phase-1-taxonomy-moves.md](phase-1-taxonomy-moves.md) — skeleton + move reference/explanation/guides/tutorial + fix link nội bộ
2. [phase-2-spec-roadmap.md](phase-2-spec-roadmap.md) — spec/done|active + roadmap/+future + sửa 5 docstring cross-ref
3. [phase-3-prune-dedup.md](phase-3-prune-dedup.md) — strip 4 core explainer + delete ~30 mirror + dedup + archive
4. [phase-4-index-root-sync.md](phase-4-index-root-sync.md) — docs/README.md index + sync README/CHANGELOG/project_context
5. [phase-5-verify-gate.md](phase-5-verify-gate.md) — gen_map + smoke + pytest + link audit + invariant

## Red-team findings (inline — đã áp vào phase)

- **R1 Link gãy hàng loạt**: doc cross-link đường dẫn tương đối → MOVE phá link. *Mitigation*: mỗi phase MOVE kèm bước grep-fix link; phase 5 audit toàn cục (AC #4).
- **R2 Docstring source trỏ doc cũ**: 5 file `.py`. *Mitigation*: phase 2 sửa đồng thời khi move spec; pytest (AC #3) bắt regression.
- **R3 Move standards file phá harness contract**: *Mitigation*: constraint-scan đã chốt GIỮ root (constraint), loại khỏi move-list.
- **R4 Xoá nhầm doc còn giá trị**: lớp per-module nhúng full code → nội dung tái sinh từ code + MAP. *Mitigation*: 4 explainer lõi (KNOWN_RISKS modules) được STRIP-giữ, không xoá; phần xoá là mirror thuần.
- **R5 `git mv` vào dir chưa tồn tại**: *Mitigation*: phase 1 step 0 `mkdir -p` toàn bộ skeleton trước.
- **R6 Empty dir sót lại** (core/, discipline/…): *Mitigation*: phase 3 cuối `find docs -type d -empty -delete`.

## Rollback

Toàn bộ là thao tác file git-tracked. Hỏng → `git restore --staged --worktree docs/ README.md CHANGELOG.md project_context.txt rag/__init__.py skills/__init__.py control/__init__.py supervisor/__init__.py tests/test_rag.py` (hoặc `git reset --hard` nếu chưa commit). Không có migration DB / state.

## Verification gate (phase 5 chi tiết)

`python tools/gen_map.py` → `python run_smoke.py` → `python -m pytest && python -m pytest tests_audit` → link audit → `find . -name '*.md' -not -path './docs/*' -not -path './plans/*' -not -path './harness/*' -not -name README.md -not -name CHANGELOG.md` (phải rỗng).
