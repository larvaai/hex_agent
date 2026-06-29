---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — Chương 3: Middleware onion + closure slice

> Plan: [plan.md](plan.md) · Template: [phase-01-scaffold-and-map.md](phase-01-scaffold-and-map.md)
> Nguồn: `core/middleware.py` · `core/kernel.py:24-30,57-61,136-138` · `system-architecture.md` §4

## Mục tiêu

Nhu cầu #2: *"Cài thêm hành vi quanh cửa mà KHÔNG sửa cửa."* (đây chính là "hook / before-after" user hỏi)
→ sinh ra `ToolMiddleware` + onion. Đây là chương có **slice khó nhất**: bẫy late-binding closure.

## Nội dung (khớp code hiện tại)

**Câu đố 1**: "Bạn muốn mỗi tool call được: đo giờ → check policy → giới hạn → log. Bạn nhét 4 việc đó vào
`execute_tool`? Hay làm sao thêm/bớt mà không đụng kernel?" → Lật: middleware — mỗi lớp là
`__call__(request, nxt)`, bọc quanh core như vỏ củ hành ([core/middleware.py:11-15](../../core/middleware.py)).

**Bảng "biến/khái niệm"** của onion ([core/kernel.py:33-46,136-138](../../core/kernel.py)):

| Thứ | Vai trò |
|---|---|
| `_middlewares: list` | danh sách lớp, đăng ký qua `use()` ([core/kernel.py:57-61](../../core/kernel.py)) |
| `nxt: ToolHandler` | "lớp kế bên trong" mà mỗi middleware gọi |
| `core` | nhân thật (resolve→execute→envelope), lớp trong cùng |
| order | đăng ký ngoài→trong; bọc `reversed` ([core/kernel.py:136-138](../../core/kernel.py)) |

**Câu đố 2 (cốt lõi slice)**: "Đăng ký theo thứ tự A, B, C. Vì sao code bọc bằng `reversed`? Và nếu viết
vòng `for mw in middlewares: handler = lambda req: mw(req, handler)` thì hỏng ở đâu?" → Lật: late-binding
closure — `handler` trong lambda bị bind trễ, mọi lambda trỏ cùng `handler` cuối. `_wrap()` tạo scope riêng
để cắt bug ([core/kernel.py:24-30](../../core/kernel.py)).

**Slice — onion + late-binding** (`<details>`, BẮT BUỘC có snippet CHẠY ĐƯỢC):
- Snippet A (sai): vòng lambng trực tiếp → in ra cho thấy mọi lớp gọi nhầm lớp cuối.
- Snippet B (đúng): `_wrap(mw, nxt)` → mỗi lớp giữ đúng `nxt` của mình.
- 6–8 dòng Python tối giản, không phụ thuộc repo, chạy `python3 -c` ra kết quả khác nhau.

**Sân khấu**: animate token đi VÀO qua các lớp (timing→policy→…→core) rồi đi RA ngược lại — đúng hình củ
hành. Cho phép 1 lớp "short-circuit" (return không gọi `nxt`) minh hoạ policy chặn
([core/middleware.py:12-13](../../core/middleware.py)).

> ⚠️ Đừng dạy budget là middleware ở đây nếu gây nhầm: `BudgetGuard` còn có bản ở **graph node**
> ([system-architecture.md:308](../../docs/system-architecture.md)). Chương này chỉ nói cơ chế onion
> chung; ví dụ lớp dùng timing/policy cho an toàn.

## Execution steps

1. Viết + CHẠY THẬT 2 snippet closure (`python3 -c "..."`) để chắc chúng minh hoạ đúng bug; dán output vào.
2. Copy template P1 → điền nội dung.
3. Self-check Validation.

## Tests / validation

- [ ] 0 lỗi console; animation onton vào-ra + short-circuit chạy.
- [ ] Snippet A/B chạy thật ra 2 kết quả khác nhau (chứng minh late-binding) — output dán trong trang.
- [ ] `file:line` footer trỏ thật (đặc biệt `core/kernel.py:24-30,136-138`).
- [ ] No CDN/external.

## Risks + rollback

- Risk: slice closure giải hụt → hiểu sai. Mitigate: bắt buộc 2 snippet chạy được, đối chiếu output.
- Risk: nhầm budget middleware/graph-node. Mitigate: note ở trên, tránh ví dụ budget.
- Rollback: `git rm chapter-3-middleware.html`.
