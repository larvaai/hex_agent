---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Design spec (final) — multi-lens advisory cho drag_from_zero

Ngày 2026-06-28 · Nguồn: brainstorm + workflow 4-lens + 3 vòng user refine · DEC-17 (shape A) + DEC-18 (design).
Bản GỌN: đã bỏ budget/cap/unlimited/echo-detector/fixed-order/free-pick-thay-combo theo chỉ đạo user (chạy **local** + user **tự kiểm soát** chất lượng lens và quyền).

## Khung

Role-conditioned ensemble trên MỘT base 35B + optional cascade synthesis (MoA-lite). Lens = góc nhìn **ADVISORY**; **agent chốt output**, lens chỉ góp giọng. Prior-art: MoA arXiv:2406.04692 (aggregator synthesize > select → validate cascade). Risk số 1 = monoculture/echo (arXiv:2605.00914) — user **chấp nhận** vì tự kiểm soát lens, không cần máy dò.

## Model 3 lớp

### CONFIG (user viết, load-once-frozen)
- `lens` = {id, prompt} — 1 câu hỏi 35B-trivial → 1 dòng ra.
- `combo` = list lens (có thể gồm 1 lens "tổng hợp" đọc lens khác); gán cho 1 hệ.
- `hệ` = attr trên agent node (topology Node.attrs — đã mở sẵn).
- `enabled` mỗi hệ, **default true** (bắt buộc chạy combo).

### PERMISSION (HARD-CODE vào capability.py — "Gate đọc token, không đọc lời agent", orchestrator.py:233)

| Rule | Ai | Cơ chế |
|---|---|---|
| quyền consult (gọi lens) | agent **có** · lens **không** | capability flag |
| ép chạy combo nếu thuộc hệ X + enabled | CODE ép, agent **không skip được** | dispatch logic |
| toggle `enabled` | **chỉ user** | by-construction: config frozen → agent vật lý không có đường ghi |

### RUNTIME
1. Agent hệ X + enabled → CODE chạy combo X (**bắt buộc**).
2. Agent muốn → gọi **thêm** lens ngoài combo (quyền của nó; named từ catalog, unknown bị drop không crash).
3. Mỗi lens = 1 call 35B → 1 dòng → **log 1 event** (LENS_QUERIED/RETURNED, **không** field verdict). Lens thử consult → bị từ chối như tool ngoài capability (**TOOL_DENIED reuse**).
4. Tất cả dòng (combo + extra) về agent → **agent chốt**.

## Cascade synthesis (điểm DUY NHẤT chạm no-forge)

Lens tổng hợp đọc dòng lens khác → nhìn giống kẻ kết luận. Giữ propose-only bằng **1 luật**: **agent luôn nhận TẤT CẢ dòng thô + dòng tổng hợp; không bao giờ thay raw bằng mỗi dòng tổng hợp.** Tổng hợp = 1 giọng nữa, không phải verdict. Thứ tự: tổng hợp chạy SAU input nó đọc — **phụ thuộc dữ liệu**, không phải luật order.

## Thứ tự lens KHÔNG cố định

Lens độc lập → order không đổi input agent (agent thấy hết dòng). Chỉ cascade có phụ thuộc dữ liệu. Caveat test: muốn replay y hệt thì key recorded-response theo **lens-id** (không theo call-order).

## OUT (bỏ — có lý do)

- budget / cap N / unlimited / hard_backstop → combo hữu hạn + local → không tốn tiền, không lo cạn.
- echo-detector thông minh → user kiểm soát chất lượng; chỉ giữ log thường mỗi lens.
- free-pick THAY combo → combo bắt buộc; agent chỉ **thêm**, không thay.
- fixed lens order → user bỏ.

## Acceptance criteria

1. **Empty-by-default:** không hệ/combo → `tools.names()` + event stream byte-identical; suite cũ pass nguyên; consult không tiêu AttemptBudget (orchestrator.py:373).
2. **Permission hard-code:** lens không có consult cap (thử → TOOL_DENIED); agent có. Test: lens cố consult bị chặn.
3. **Mandate:** agent hệ X + enabled → combo chạy, agent không skip; enabled=false (user set) → không chạy; agent không flip được enabled.
4. Agent gọi **thêm** lens ngoài combo được; unknown lens id drop, không crash.
5. **Cascade:** agent nhận TẤT CẢ dòng thô; synthesis append, không thay thế; synthesis chạy sau input. Test: combo có synthesis → log có cả raw lẫn synthesis.
6. Lens output **không** field verdict/route (mirror FORBIDDEN_VERDICT_KEYS verifier.py:26); mỗi lens 1 event.
7. **Determinism:** cùng combo + cùng RecordedLLM (key theo lens-id) → cùng tập dòng về agent.

## Event types (lean — chỉ 2 mới)

`LENS_QUERIED` {hệ, combo|adhoc, lens_id, reads:[]} · `LENS_RETURNED` {lens_id, line} (no verdict). Bracket consult = TOOL_CALLED/TOOL_RESULT sẵn có. Lens-consult-denied = TOOL_DENIED sẵn có.

## Touchpoints (cho plan)

capability.py (consult permission flag) · registries.py (LensRegistry) · orchestrator.py (`_run_tool` nhánh consult_lenses + mandate dispatch) · agent.py (`Agent.he`) · events.py (2 event) · wiring.py (seed lens config + hệ attr) · harness/data/lenses.yaml · topology.py (hệ attr — đã mở).

## Câu hỏi mở

- Catalog seed: ship sẵn hệ/lens nào lúc đầu?
- "agent gọi thêm lens": tự do mọi lens trong catalog, hay chỉ lens cùng hệ?
- Cascade biểu diễn phụ thuộc trong combo config thế nào (field `reads:`)?
