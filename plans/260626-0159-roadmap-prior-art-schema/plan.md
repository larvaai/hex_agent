---
plan: roadmap-prior-art-schema
slug: roadmap-prior-art-schema
created: 2026-06-26 01:59
mode: fast
status: draft
owner: namson.nguyen102@gmail.com
source_brief: plans/reports/brainstorm-260626-0159-prior-art-schema-committee-agent-report.md
decision: DEC-7 (prior_art external-anchor schema) + DEC-8 (Committee-Agent đặt nhà E21)
phases: 2
risk: low / docs-only / không đụng runtime
standards: docs/system-architecture.md, docs/code-standards.md, harness/rules/documentation-management.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Wire DEC-7 + DEC-8 vào docs/roadmap

Áp 2 quyết định đã chốt (xem [decisions.md](../../docs/decisions.md) DEC-7, DEC-8) vào hệ roadmap.
**Thuần docs — KHÔNG đụng code runtime.** Nguồn nội dung:
[brainstorm report §2 + §3.1](../reports/brainstorm-260626-0159-prior-art-schema-committee-agent-report.md).

DEC-8 đã chốt nhà = E21 — **KHÔNG relitigate E21-vs-E22** trong khi thực thi (đọc DEC-8 trước nếu tension tái xuất).

## Expected output (artifact người dùng thấy)

```
docs/roadmap/README.md               # schema 8→9 trường (thêm prior_art 3b); §6 bảng +1 dòng; §7 anti-rot +prior_art
docs/roadmap/THRESHOLDS.md           # ghi chú maintenance: prior_art = external anchor, refresh checked:date, KHÔNG phải trigger
docs/roadmap/future/committee-agent.md  # note 9-trường MỚI (E21, park-with-trigger)
docs/GLOSSARY.md                     # +2 hàng: "external anchor", "Committee-Agent"
```

## Acceptance criteria (đầu vào → đầu ra nghĩa là "done")

1. `docs/roadmap/README.md` §3 liệt kê **9 trường** với `prior_art` ở vị trí **3b** (ngay sau `current_anchors`);
   có khuôn `<tên> — <URL> — mechanism:"<nguyên-lý>" — checked:<date>`; ghi rõ 3 luật:
   (a) proof-of-FEASIBILITY ≠ proof-of-NEED, (b) prior-art KHÔNG bao giờ là thaw-trigger,
   (c) `critique` BẮT BUỘC có dòng `proven-elsewhere != needed-here`.
2. `README.md` §7 anti-rot: thêm 1 gạch đầu dòng — refresh `prior_art.checked:date` đi cùng nhịp refresh `current_anchors`.
3. `README.md` §6 bảng trạng thái: +1 dòng `Committee-Agent | park-with-trigger | future | — | E21 (observe) + E10 (core) | 2026-06-26`.
4. `THRESHOLDS.md`: ghi chú ngắn — prior_art là external anchor, refresh theo `checked:date`, **KHÔNG** thêm lệnh đếm/ngưỡng trigger cho nó.
5. `docs/roadmap/future/committee-agent.md` tồn tại, đủ **9 trường**, anchors `file:line` verbatim từ report §3.1,
   3 `prior_art` (MoA/Self-Refine/Least-to-Most) có `mechanism`+`url`+`checked:2026-06-26`,
   `dependencies` ghi rõ carve (E21 sở hữu observe/redact/trash; core fan-out+aggregate = orchestration, gate-in E10).
6. `docs/GLOSSARY.md` có 2 hàng mới: `external anchor`, `Committee-Agent`.
7. Triết lý `deps 🟢 = được phép ≠ nên` giữ nguyên; evidence (file:line, URL) verbatim; prose tiếng Việt (output.yaml `vi`).

## Scope boundary (OUT đợt này)

- KHÔNG đụng code (`supervisor/`, `control/`, `graph/`...). Chỉ docs.
- KHÔNG hồi cứu sửa 5 note future cũ (E11–E14, E20) để thêm `prior_art` — schema mới optional cho note cũ, chỉ áp khi có prior-art thật. Ghi nhận là việc sau (không phải đợt này).
- KHÔNG tạo epic E22, KHÔNG sửa `project-roadmap.md` epic list (DEC-8: nhà = E21).
- KHÔNG build committee-agent (vẫn `park-with-trigger`).

## Phases

- [phase-1-schema.md](phase-1-schema.md) — README §3/§7 + THRESHOLDS + GLOSSARY (external anchor)
- [phase-2-committee-note.md](phase-2-committee-note.md) — tạo committee-agent.md + README §6 + GLOSSARY (Committee-Agent)

## Rollback

Thuần docs, không migration, không runtime. Hỏng → `git checkout -- docs/roadmap/ docs/GLOSSARY.md` hoặc revert commit. Không có state/CI phụ thuộc.

## Verification (fast — không CI gate)

- `grep -nE 'prior_art' docs/roadmap/README.md` → thấy 3b + 3 luật.
- `test -f docs/roadmap/future/committee-agent.md && grep -c '^## ' docs/roadmap/future/committee-agent.md` → ≥9 mục.
- `grep -c 'external anchor\|Committee-Agent' docs/GLOSSARY.md` → 2.
- Đọc tay: §6 bảng có dòng Committee-Agent; THRESHOLDS không có lệnh-đếm-trigger cho prior_art.
