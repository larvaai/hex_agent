---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Scaffold + design-system + Chương 0 (Bản đồ)

> Plan: [plan.md](plan.md) · Brief: [discovery-brief.md](discovery-brief.md)
> Nguồn nội dung: `docs/system-architecture.md` §1,3,12 · `docs/reference/runtime-flow.md` §1

## Mục tiêu

Chốt **template** (skeleton HTML + primitive blocks/arrows/animation) qua chương đơn giản nhất —
Chương 0, toàn cảnh "quốc gia". Đây là phase chốt gu; P2–P4 copy template này.

## Files

- **Tạo** `docs/explanation/learn/README.md` — index: "luật chơi" (nhịp mỗi chương) + link 4 chương.
- **Tạo** `docs/explanation/learn/chapter-0-ban-do.html` — chương map, self-contained.

## Template phải định nghĩa (tài liệu hoá trong README + hiện thân trong chapter-0)

Skeleton 1 file HTML self-contained, các khối theo thứ tự:
1. `<header>` — tên chương + 1 dòng "Nhu cầu".
2. **Hộp câu đố** — câu hỏi hiện; đáp án ẩn sau nút "Lật đáp án" (toggle `hidden`, JS thuần).
3. **Sân khấu** `<svg>` — blocks (rect + label) + arrows (line/path + marker), nút **▶ Play / ⏭ Step**
   chạy một "token" (circle) di chuyển dọc luồng (CSS transition hoặc requestAnimationFrame).
4. (chương sâu) **Bảng `__init__`** — `<table>`: biến → vai trò.
5. (nếu khó) **Hộp "slice"** — `<details>` mở rộng, có snippet tối giản.
6. `<footer>` — evidence link `file:line` + dòng "verify lại nếu sửa file X".

Ràng buộc: inline `<style>`+`<script>`, KHÔNG `src`/`href` ngoài, KHÔNG CDN. CSS variables cho màu/typo.

## Nội dung Chương 0 (CHỈ độ cao khối + mũi tên — KHÔNG tên biến)

Dạy đúng một ý: **cả hệ thống đứng trên 1 cánh cửa + 5 class lõi; mọi epic là plugin quanh nó.**

- **Câu đố mở màn**: "Một agent phải gọi LLM, đọc file, chạy lệnh, giao việc cho agent con — 4 việc rất
  khác nhau. Nếu bạn là kiến trúc sư, bạn cho chúng đi qua **mấy** cánh cửa?" → Lật: **một** cánh cửa
  (`execute_tool` = chokepoint, `docs/GLOSSARY.md:7`). Vì sao một? → để safety/observability/budget
  không bị bypass (`system-architecture.md:34`).
- **Sân khấu**: vẽ 1 cánh cửa trung tâm (`execute_tool`); token "một tool call" bay từ caller → qua cửa →
  ra envelope. Quanh cửa: 10 lớp (theo bảng `system-architecture.md:60-72`) làm khối mờ; bấm vào lớp nào
  highlight + 1 dòng vai trò. Mũi tên thứ 2 (màu khác): delegation = **chokepoint riêng** (không qua cửa
  chính, `system-architecture.md:36,123`).
- Map "nhu cầu → chương": liệt kê 13 chương như lộ trình (đợt này mới có 0–3 sáng, 4–12 mờ "sắp tới").

## Execution steps

1. Tạo `docs/explanation/learn/` (qua Write file đầu tiên — không cần mkdir riêng).
2. Viết `chapter-0-ban-do.html` hiện thân template; test mở browser.
3. Trích template skeleton + "luật chơi" vào `README.md`.
4. Self-check theo Validation.

## Tests / validation

- [ ] Mở `chapter-0-ban-do.html` → 0 lỗi console; ▶ Play chạy token mượt.
- [ ] `grep -iE 'https?://|cdn' chapter-0-ban-do.html` → rỗng (trừ comment/evidence path).
- [ ] Chương 0 KHÔNG chứa tên field/biến (kỷ luật map-first) — đọc rà tay.
- [ ] 10 lớp khớp `system-architecture.md:60-72`; mũi tên delegation tách riêng.
- [ ] README link tới cả 4 chương (chương 1–3 có thể là placeholder tới khi P2–P4 xong).

## Risks + rollback

- Risk: template quá rườm → khó copy. Mitigate: giữ skeleton tối giản, 1 primitive animation tái dùng.
- Rollback: `git rm -r docs/explanation/learn/`.
