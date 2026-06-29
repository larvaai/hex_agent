---
plan: project-flow-explainer
slug: project-flow-explainer
created: 2026-06-26 01:43
mode: hard
status: draft
owner: namson.nguyen102@gmail.com
source_brief: plans/260626-0143-project-flow-explainer/discovery-brief.md
decision: none-new (kế thừa DEC-1 Diátaxis — learn/ nằm dưới explanation/)
phases: 4
risk: low-logic / docs-only / không đụng runtime
standards: docs/system-architecture.md, docs/code-standards.md, harness/rules/documentation-management.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Giáo trình tương tác "xây quốc gia" (Chương 0–3)

Thực thi `discovery-brief.md`. Đây là **đợt 1** theo cadence user chốt: build template +
Chương 0–3, lấy feedback, rồi đợt sau mới nhân bản 4–12 + ★ generator. **Không đụng code runtime** —
chỉ sinh tài liệu HTML/markdown trong `docs/explanation/learn/`.

## Expected output (artifact người dùng thấy)

```
docs/explanation/learn/
  README.md                      # index markdown: "luật chơi" + link 4 chương
  chapter-0-ban-do.html          # Toàn cảnh: 1 cánh cửa + 5 class lõi + 10 lớp, blocks+arrows động
  chapter-1-kernel.html          # Nhu cầu "ra lệnh → thi hành": AgentKernel + execute_tool
  chapter-2-session.html         # Nhu cầu "mỗi run có bộ nhớ riêng": KernelSession + State + Factory
  chapter-3-middleware.html      # Nhu cầu "cài hành vi quanh cửa": middleware onion + closure slice
```

Mỗi file `.html` **mở thẳng bằng browser là chạy** — không build step, không CDN, không file ngoài.
README.md là cổng vào (markdown, hợp `docs/`).

## Acceptance criteria (đầu vào → đầu ra nghĩa là "done")

Một chương "done" khi mở `file://.../chapter-N.html` trong browser thì:

1. **Không lỗi console JS** (0 error) và không request mạng nào (grep: không có `http://`/`https://`/`cdn`
   trong `<script src>`/`<link href>`).
2. **Có đúng nhịp sư phạm**: khối "Nhu cầu" (đầu) → câu đố (ẩn đáp án sau nút "Lật") → sân khấu animation
   (blocks + mũi tên, có nút play/step) → (chương sâu) bảng biến `__init__` → (nếu khó) hộp "slice" mở rộng
   → footer evidence link.
3. **Chính xác với code HIỆN TẠI**: mọi claim code trỏ tới `file:line` có thật (verify bằng grep). Đặc biệt
   `AgentKernel` field = `registry/events/config/_middlewares/_frozen` (KHÔNG có `state`/`accept_task` —
   prose cũ `docs/explanation/modules/kernel.md` đã drift, xem §Touchpoints).
4. **Chương 0** chỉ ở độ cao "khối + mũi tên" — KHÔNG nhắc tên biến/field (kỷ luật map-first).
5. **Chương sâu (1–3)** có bảng `__init__` gồm cả field nội bộ (`_frozen`/`_closed`/`_middlewares`).
6. README.md liệt kê đủ 4 chương với link tương đối mở được.

## Scope boundary — OUT (đợt này)

- Chương 4–12 (LLM, discipline, observability, safety, loop, delegation, multi-agent, control plane, resume).
- ★ Skill generator (tái-tạo cho repo bất kỳ) — bài toán mở, có thể cần discovery riêng.
- Sửa drift `docs/explanation/modules/kernel.md` — flag follow-up, không sửa trong plan này.
- Bất kỳ thay đổi code runtime `core_agent`.

## Non-negotiable constraints

| Constraint | Nguồn |
|---|---|
| HTML/SVG/JS thuần, self-contained, no build, no CDN | discovery-brief §2 (user) |
| Markdown chỉ trong `docs/`/`plans/`; HTML đặt `docs/explanation/learn/` | `documentation-management.md:17-23` + DEC-1 |
| Dùng đúng từ glossary (`chokepoint`, …), không đặt tên mới | `docs/GLOSSARY.md:7` |
| File kebab-case (HTML/JS) | CLAUDE.md modularization rule |
| Ngôn ngữ vi; evidence (file:line) giữ nguyên | `harness/data/output.yaml` |
| output_style junior: giải "tại sao trước how", khích lệ | session output_style=1 |
| Nội dung khớp code hiện tại, cite `file:line` | `verification-mechanism.md` |

## Touchpoints (file thật bị đụng / dùng làm nguồn)

**Tạo mới** (5 file, đều trong `docs/explanation/learn/`): README.md + 4 html ở trên.

**Đọc làm nguồn (KHÔNG sửa):**
- `core/kernel.py:14-21,24-30,33-55,63,113,136-138` — kernel, deep_freeze, _wrap, fields, execute_tool, try/except.
- `core/session.py:15-46,49-57,104-186` — SessionIdentity, KernelSession fields, SessionFactory.
- `core/middleware.py:11` — ToolMiddleware protocol.
- `core/registry.py`, `core/schemas.py` — Registry/NullToolPort, envelope `[UNVERIFIED line — confirm in cook]`.
- `docs/system-architecture.md` (§1,3,4,6,12) + `docs/reference/runtime-flow.md` — khung + sơ đồ đã verify (2026-06-25/26).
- `docs/explanation/modules/kernel.md` — **prior art nhưng DRIFTED** (tả field `state`/`accept_task` không còn). Dùng để biết ranh giới, KHÔNG copy.

## Phases

| # | Phase | File | Phụ thuộc |
|---|---|---|---|
| 1 | Scaffold + design-system + Chương 0 (map) | [phase-01-scaffold-and-map.md](phase-01-scaffold-and-map.md) | — |
| 2 | Chương 1 — kernel + execute_tool | [phase-02-chapter-kernel.md](phase-02-chapter-kernel.md) | P1 (template) |
| 3 | Chương 2 — session + state | [phase-03-chapter-session.md](phase-03-chapter-session.md) | P1 |
| 4 | Chương 3 — middleware onion + closure slice | [phase-04-chapter-middleware.md](phase-04-chapter-middleware.md) | P1 |

Phase 1 chốt template (skeleton + primitive blocks/arrows/animation). P2–P4 copy template, độc lập nhau
→ có thể làm song song sau P1, nhưng cook tuần tự để giữ feedback loop.

## Decisions (plan-level, không phải DEC kiến trúc)

1. **Self-contained inline HTML** (không shared CSS file) — honor "no build/no CDN/mở browser là chạy".
   Trade-off: lặp CSS giữa các file; mitigate: template tài liệu hoá + ★ generator tái sinh (không sửa tay).
2. **Index = README.md markdown** (không index.html) — hợp cây `docs/`, mở được trên GitHub.
3. **Visual primitive** = SVG block + SVG/CSS arrow + JS step-animation (token chạy qua flow); không lib physics.
4. **Vị trí** `docs/explanation/learn/` — dưới nhánh explanation/ của DEC-1 Diátaxis.

→ Không tạo DEC mới: đây là quyết định artifact tài liệu, không phải kiến trúc hệ thống. Nếu human muốn
ghi sổ #1 (inline-HTML) thì append DEC khi approve.

## Red-team (inline — proportionate)

Task docs-only, reversible, blast radius runtime = 0 → không spawn red-teamer agent (token-efficiency).
Adversarial sweep inline, failure modes + mitigation:

| Failure mode | Mitigation trong plan |
|---|---|
| Copy nhầm prose drift (`kernel.md`) → dạy sai field | AC#3 ép verify field hiện tại bằng grep; touchpoints đánh dấu kernel.md DRIFTED |
| Chương 0 sa đà chi tiết → mất tác dụng định hướng | AC#4 cấm tên biến ở Chương 0 |
| "Bẫy budget": dạy budget là middleware (sai) khi nó ở graph node | Note xuống P chứa budget (đợt sau); đợt này 0–3 không chạm budget → an toàn |
| Animation đẹp nhưng sai luồng (AI-slop) | AC#1+#3: flow phải khớp `execute_tool` thật (publish→scope→onion→core→publish) |
| CSS lặp 4 file khó bảo trì | Decisions#1: template hoá + generator tái sinh |
| Slice closure (P4) giải hụt | P4 yêu cầu snippet tối giản CHẠY ĐƯỢC minh hoạ bug late-binding |

## Risks + rollback

- **Risk**: format/gu sai sau khi build cả 4 → phải sửa lại. **Mitigation**: P1 chốt template + Chương 0
  (đơn giản nhất) trước; review template trước khi P2–P4.
- **Risk**: drift tương lai khi code đổi. **Mitigation**: footer mỗi chương cite `file:line` + câu
  "verify lại nếu sửa file X".
- **Rollback**: docs-only → `git rm docs/explanation/learn/` + `git checkout` là sạch. Không ảnh hưởng runtime/test.

## Evidence filter

Mọi claim code trong phase files có `file:line`. Chỗ chưa mở file (registry/schemas nội bộ) gắn
`[UNVERIFIED — confirm in cook]`. Cook phải resolve tag trước khi viết nội dung liên quan.
